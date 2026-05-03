"""
Paper trading simulator.
Maintains a fake INR balance and fake positions so the bot can be
tested without real money.
"""

import uuid
import time
from dataclasses import dataclass, field
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


@dataclass
class PaperPosition:
    symbol:        str
    qty:           float          # Amount of crypto held
    entry_price:   float          # Price at which we bought
    entry_time:    float          # Unix timestamp
    amount_inr:    float          # INR spent (for record-keeping)
    stop_loss:     float          # Absolute price for stop-loss
    take_profit:   float          # Absolute price for take-profit
    trailing_high: float = 0.0   # Highest price seen since entry (for trailing stop)
    order_id:      str = field(default_factory=lambda: str(uuid.uuid4())[:8])


class PaperTrader:
    """
    Drop-in replacement for live order execution.
    All methods mirror the CoinDCXClient interface so the rest of the
    bot doesn't need to care whether it's live or paper.
    """

    def __init__(self):
        self.balance_inr: float = settings.INITIAL_CAPITAL_INR
        self.positions: dict[str, PaperPosition] = {}   # symbol → position
        self.closed_trades: list[dict] = []
        self._daily_pnl: float = 0.0
        self._day_start: float = time.time()

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
        return self.daily_pnl <= -settings.DAILY_LOSS_LIMIT_INR

    @property
    def open_position_count(self) -> int:
        return len(self.positions)

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_market_buy(self, symbol: str, amount_inr: float,
                         current_price: float) -> Optional[PaperPosition]:
        """
        Simulate a market buy.
        Returns the PaperPosition or None if the order was rejected
        (insufficient balance, position limit reached, daily loss limit hit).
        """
        if self.is_daily_limit_hit:
            return None
        if self.open_position_count >= settings.MAX_OPEN_POSITIONS:
            return None
        if symbol in self.positions:
            return None   # Already have a position in this coin

        actual_spend = min(amount_inr, self.balance_inr, settings.MAX_POSITION_INR)
        if actual_spend < 100:   # CoinDCX minimum order ~₹100
            return None

        qty          = actual_spend / current_price
        stop_loss    = current_price * (1 - settings.STOP_LOSS_PCT)
        take_profit  = current_price * (1 + settings.TAKE_PROFIT_PCT)

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
        """
        Simulate a market sell.
        Returns a trade record dict or None if no position exists.
        """
        position = self.positions.pop(symbol, None)
        if position is None:
            return None

        proceeds   = position.qty * current_price
        pnl        = proceeds - position.amount_inr
        pnl_pct    = (pnl / position.amount_inr) * 100

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
        """Raise the trailing stop if the price has moved up enough."""
        pos = self.positions.get(symbol)
        if pos is None:
            return

        gain_pct = (current_price - pos.entry_price) / pos.entry_price
        if gain_pct >= settings.TRAILING_STOP_TRIGGER:
            if current_price > pos.trailing_high:
                pos.trailing_high = current_price
                pos.stop_loss = pos.trailing_high * (1 - settings.TRAILING_STOP_OFFSET)

    def check_exit_conditions(self, symbol: str,
                              current_price: float) -> Optional[str]:
        """
        Check if price has hit stop-loss or take-profit.
        Returns the exit reason string, or None if position should stay open.
        """
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
        """Total value: free INR balance + mark-to-market open positions."""
        open_value = sum(
            pos.qty * prices.get(pos.symbol, pos.entry_price)
            for pos in self.positions.values()
        )
        return self.balance_inr + open_value

    def summary(self, prices: dict[str, float]) -> dict:
        total_value = self.portfolio_value(prices)
        return {
            "balance_inr":   round(self.balance_inr, 2),
            "open_positions": self.open_position_count,
            "portfolio_value": round(total_value, 2),
            "total_pnl":     round(total_value - settings.INITIAL_CAPITAL_INR, 2),
            "daily_pnl":     round(self._daily_pnl, 2),
            "total_trades":  len(self.closed_trades),
        }
