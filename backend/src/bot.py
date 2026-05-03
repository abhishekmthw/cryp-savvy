"""
Main bot loop.
Orchestrates: coin scanning → signal analysis → risk checks → order execution →
              portfolio logging → dashboard refresh → alerts → API state update.

Run with:
    python src/bot.py
"""

import time
import signal
import sys
import os
import threading

# Make project root importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings
from src.exchange.coindcx_client import CoinDCXClient
from src.exchange.paper_trader import PaperTrader
from src.data.market_data import MarketData
from src.analysis.signal_engine import analyse_symbol, analyse_open_position, Signal
from src.trading.risk_manager import RiskManager
from src.trading.order_manager import OrderManager
from src.trading.portfolio import Portfolio
from src.monitoring.logger import get_logger
from src.monitoring import alerts
from src.monitoring import dashboard
from src.api.state import BotState

log = get_logger()


def _start_api_server(bot_state: BotState):
    """Launch the FastAPI server (called from a daemon thread)."""
    import uvicorn
    from src.api.main import create_app

    app = create_app(bot_state)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.API_PORT,
        log_level="warning",  # suppress uvicorn access logs; bot logger handles the rest
    )


class TradingBot:
    def __init__(self):
        log.info(f"Initialising bot | mode=[bold]{settings.MODE.upper()}[/bold]")

        self._paper       = PaperTrader()
        self._exchange    = CoinDCXClient()
        self._market_data = MarketData(self._exchange)
        self._risk        = RiskManager(self._paper)
        self._order_mgr   = OrderManager(
            self._paper,
            live_client=self._exchange if settings.LIVE else None,
        )
        self._portfolio   = Portfolio()

        # Shared state — read by the API server thread
        self._state = BotState(
            paper_trader=self._paper,
            portfolio=self._portfolio,
            is_running=True,
        )

        # Start API server in a daemon thread so it dies with the bot process
        api_thread = threading.Thread(
            target=_start_api_server,
            args=(self._state,),
            daemon=True,
            name="api-server",
        )
        api_thread.start()
        log.info(f"API server started on port {settings.API_PORT}")

        self._last_daily_summary = 0.0
        self._running = True

        alerts.alert_startup(settings.MODE)

    # ── Core Scan ─────────────────────────────────────────────────────────────

    def _scan(self):
        log.info("Starting scan cycle …")

        # 1. Fetch top momentum coins
        symbols = self._market_data.get_top_momentum_symbols()
        if not symbols:
            log.warning("No symbols returned by momentum scanner — skipping cycle")
            return

        # 2. Fetch current prices for all symbols of interest
        all_symbols = list(set(symbols) | set(self._paper.positions.keys()))
        current_prices: dict[str, float] = {}
        for sym in all_symbols:
            price = self._market_data.get_current_price(sym)
            if price:
                current_prices[sym] = price

        # 3. Check exit conditions for open positions first
        for sym in list(self._paper.positions.keys()):
            price = current_prices.get(sym)
            if price is None:
                continue

            should_exit, reason = self._risk.should_exit(sym, price)
            if should_exit:
                trade = self._order_mgr.sell(sym, price, reason=reason)
                if trade:
                    log.info(
                        f"SELL {sym} | reason={reason} | "
                        f"P&L ₹{trade['pnl']:+.2f} ({trade['pnl_pct']:+.2f}%)"
                    )
                    self._portfolio.record_trade(trade)
                    alerts.alert_sell(sym, price, trade["pnl"], trade["pnl_pct"], reason, settings.MODE)
                    self._state.push_event("trade_sell", {
                        "symbol":    sym,
                        "price":     price,
                        "pnl":       trade["pnl"],
                        "pnl_pct":   trade["pnl_pct"],
                        "reason":    reason,
                        "timestamp": time.time(),
                    })
                    if self._paper.is_daily_limit_hit:
                        log.warning("Daily loss limit hit — pausing trading for today")
                        alerts.alert_daily_limit()
                        self._state.push_event("daily_limit_hit", {"timestamp": time.time()})
                continue

            # Signal-based exit
            analysis = analyse_open_position(sym, self._market_data)
            if analysis["action"] == Signal.SELL:
                trade = self._order_mgr.sell(sym, price, reason="sell_signal")
                if trade:
                    log.info(
                        f"SELL {sym} | reason=signal | score={analysis['composite_score']} | "
                        f"P&L ₹{trade['pnl']:+.2f} ({trade['pnl_pct']:+.2f}%)"
                    )
                    self._portfolio.record_trade(trade)
                    alerts.alert_sell(sym, price, trade["pnl"], trade["pnl_pct"], "sell_signal", settings.MODE)
                    self._state.push_event("trade_sell", {
                        "symbol":    sym,
                        "price":     price,
                        "pnl":       trade["pnl"],
                        "pnl_pct":   trade["pnl_pct"],
                        "reason":    "sell_signal",
                        "timestamp": time.time(),
                    })

        # 4. Evaluate new entry opportunities
        signals = []
        for sym in symbols:
            if sym in self._paper.positions:
                continue

            analysis = analyse_symbol(sym, self._market_data)
            signals.append(analysis)

            if analysis["action"] == Signal.BUY:
                price = current_prices.get(sym)
                if price is None:
                    continue

                allowed, reason = self._risk.can_open_position(sym)
                if not allowed:
                    log.debug(f"BUY {sym} blocked: {reason}")
                    continue

                amount_inr = self._risk.position_size_inr()
                order = self._order_mgr.buy(sym, amount_inr, price)
                if order:
                    log.info(
                        f"BUY  {sym} | price=₹{price:,.4f} | "
                        f"amount=₹{amount_inr:,.2f} | score={analysis['composite_score']}"
                    )
                    alerts.alert_buy(sym, price, amount_inr, analysis["composite_score"], settings.MODE)
                    self._state.push_event("trade_buy", {
                        "symbol":     sym,
                        "price":      price,
                        "amount_inr": amount_inr,
                        "score":      analysis["composite_score"],
                        "timestamp":  time.time(),
                    })

        # 5. Update shared API state
        self._state.update_scan(signals, current_prices)
        self._state.push_event("scan_complete", {
            "signals":        signals,
            "open_positions": self._paper.open_position_count,
            "timestamp":      time.time(),
        })

        # 6. Refresh CLI dashboard
        stats = self._portfolio.stats()
        dashboard.render(self._paper, stats, signals, current_prices)

        # 7. Daily summary (once per day)
        now = time.time()
        if now - self._last_daily_summary >= 86_400:
            portfolio_value = self._paper.portfolio_value(current_prices)
            alerts.alert_daily_summary(stats, portfolio_value)
            self._last_daily_summary = now

    # ── Main Loop ─────────────────────────────────────────────────────────────

    def run(self):
        log.info(f"Bot running | scan interval: {settings.SCAN_INTERVAL_S}s | Ctrl-C to stop")

        def _stop(signum, frame):
            log.info("Shutdown signal received — stopping bot …")
            self._running = False
            self._state.is_running = False

        signal.signal(signal.SIGINT,  _stop)
        signal.signal(signal.SIGTERM, _stop)

        while self._running:
            try:
                self._scan()
            except Exception as exc:
                log.exception(f"Unexpected error in scan cycle: {exc}")
                alerts.alert_error(str(exc))

            if not self._running:
                break

            log.info(f"Sleeping {settings.SCAN_INTERVAL_S}s until next scan …")
            for _ in range(settings.SCAN_INTERVAL_S):
                if not self._running:
                    break
                time.sleep(1)

        log.info("Bot stopped.")
        self._portfolio.close()


if __name__ == "__main__":
    TradingBot().run()
