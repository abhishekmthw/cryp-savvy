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

from cryptography.exceptions import InvalidTag

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.analysis.signal_engine import analyse_open_position, analyse_symbol, Signal
from src.bot.config import BotConfig
from src.bot.errors import BotStartError
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


def _dominant_regime(signals: list) -> Optional[str]:
    """Most common regime across the scanned signals (drives shift suggestions)."""
    counts: dict[str, int] = {}
    for s in signals:
        r = s.get("regime")
        if r:
            counts[r] = counts.get(r, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


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
        allocation=None,
    ):
        self.user_id = user_id
        self._cfg    = config
        self._mode   = mode
        self._scanner = scanner
        self._portfolio = portfolio
        self._alloc  = allocation

        self._paper      = PaperTrader(config)
        self._coindcx    = coindcx_client
        self._alerter    = alerter
        self._risk       = RiskManager(self._paper, config, allocation=allocation)
        self._last_regime: Optional[str] = None
        self._order_mgr  = OrderManager(
            self._paper, mode=mode, live_client=coindcx_client,
            user_id=user_id, order_store=portfolio,
            quote_currency=settings.QUOTE_CURRENCY,
        )

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._fast_thread: Optional[threading.Thread] = None
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
        # Fast SL/TP + live-price monitor (independent of the 5-min scan).
        self._fast_thread = threading.Thread(target=self._fast_loop, daemon=True,
                                             name=f"fast-{self.user_id[:8]}")
        self._fast_thread.start()
        self._alerter.alert_startup(self._mode)
        log.info(f"UserBot {self.user_id[:8]} started in {self._mode} mode")

    def stop(self) -> None:
        self._stop.set()
        self.state.is_running = False
        for t in (self._thread, getattr(self, "_fast_thread", None)):
            if t:
                t.join(timeout=5)
        # Wipe decrypted exchange credentials from memory on stop.
        try:
            self._coindcx.clear_keys()
        except Exception:
            pass
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

        # 1. SL / TP / trailing exits (also handled continuously by _fast_loop).
        # ``state.lock`` guards every read/write of paper_trader so the API
        # handlers never iterate a dict that's being mutated here.
        self._check_exits(current_prices)

        # 1b. Signal-based exits — needs OHLCV, so only on the full scan.
        with self.state.lock:
            held = list(self._paper.positions.keys())
        for sym in held:
            price = current_prices.get(sym) or market_data.get_current_price(sym)
            if price is None:
                continue
            analysis = analyse_open_position(sym, market_data)
            if analysis["action"] == Signal.SELL:
                self._do_sell(sym, price, reason="sell_signal", score=analysis.get("composite_score"))

        # 2. Entry checks
        signals = []
        for sym in symbols:
            with self.state.lock:
                if sym in self._paper.positions:
                    continue

            analysis = analyse_symbol(sym, market_data)
            signals.append(analysis)

            if analysis["action"] != Signal.BUY:
                continue
            price = current_prices.get(sym)
            if price is None:
                continue

            atr = analysis.get("atr")
            bucket = analysis.get("bucket") or "day"
            with self.state.lock:
                allowed, _ = self._risk.can_open_position(sym, bucket)
                if not allowed:
                    continue
                amount_usdt = self._risk.position_size_usdt(price=price, atr=atr, bucket=bucket)
                if amount_usdt < settings.MIN_TRADE_USDT:
                    continue
                order = self._order_mgr.buy(
                    sym, amount_usdt, price, atr=atr, bucket=bucket,
                    strategy=analysis.get("strategy", "none"),
                    regime=analysis.get("regime"),
                    score=analysis.get("composite_score"),
                )
            if order:
                self._persist_position(sym)
                self._alerter.alert_buy(sym, price, amount_usdt,
                                        analysis["composite_score"], self._mode)
                self.state.push_event("trade_buy", {
                    "symbol":     sym,
                    "price":      price,
                    "amount_usdt": amount_usdt,
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

        # 3b. Suggest a day/long split if the dominant regime flipped
        self._maybe_suggest_shift(_dominant_regime(signals))

        # 4. Daily summary (once per day, per user)
        now = time.time()
        if now - self._last_daily_summary >= 86_400:
            stats = self._portfolio.stats()
            self._alerter.alert_daily_summary(stats, self._paper.portfolio_value(current_prices))
            self._last_daily_summary = now

    def _do_sell(self, symbol: str, price: float, reason: str, score: Optional[float] = None) -> None:
        with self.state.lock:
            trade = self._order_mgr.sell(symbol, price, reason=reason)
            still_open = symbol in self._paper.positions
        if not trade:
            return
        self._portfolio.record_trade(trade)
        # Route realized P&L to its bucket (profit compounds in-bucket) and
        # update that bucket's drawdown circuit-breaker.
        self._account_bucket_close(trade)
        # Keep the persisted open-positions table in sync with the book.
        if still_open:
            self._persist_position(symbol)   # partial fill — remainder stays open
        else:
            self._safe(lambda: self._portfolio.delete_position(symbol))
        self._alerter.alert_sell(symbol, price, trade["pnl"], trade["pnl_pct"], reason, self._mode)
        self.state.push_event("trade_sell", {
            "symbol":    symbol,
            "price":     price,
            "pnl":       trade["pnl"],
            "pnl_pct":   trade["pnl_pct"],
            "reason":    reason,
            "timestamp": time.time(),
        })

    # ── Fast monitor loop (SL/TP/trailing + live prices) ───────────────────────

    def _fast_loop(self) -> None:
        """Runs every ``FAST_POLL_S``: refresh held-symbol prices, enforce
        stop-loss/take-profit/trailing immediately (not on the 5-min cadence),
        and push a ``price_update`` so the dashboard shows live P&L."""
        while not self._stop.is_set():
            self._scanner.price_event.wait(timeout=settings.FAST_POLL_S)
            if self._stop.is_set():
                break
            try:
                with self.state.lock:
                    held = list(self._paper.positions.keys())
                if not held:
                    continue

                all_prices = self._scanner.get_all_prices_snapshot()
                prices = {s: all_prices[s] for s in held if s in all_prices}
                # Fall back to a direct fetch for any held symbol missing a price.
                md = self._scanner.cache.market_data
                for s in held:
                    if s not in prices and md is not None:
                        p = md.get_current_price(s)
                        if p is not None:
                            prices[s] = p
                if not prices:
                    continue

                self._check_exits(prices)

                with self.state.lock:
                    self.state.current_prices.update(prices)
                    snapshot_prices = dict(self.state.current_prices)
                    portfolio_value = self._paper.portfolio_value(snapshot_prices)
                    daily_pnl = self._paper.daily_pnl
                self.state.push_event("price_update", {
                    "prices":          prices,
                    "portfolio_value": round(portfolio_value, 2),
                    "daily_pnl":       round(daily_pnl, 2),
                    "timestamp":       time.time(),
                })
            except Exception:
                log.exception(f"UserBot {self.user_id[:8]} fast loop failed")

    def _check_exits(self, prices: dict) -> None:
        """Enforce SL/TP/trailing for held symbols using ``prices``. Safe to call
        from both the fast loop and the 5-min tick."""
        with self.state.lock:
            held = list(self._paper.positions.keys())
        for sym in held:
            price = prices.get(sym)
            if price is None:
                continue
            with self.state.lock:
                should_exit, reason = self._risk.should_exit(sym, price)
            if should_exit:
                self._do_sell(sym, price, reason=reason)
                if self._paper.is_daily_limit_hit:
                    self._alerter.alert_daily_limit()
                    self.state.push_event("daily_limit_hit", {"timestamp": time.time()})
            else:
                # the exit check may have advanced the trailing stop — persist it
                self._persist_position(sym)

    # ── bucket accounting (capital allocation) ─────────────────────────────────

    def _account_bucket_close(self, trade: dict) -> None:
        if self._alloc is None:
            return
        bucket = trade.get("bucket") or "day"
        b = self._alloc.get(bucket)
        if b is None:
            return
        self._alloc.record_close(bucket, trade["pnl"])
        with self.state.lock:
            equity = b.capital + self._paper.unrealized_in(bucket, self.state.current_prices)
        state = self._alloc.update_drawdown(bucket, equity)
        if state in ("halted", "paused"):
            self.state.push_event("bucket_drawdown", {
                "bucket": bucket, "state": state, "timestamp": time.time(),
            })
        self._safe(lambda: self._portfolio.save_bucket_state(
            bucket, b.realized_pnl, b.peak_equity, b.drawdown_state))

    def _maybe_suggest_shift(self, regime: Optional[str]) -> None:
        """When the dominant regime flips, suggest a day/long split — but never
        move funds without the user confirming (POST /api/allocation/confirm-shift)."""
        if self._alloc is None or not regime or regime == self._last_regime:
            self._last_regime = regime
            return
        self._last_regime = regime
        # trending → favour the long bucket; sideways → favour the day bucket
        if regime == "bull":
            day_pct, long_pct = 25, 75
        elif regime == "sideways":
            day_pct, long_pct = 45, 55
        else:  # bear — de-risk: hold mostly long-term, minimal day-trading
            day_pct, long_pct = 15, 85
        self.state.push_event("shift_suggestion", {
            "regime": regime, "suggested_day_pct": day_pct,
            "suggested_long_pct": long_pct, "timestamp": time.time(),
        })

    # ── persistence helpers ────────────────────────────────────────────────────

    def _persist_position(self, symbol: str) -> None:
        with self.state.lock:
            snapshot = self._paper.position_as_dict(symbol)
        if snapshot is None:
            self._safe(lambda: self._portfolio.delete_position(symbol))
        else:
            self._safe(lambda: self._portfolio.upsert_position(snapshot))

    @staticmethod
    def _safe(fn) -> None:
        try:
            fn()
        except Exception:
            log.exception("position persistence failed")


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

        # Decrypt credentials if present (CoinDCX is required only for live mode).
        # An InvalidTag here means the deployment's MASTER_ENCRYPTION_KEY no longer
        # matches the key these credentials were wrapped with — surface a clear,
        # actionable message instead of letting it bubble up as a bare 500.
        try:
            dek = vault.unwrap_dek(user.wrapped_dek, user.dek_nonce)
        except InvalidTag as exc:
            log.warning("DEK unwrap failed for %s — KEK mismatch", user_id[:8])
            raise BotStartError(
                "Saved credentials can't be decrypted. The encryption key on this "
                "deployment doesn't match the one used when they were saved. "
                "Re-save your CoinDCX keys in Settings, or restore the original "
                "MASTER_ENCRYPTION_KEY."
            ) from exc

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
                capital_usdt=cfg.initial_capital_usdt,
                daily_loss_limit_usdt=cfg.daily_loss_limit_usdt,
            )
        else:
            alerter = NULL_ALERTER

    portfolio = Portfolio(user_id=user_id, initial_capital_usdt=cfg.initial_capital_usdt)

    # Build the allocation (day/long buckets) if the user has set one.
    allocation = _build_allocation(portfolio)

    bot = UserBot(
        user_id=user_id,
        config=cfg,
        mode=mode,
        coindcx_client=coindcx_client,
        alerter=alerter,
        portfolio=portfolio,
        scanner=scanner,
        allocation=allocation,
    )
    _restore_state(bot, portfolio, cfg, allocation)
    return bot


def _build_allocation(portfolio: Portfolio):
    """Construct an AllocationManager from the user's saved allocation + bucket
    state, or return None (single-pool mode) if they haven't allocated yet."""
    from src.trading.allocation import AllocationManager
    alloc_row = portfolio.load_allocation()
    if alloc_row is None:
        return None
    states = portfolio.load_bucket_states()
    mgr = AllocationManager.from_budgets(
        day_budget=alloc_row["day_budget"],
        long_budget=alloc_row["long_budget"],
        day_realized=states.get("day", {}).get("realized_pnl", 0.0),
        long_realized=states.get("long", {}).get("realized_pnl", 0.0),
    )
    for bucket, st in states.items():
        b = mgr.get(bucket)
        if b is not None:
            b.peak_equity = st.get("peak_equity", 0.0)
            b.drawdown_state = st.get("drawdown_state", "normal")
    return mgr


def _restore_state(bot: "UserBot", portfolio: Portfolio, cfg: BotConfig,
                   allocation=None) -> None:
    """
    Rebuild in-memory paper-trader state from the DB after a restart so open
    positions, available cash, and today's realized P&L survive a crash. Without
    this, a restart would silently reset the daily loss-limit and abandon open
    positions (see analysis finding #10).
    """
    try:
        positions = portfolio.load_positions()
        realized_all = float(portfolio.stats().get("total_pnl", 0.0) or 0.0)
        deployed = sum(float(p["amount_usdt"]) for p in positions)
        # Starting capital is the allocation total when set, else the config default.
        base_capital = (allocation.total_capital - realized_all
                        if allocation is not None else cfg.initial_capital_usdt)
        # cash = capital + all realized P&L − capital currently deployed
        bot._paper.balance_usdt = base_capital + realized_all - deployed
        for p in positions:
            bot._paper.restore_position(p)
        from src.exchange.paper_trader import _utc_day_start
        bot._paper.restore_daily_pnl(portfolio.daily_realized_pnl(_utc_day_start()))
        if positions:
            log.info("Restored %d open position(s) for %s from DB",
                     len(positions), bot.user_id[:8])
    except Exception:
        log.exception("State restore failed for %s — starting fresh", bot.user_id[:8])
