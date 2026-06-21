"""
Per-user portfolio adapter.

This is now a thin facade over ``src.db.repositories`` — the persistence
layer is SQLAlchemy/Postgres, scoped by ``user_id``. The class keeps the
same method names (``record_trade``, ``stats``, …) the rest of the bot
already calls.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.db.engine import session_scope
from src.db import repositories as repo


class Portfolio:
    def __init__(self, user_id: str, initial_capital_usdt: float):
        self._user_id = user_id
        self._initial_capital = initial_capital_usdt

    def record_trade(self, trade: dict) -> None:
        with session_scope() as db:
            repo.record_trade(db, user_id=self._user_id, trade=trade)

    # ── Orders (idempotent intent log) ────────────────────────────────────────

    def create_order(self, **kwargs) -> None:
        with session_scope() as db:
            repo.create_order(db, user_id=self._user_id, **kwargs)

    def update_order(self, client_order_id: str, **fields) -> None:
        with session_scope() as db:
            repo.update_order(db, client_order_id, **fields)

    # ── Open-position persistence (restart recovery) ──────────────────────────

    def upsert_position(self, position: dict) -> None:
        with session_scope() as db:
            repo.upsert_position(db, self._user_id, position)

    def delete_position(self, symbol: str) -> None:
        with session_scope() as db:
            repo.delete_position(db, self._user_id, symbol)

    def load_positions(self) -> list:
        with session_scope() as db:
            return [
                {
                    "symbol":        p.symbol,
                    "qty":           float(p.qty),
                    "entry_price":   float(p.entry_price),
                    "entry_time":    float(p.entry_time),
                    "amount_usdt":    float(p.amount_usdt),
                    "stop_loss":     float(p.stop_loss),
                    "take_profit":   float(p.take_profit),
                    "trailing_high": float(p.trailing_high),
                    "order_id":      p.order_id,
                    "bucket":        getattr(p, "bucket", "day"),
                }
                for p in repo.positions_for_user(db, self._user_id)
            ]

    def daily_realized_pnl(self, day_start_ts: float) -> float:
        with session_scope() as db:
            return repo.daily_realized_pnl(db, self._user_id, day_start_ts)

    # ── Allocation / bucket state ─────────────────────────────────────────────

    def load_allocation(self) -> dict | None:
        with session_scope() as db:
            a = repo.get_allocation(db, self._user_id)
            if a is None or a.status != "active":
                return None
            return {
                "total": float(a.total_allocated),
                "day_budget": float(a.day_budget),
                "long_budget": float(a.long_budget),
                "allocate_all": bool(a.allocate_all),
                "status": a.status,
            }

    def load_bucket_states(self) -> dict[str, dict]:
        with session_scope() as db:
            return {
                s.bucket: {
                    "realized_pnl": float(s.realized_pnl),
                    "peak_equity": float(s.peak_equity),
                    "drawdown_state": s.drawdown_state,
                }
                for s in repo.get_bucket_states(db, self._user_id)
            }

    def save_bucket_state(self, bucket: str, realized_pnl: float,
                          peak_equity: float, drawdown_state: str) -> None:
        with session_scope() as db:
            repo.upsert_bucket_state(
                db, user_id=self._user_id, bucket=bucket,
                realized_pnl=realized_pnl, peak_equity=peak_equity,
                drawdown_state=drawdown_state,
            )

    def stats(self) -> dict:
        with session_scope() as db:
            return repo.trade_stats(db, self._user_id)
