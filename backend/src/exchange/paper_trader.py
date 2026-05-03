"""
Paper trading simulator.
Maintains a fake INR balance and fake positions so the bot can be
tested without real money. Now per-user — every instance owns one user's
balance, positions, and daily P&L.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.bot.config import BotConfig


@dataclass
class PaperPosition:
    symbol:        str
    qty:           float
    entry_price:   float
    entry_time:    float
    amount_inr:    float
    stop_loss:     float
    take_profit:   float
    trailing_high: float = 0.0
    order_id:      str = field(default_factory=lambda: str(uuid.uuid4())[:8])


class PaperTrader:
    def __init__(self, config: BotConfig):
        self._cfg = config
        self.balance_inr: float = config.initial_capital_inr
        self.positions: dict[str, PaperPosition] = {}
        self.closed_trades: list[dict] = []
        self._daily_pnl: float = 0.0
        self._day_start: float = time.time()

    @property
    def initial_capital_inr(self) -> float:
        return self._cfg.initial_capital_inr

    # ── State ─────────────────────────────────────────────────────────────────

    def reset_daily_pnl_if_new_day(self):
        now = time.time()
        if now - self._day_start >= 86_400:
            self._daily_pnl = 0.0
            self._day_start = now

    @property
    def daily_pnl(self) -> float:
        self.reset_daily_pnl_if_new_day()
        return self._daily_pnl

    @property
    def is_daily_limit_hit(self) -> bool:
        return self.daily_pnl <= -self._cfg.daily_loss_limit_inr

    @property
    def open_position_count(self) -> int:
        return len(self.positions)

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_market_buy(self, symbol: str, amount_inr: float,
                         current_price: float) -> Optional[PaperPosition]:
        if self.is_daily_limit_hit:
            return None
        if self.open_position_count >= self._cfg.max_open_positions:
            return None
        if symbol in self.positions:
            return None

        actual_spend = min(amount_inr, self.balance_inr, self._cfg.max_position_inr)
        if actual_spend < 100:
            return None

        qty         = actual_spend / current_price
        stop_loss   = current_price * (1 - self._cfg.stop_loss_pct)
        take_profit = current_price * (1 + self._cfg.take_profit_pct)

        position = PaperPosition(
            symbol=symbol,
            qty=qty,
            entry_price=current_price,
            entry_time=time.time(),
            amount_inr=actual_spend,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_high=current_price,
        )

        self.balance_inr -= actual_spend
        self.positions[symbol] = position
        return position

    def place_market_sell(self, symbol: str, current_price: float,
                          reason: str = "signal") -> Optional[dict]:
        position = self.positions.pop(symbol, None)
        if position is None:
            return None

        proceeds = position.qty * current_price
        pnl      = proceeds - position.amount_inr
        pnl_pct  = (pnl / position.amount_inr) * 100

        self.balance_inr += proceeds
        self._daily_pnl  += pnl

        record = {
            "order_id":    position.order_id,
            "symbol":      symbol,
            "entry_price": position.entry_price,
            "exit_price":  current_price,
            "qty":         position.qty,
            "amount_inr":  position.amount_inr,
            "proceeds":    proceeds,
            "pnl":         pnl,
            "pnl_pct":     pnl_pct,
            "reason":      reason,
            "duration_s":  time.time() - position.entry_time,
        }
        self.closed_trades.append(record)
        return record

    # ── Position Maintenance ──────────────────────────────────────────────────

    def update_trailing_stop(self, symbol: str, current_price: float):
        pos = self.positions.get(symbol)
        if pos is None:
            return

        gain_pct = (current_price - pos.entry_price) / pos.entry_price
        if gain_pct >= self._cfg.trailing_stop_trigger:
            if current_price > pos.trailing_high:
                pos.trailing_high = current_price
                pos.stop_loss = pos.trailing_high * (1 - self._cfg.trailing_stop_offset)

    def check_exit_conditions(self, symbol: str,
                              current_price: float) -> Optional[str]:
        pos = self.positions.get(symbol)
        if pos is None:
            return None

        self.update_trailing_stop(symbol, current_price)

        if current_price <= pos.stop_loss:
            return "stop_loss"
        if current_price >= pos.take_profit:
            return "take_profit"
        return None

    # ── Summary ───────────────────────────────────────────────────────────────

    def portfolio_value(self, prices: dict[str, float]) -> float:
        open_value = sum(
            pos.qty * prices.get(pos.symbol, pos.entry_price)
            for pos in self.positions.values()
        )
        return self.balance_inr + open_value

    def summary(self, prices: dict[str, float]) -> dict:
        total_value = self.portfolio_value(prices)
        return {
            "balance_inr":    round(self.balance_inr, 2),
            "open_positions": self.open_position_count,
            "portfolio_value": round(total_value, 2),
            "total_pnl":      round(total_value - self._cfg.initial_capital_inr, 2),
            "daily_pnl":      round(self._daily_pnl, 2),
            "total_trades":   len(self.closed_trades),
        }
