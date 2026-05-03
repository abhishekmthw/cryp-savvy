"""
Per-user portfolio adapter.

This is now a thin facade over ``src.db.repositories`` — the persistence
layer is SQLAlchemy/Postgres, scoped by ``user_id``. The class keeps the
same method names (``record_trade``, ``stats``, ``recent_trades``,
``pnl_history``) the rest of the bot already calls.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.db.engine import session_scope
from src.db import repositories as repo


class Portfolio:
    def __init__(self, user_id: str, initial_capital_inr: float):
        self._user_id = user_id
        self._initial_capital = initial_capital_inr

    def record_trade(self, trade: dict) -> None:
        with session_scope() as db:
            repo.record_trade(db, user_id=self._user_id, trade=trade)

    def stats(self) -> dict:
        with session_scope() as db:
            return repo.trade_stats(db, self._user_id)

    def recent_trades(self, n: int = 10) -> list[dict]:
        with session_scope() as db:
            return repo.trades_for_user(db, self._user_id, limit=n)

    def pnl_history(self) -> list[dict]:
        with session_scope() as db:
            return repo.pnl_history_for_user(db, self._user_id, self._initial_capital)

    def close(self) -> None:
        # No persistent connection of our own — engine is module-level.
        pass
