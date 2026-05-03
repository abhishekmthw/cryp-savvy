"""
Per-user trading worker.

Each ``UserBot`` instance is bound to one Clerk user and owns:
- a ``BotConfig`` (loaded from the user's ``user_bot_config`` row)
- a ``PaperTrader`` (in-memory positions)
- a ``RiskManager`` + ``OrderManager``
- a per-user ``CoinDCXClient`` (for live mode) decrypted from the vault
- a ``TelegramAlerter`` (per-user bot+chat, decrypted from the vault)

It reads market data from the shared scanner cache — never issues its
own market-data requests.
"""

from __future__ import annotations

import sys
import os
import threading
import time
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.analysis.signal_engine import analyse_open_position, analyse_symbol, Signal
from src.bot.config import BotConfig
from src.bot.scanner import MarketDataScanner
from src.db.engine import session_scope
from src.db import repositories as repo
from src.db.models import User
from src.exchange.coindcx_client import CoinDCXClient
from src.exchange.paper_trader import PaperTrader
from src.monitoring.alerts import TelegramAlerter, NULL_ALERTER
from src.monitoring.logger import get_logger
from src.security.crypto import CredentialVault
from src.trading.order_manager import OrderManager
from src.trading.portfolio import Portfolio
from src.trading.risk_manager import RiskManager


log = get_logger()


class UserBot:
    def __init__(
        self,
        *,
        user_id: str,
        config: BotConfig,
        mode: str,
        coindcx_client: CoinDCXClient,
        alerter: TelegramAlerter,
        portfolio: Portfolio,
        scanner: MarketDataScanner,
    ):
        self.user_id = user_id
        self._cfg    = config
        self._mode   = mode
        self._scanner = scanner
        self._portfolio = portfolio

        self._paper      = PaperTrader(config)
        self._coindcx    = coindcx_client
        self._alerter    = alerter
        self._risk       = RiskManager(self._paper, config)
        self._order_mgr  = OrderManager(self._paper, mode=mode, live_client=coindcx_client)

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_daily_summary = 0.0

        # Per-user shared API state — populated each tick, read by FastAPI handlers
        from src.api.state import UserBotState
        self.state = UserBotState(
            user_id=user_id,
            paper_trader=self._paper,
            portfolio=portfolio,
            mode=mode,
            is_running=False,
        )

    # ── Public lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.state.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"user-bot-{self.user_id[:8]}")
        self._thread.start()
        self._alerter.alert_startup(self._mode)
        log.info(f"UserBot {self.user_id[:8]} started in {self._mode} mode")

    def stop(self) -> None:
        self._stop.set()
        self.state.is_running = False
        if self._thread:
            self._thread.join(timeout=5)
        log.info(f"UserBot {self.user_id[:8]} stopped")

    # ── Worker loop ───────────────────────────────────────────────────────────

    def _run(self) -> None:
        # Wait for the first scan, then process subsequent scans as they happen.
        while not self._stop.is_set():
            # Block until scanner has a fresh cache to read
            self._scanner.scan_complete_event.wait(timeout=1)
            if self._stop.is_set():
                break
            try:
                self._tick()
            except Exception as exc:
                log.exception(f"UserBot {self.user_id[:8]} tick failed: {exc}")
                self._alerter.alert_error(str(exc))

    def _tick(self) -> None:
        with self._scanner.cache.lock:
            symbols = list(self._scanner.cache.symbols)
            current_prices = dict(self._scanner.cache.current_prices)
            market_data = self._scanner.cache.market_data

        if not symbols or market_data is None:
            return

        # 1. Exit checks for open positions
        for sym in list(self._paper.positions.keys()):
            price = current_prices.get(sym)
            if price is None:
                # Refresh the price for any held symbol not in the top-N
                price = market_data.get_current_price(sym)
                if price is None:
                    continue
                current_prices[sym] = price

            should_exit, reason = self._risk.should_exit(sym, price)
            if should_exit:
                self._do_sell(sym, price, reason=reason)
                if self._paper.is_daily_limit_hit:
                    self._alerter.alert_daily_limit()
                    self.state.push_event("daily_limit_hit", {"timestamp": time.time()})
                continue

            analysis = analyse_open_position(sym, market_data)
            if analysis["action"] == Signal.SELL:
                self._do_sell(sym, price, reason="sell_signal", score=analysis.get("composite_score"))

        # 2. Entry checks
        signals = []
        for sym in symbols:
            if sym in self._paper.positions:
                continue

            analysis = analyse_symbol(sym, market_data)
            signals.append(analysis)

            if analysis["action"] != Signal.BUY:
                continue
            price = current_prices.get(sym)
            if price is None:
                continue

            allowed, _ = self._risk.can_open_position(sym)
            if not allowed:
                continue

            amount_inr = self._risk.position_size_inr()
            order = self._order_mgr.buy(sym, amount_inr, price)
            if order:
                self._alerter.alert_buy(sym, price, amount_inr,
                                        analysis["composite_score"], self._mode)
                self.state.push_event("trade_buy", {
                    "symbol":     sym,
                    "price":      price,
                    "amount_inr": amount_inr,
                    "score":      analysis["composite_score"],
                    "timestamp":  time.time(),
                })

        # 3. Update per-user state
        self.state.update_scan(signals, current_prices)
        self.state.push_event("scan_complete", {
            "signals":        signals,
            "open_positions": self._paper.open_position_count,
            "timestamp":      time.time(),
        })

        # 4. Daily summary (once per day, per user)
        now = time.time()
        if now - self._last_daily_summary >= 86_400:
            stats = self._portfolio.stats()
            self._alerter.alert_daily_summary(stats, self._paper.portfolio_value(current_prices))
            self._last_daily_summary = now

    def _do_sell(self, symbol: str, price: float, reason: str, score: Optional[float] = None) -> None:
        trade = self._order_mgr.sell(symbol, price, reason=reason)
        if not trade:
            return
        self._portfolio.record_trade(trade)
        self._alerter.alert_sell(symbol, price, trade["pnl"], trade["pnl_pct"], reason, self._mode)
        self.state.push_event("trade_sell", {
            "symbol":    symbol,
            "price":     price,
            "pnl":       trade["pnl"],
            "pnl_pct":   trade["pnl_pct"],
            "reason":    reason,
            "timestamp": time.time(),
        })


# ── Factory ─────────────────────────────────────────────────────────────────

def build_user_bot(user_id: str, scanner: MarketDataScanner,
                   vault: CredentialVault) -> UserBot | None:
    """
    Construct a UserBot from the DB row + vault. Returns None if the user has
    no CoinDCX credentials saved (paper mode still works, but the design is
    that bot-start is gated on credentials existing).
    """
    from src.api.credentials import (
        P_COINDCX_KEY, P_COINDCX_SECRET, P_TELEGRAM_TOKEN, P_TELEGRAM_CHAT,
    )

    with session_scope() as db:
        user: User | None = db.get(User, user_id)
        if user is None:
            return None
        cfg_row = repo.get_bot_config(db, user_id)
        if cfg_row is None:
            return None
        cfg = BotConfig.from_user_row(cfg_row)
        mode = user.mode

        # Decrypt credentials if present (CoinDCX is required only for live mode)
        dek = vault.unwrap_dek(user.wrapped_dek, user.dek_nonce)

        api_key = api_secret = ""
        ck = repo.get_credential(db, user_id, P_COINDCX_KEY)
        cs = repo.get_credential(db, user_id, P_COINDCX_SECRET)
        if ck and cs:
            api_key    = vault.decrypt(dek, ck.ciphertext, ck.nonce)
            api_secret = vault.decrypt(dek, cs.ciphertext, cs.nonce)

        coindcx_client = CoinDCXClient(api_key=api_key, api_secret=api_secret)

        # Telegram is optional
        tt = repo.get_credential(db, user_id, P_TELEGRAM_TOKEN)
        tc = repo.get_credential(db, user_id, P_TELEGRAM_CHAT)
        if tt and tc:
            alerter = TelegramAlerter(
                bot_token=vault.decrypt(dek, tt.ciphertext, tt.nonce),
                chat_id=vault.decrypt(dek, tc.ciphertext, tc.nonce),
                capital_inr=cfg.initial_capital_inr,
                daily_loss_limit_inr=cfg.daily_loss_limit_inr,
            )
        else:
            alerter = NULL_ALERTER

    portfolio = Portfolio(user_id=user_id, initial_capital_inr=cfg.initial_capital_inr)

    return UserBot(
        user_id=user_id,
        config=cfg,
        mode=mode,
        coindcx_client=coindcx_client,
        alerter=alerter,
        portfolio=portfolio,
        scanner=scanner,
    )
