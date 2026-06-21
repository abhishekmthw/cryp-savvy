"""
Capital allocation — splits the user's USDT into isolated day-trading and
long-term buckets.

Design (logical partition over a single physical balance):
- Each bucket has a fixed ``budget`` (set when the user allocates). Realized P&L
  accrues to the bucket so **profit compounds inside the bucket** — it is never
  withdrawn. A bucket's *effective capital* = budget + realized_pnl.
- A new entry in a bucket is allowed only while its deployed capital + the new
  size stays within that bucket's effective capital → buckets can't borrow from
  each other.
- Each bucket has its own drawdown circuit-breaker (reduce → halt → pause).

The bot never moves money between buckets on its own; the split only changes
when the user confirms a suggested shift.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings

DAY = "day"
LONG = "long"


@dataclass
class BucketBudget:
    bucket: str
    budget: float
    realized_pnl: float = 0.0
    peak_equity: float = 0.0
    drawdown_state: str = "normal"   # normal | reduced | halted | paused

    @property
    def capital(self) -> float:
        """Effective capital — budget plus compounded realized P&L."""
        return self.budget + self.realized_pnl


@dataclass
class AllocationManager:
    buckets: dict[str, BucketBudget] = field(default_factory=dict)

    @classmethod
    def from_budgets(cls, day_budget: float, long_budget: float,
                     day_realized: float = 0.0, long_realized: float = 0.0) -> "AllocationManager":
        return cls(buckets={
            DAY:  BucketBudget(DAY,  day_budget,  day_realized),
            LONG: BucketBudget(LONG, long_budget, long_realized),
        })

    @property
    def total_capital(self) -> float:
        return sum(b.capital for b in self.buckets.values())

    def get(self, bucket: str) -> BucketBudget | None:
        return self.buckets.get(bucket)

    def available(self, bucket: str, deployed: float) -> float:
        b = self.buckets.get(bucket)
        if b is None:
            return 0.0
        return max(0.0, b.capital - deployed)

    def can_open(self, bucket: str, size: float, deployed: float) -> bool:
        b = self.buckets.get(bucket)
        if b is None or b.drawdown_state in ("halted", "paused"):
            return False
        return deployed + size <= b.capital + 1e-9

    def record_close(self, bucket: str, pnl: float) -> None:
        b = self.buckets.get(bucket)
        if b is not None:
            b.realized_pnl += pnl

    def update_drawdown(self, bucket: str, equity: float) -> str:
        """Update peak equity + drawdown tier for a bucket; returns the new
        state. Tiers (aggressive profile): reduce 15% → halt 25% → pause 35%."""
        b = self.buckets.get(bucket)
        if b is None:
            return "normal"
        b.peak_equity = max(b.peak_equity, equity, b.capital)
        if b.peak_equity <= 0:
            return b.drawdown_state
        dd = (b.peak_equity - equity) / b.peak_equity
        if dd >= settings.DRAWDOWN_PAUSE_PCT:
            b.drawdown_state = "paused"
        elif dd >= settings.DRAWDOWN_HALT_PCT:
            b.drawdown_state = "halted"
        elif dd >= settings.DRAWDOWN_REDUCE_PCT:
            b.drawdown_state = "reduced"
        else:
            b.drawdown_state = "normal"
        return b.drawdown_state
