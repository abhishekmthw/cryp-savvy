"""
Risk manager.
Decides whether a proposed trade is permitted given current portfolio
state, position limits, and daily loss cap.
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


class RiskManager:
    def __init__(self, trader):
        """
        trader: PaperTrader instance (or a live order handler with the same interface).
        """
        self._trader = trader

    def can_open_position(self, symbol: str) -> tuple[bool, str]:
        """
        Returns (allowed: bool, reason: str).
        Checks: daily loss limit, max open positions, duplicate symbol.
        """
        if self._trader.is_daily_limit_hit:
            return False, f"Daily loss limit of ₹{settings.DAILY_LOSS_LIMIT_INR} reached — bot paused for today"

        if self._trader.open_position_count >= settings.MAX_OPEN_POSITIONS:
            return False, f"Max open positions ({settings.MAX_OPEN_POSITIONS}) reached"

        if symbol in self._trader.positions:
            return False, f"Already have an open position in {symbol}"

        if self._trader.balance_inr < 100:
            return False, f"Insufficient balance (₹{self._trader.balance_inr:.2f})"

        return True, "ok"

    def position_size_inr(self) -> float:
        """
        How much INR to allocate to the next trade.
        Uses the configured MAX_POSITION_INR, capped at available balance.
        """
        return min(settings.MAX_POSITION_INR, self._trader.balance_inr)

    def should_exit(self, symbol: str, current_price: float) -> tuple[bool, str]:
        """
        Returns (should_exit: bool, reason: str).
        Checks stop-loss and take-profit thresholds via the paper/live trader.
        """
        reason = self._trader.check_exit_conditions(symbol, current_price)
        if reason:
            return True, reason
        return False, ""
