"""
BotOrchestrator — owns the dictionary of running ``UserBot`` instances.

API surface:
- ``start(user_id)``   — instantiate + start a UserBot
- ``stop(user_id)``    — stop + remove a UserBot
- ``get_state(user_id)`` — returns the per-user UserBotState (or a fresh empty one)
- ``boot_persisted_users()`` — on app start, restart bots for users with
  ``bot_enabled=True``

Thread-safe: a single lock guards ``_bots`` mutation.
"""

from __future__ import annotations

import threading

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.api.state import UserBotState
from src.bot.scanner import MarketDataScanner
from src.bot.user_worker import UserBot, build_user_bot
from src.db.engine import session_scope
from src.db import repositories as repo
from src.db.models import User
from src.monitoring.logger import get_logger
from src.security.crypto import CredentialVault


log = get_logger()


class BotOrchestrator:
    def __init__(self, scanner: MarketDataScanner, vault: CredentialVault):
        self._scanner = scanner
        self._vault   = vault
        self._bots: dict[str, UserBot] = {}
        self._lock = threading.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, user_id: str) -> bool:
        with self._lock:
            if user_id in self._bots:
                return True

            bot = build_user_bot(user_id, self._scanner, self._vault)
            if bot is None:
                log.warning(f"Cannot start bot for {user_id[:8]}: no config row")
                return False

            self._bots[user_id] = bot

        bot.start()

        with session_scope() as db:
            user = db.get(User, user_id)
            if user:
                user.bot_enabled = True
        return True

    def stop(self, user_id: str) -> None:
        with self._lock:
            bot = self._bots.pop(user_id, None)
        if bot:
            bot.stop()
        with session_scope() as db:
            user = db.get(User, user_id)
            if user:
                user.bot_enabled = False

    def set_mode(self, user_id: str, mode: str) -> None:
        with session_scope() as db:
            user = db.get(User, user_id)
            if user:
                user.mode = mode
        # Restart the bot if currently running so the new mode takes effect
        with self._lock:
            running = user_id in self._bots
        if running:
            self.stop(user_id)
            self.start(user_id)

    # ── Read access ───────────────────────────────────────────────────────────

    def get_state(self, user_id: str) -> UserBotState:
        with self._lock:
            bot = self._bots.get(user_id)
        if bot:
            return bot.state
        # Return an empty stub state so API handlers can render zero values
        from src.bot.config import BotConfig
        from src.exchange.paper_trader import PaperTrader
        from src.trading.portfolio import Portfolio

        cfg = BotConfig.defaults()
        with session_scope() as db:
            row = repo.get_bot_config(db, user_id)
        if row is not None:
            cfg = BotConfig.from_user_row(row)

        stub_paper = PaperTrader(cfg)
        stub_portfolio = Portfolio(user_id=user_id, initial_capital_inr=cfg.initial_capital_inr)
        return UserBotState(
            user_id=user_id,
            paper_trader=stub_paper,
            portfolio=stub_portfolio,
            mode="paper",
            is_running=False,
        )

    def is_running(self, user_id: str) -> bool:
        with self._lock:
            return user_id in self._bots

    def all_states(self) -> dict[str, UserBotState]:
        with self._lock:
            return {uid: bot.state for uid, bot in self._bots.items()}

    # ── Boot ──────────────────────────────────────────────────────────────────

    def boot_persisted_users(self) -> None:
        with session_scope() as db:
            users = repo.list_users_with_bot_enabled(db)
            user_ids = [u.clerk_user_id for u in users]
        for uid in user_ids:
            try:
                self.start(uid)
            except Exception:
                log.exception(f"Failed to boot bot for {uid[:8]}")
