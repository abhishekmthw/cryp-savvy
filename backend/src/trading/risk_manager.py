"""
Risk manager.
Decides whether a proposed trade is permitted given the current portfolio
state, position limits, and daily loss cap.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.bot.config import BotConfig


class RiskManager:
    def __init__(self, trader, config: BotConfig):
        self._trader = trader
        self._cfg = config

    def can_open_position(self, symbol: str) -> tuple[bool, str]:
        if self._trader.is_daily_limit_hit:
            return False, f"Daily loss limit of ₹{self._cfg.daily_loss_limit_inr} reached — bot paused for today"

        if self._trader.open_position_count >= self._cfg.max_open_positions:
            return False, f"Max open positions ({self._cfg.max_open_positions}) reached"

        if symbol in self._trader.positions:
            return False, f"Already have an open position in {symbol}"

        if self._trader.balance_inr < 100:
            return False, f"Insufficient balance (₹{self._trader.balance_inr:.2f})"

        return True, "ok"

    def position_size_inr(self) -> float:
        return min(self._cfg.max_position_inr, self._trader.balance_inr)

    def should_exit(self, symbol: str, current_price: float) -> tuple[bool, str]:
        reason = self._trader.check_exit_conditions(symbol, current_price)
        if reason:
            return True, reason
        return False, ""
