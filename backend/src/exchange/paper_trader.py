"""
Paper trading simulator.
Maintains a fake INR balance and fake positions so the bot can be
tested without real money. Now per-user — every instance owns one user's
balance, positions, and daily P&L.
"""

from __future__ import annotations

import datetime
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.bot.config import BotConfig


def _utc_day_start(now: Optional[float] = None) -> float:
    """Epoch seconds for the most recent UTC midnight — a stable day boundary
    that (unlike 'seconds since process start') survives a restart."""
    dt = datetime.datetime.fromtimestamp(now if now is not None else time.time(),
                                         tz=datetime.timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


@dataclass
class PaperPosition:
    symbol:        str
    qty:           float
    entry_price:   float
    entry_time:    float
    amount_usdt:    float
    stop_loss:     float
    take_profit:   float
    trailing_high: float = 0.0
    bucket:        str = "day"
    # Entry attribution — recorded at buy time so a closed trade can be traced
    # back to which sub-strategy/regime opened it (diagnostics).
    strategy:      str = "none"
    regime:        Optional[str] = None
    entry_score:   Optional[float] = None
    order_id:      str = field(default_factory=lambda: str(uuid.uuid4())[:8])


class PaperTrader:
    def __init__(self, config: BotConfig):
        self._cfg = config
        self.balance_usdt: float = config.initial_capital_usdt
        self.positions: dict[str, PaperPosition] = {}
        self.closed_trades: list[dict] = []
        self._daily_pnl: float = 0.0
        self._day_start: float = _utc_day_start()

    @property
    def initial_capital_usdt(self) -> float:
        return self._cfg.initial_capital_usdt

    # ── State ─────────────────────────────────────────────────────────────────

    def reset_daily_pnl_if_new_day(self):
        today = _utc_day_start()
        if today > self._day_start:
            self._daily_pnl = 0.0
            self._day_start = today

    def restore_daily_pnl(self, realized_today: float) -> None:
        """Re-seed today's realized P&L from the DB on restart so the daily
        loss-limit circuit-breaker can't be reset by bouncing the process."""
        self._day_start = _utc_day_start()
        self._daily_pnl = realized_today

    def restore_position(self, p: dict) -> None:
        """Re-open a persisted position WITHOUT touching balance (the caller
        reconstructs cash separately from realized P&L and deployed capital)."""
        pos = PaperPosition(
            symbol=p["symbol"], qty=p["qty"], entry_price=p["entry_price"],
            entry_time=p["entry_time"], amount_usdt=p["amount_usdt"],
            stop_loss=p["stop_loss"], take_profit=p["take_profit"],
            trailing_high=p.get("trailing_high") or p["entry_price"],
            bucket=p.get("bucket", "day"),
            strategy=p.get("strategy", "none"),
            regime=p.get("regime"),
            entry_score=p.get("entry_score"),
        )
        if p.get("order_id"):
            pos.order_id = p["order_id"]
        self.positions[p["symbol"]] = pos

    def position_as_dict(self, symbol: str) -> Optional[dict]:
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        return {
            "symbol": pos.symbol, "qty": pos.qty, "entry_price": pos.entry_price,
            "entry_time": pos.entry_time, "amount_usdt": pos.amount_usdt,
            "stop_loss": pos.stop_loss, "take_profit": pos.take_profit,
            "trailing_high": pos.trailing_high, "order_id": pos.order_id,
            "bucket": pos.bucket, "strategy": pos.strategy, "regime": pos.regime,
            "entry_score": pos.entry_score, "status": "open",
        }

    @property
    def daily_pnl(self) -> float:
        self.reset_daily_pnl_if_new_day()
        return self._daily_pnl

    @property
    def is_daily_limit_hit(self) -> bool:
        return self.daily_pnl <= -self._cfg.daily_loss_limit_usdt

    @property
    def open_position_count(self) -> int:
        return len(self.positions)

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_market_buy(self, symbol: str, amount_usdt: float,
                         current_price: float,
                         fill_price: Optional[float] = None,
                         fill_qty: Optional[float] = None,
                         atr: Optional[float] = None,
                         bucket: str = "day",
                         strategy: str = "none",
                         regime: Optional[str] = None,
                         entry_score: Optional[float] = None) -> Optional[PaperPosition]:
        if self.is_daily_limit_hit:
            return None
        if self.open_position_count >= self._cfg.max_open_positions:
            return None
        if symbol in self.positions:
            return None

        live_fill = fill_price is not None
        if fill_qty is not None:
            # Live mode: use the *actual* exchange fill (already net of real fees).
            entry_price  = fill_price if live_fill else current_price
            qty          = fill_qty
            actual_spend = qty * entry_price
        else:
            # Paper mode: model slippage (worse entry) + taker fee (fewer units).
            base_price   = fill_price if live_fill else current_price
            entry_price  = base_price * (1 + settings.SLIPPAGE_PCT)
            actual_spend = min(amount_usdt, self.balance_usdt, self._cfg.max_position_usdt)
            if actual_spend < settings.MIN_TRADE_USDT:
                return None
            qty = (actual_spend / entry_price) * (1 - settings.FEE_PCT)

        stop_loss, take_profit = self._compute_stops(entry_price, atr, bucket)

        position = PaperPosition(
            symbol=symbol,
            qty=qty,
            entry_price=entry_price,
            entry_time=time.time(),
            amount_usdt=actual_spend,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_high=entry_price,
            bucket=bucket,
            strategy=strategy,
            regime=regime,
            entry_score=entry_score,
        )

        self.balance_usdt -= actual_spend
        self.positions[symbol] = position
        return position

    def _compute_stops(self, entry_price: float, atr: Optional[float],
                       bucket: str) -> tuple[float, float]:
        """ATR-based stops scaled by bucket; falls back to fixed-pct stops when
        ATR is unavailable or ATR stops are disabled."""
        if settings.USE_ATR_STOPS and atr:
            if bucket == "long":
                sl_mult, tp_mult = settings.ATR_SL_MULT_LONG, settings.ATR_TP_MULT_LONG
            else:
                sl_mult, tp_mult = settings.ATR_SL_MULT_DAY, settings.ATR_TP_MULT_DAY
            return (entry_price - sl_mult * atr, entry_price + tp_mult * atr)
        return (entry_price * (1 - self._cfg.stop_loss_pct),
                entry_price * (1 + self._cfg.take_profit_pct))

    def place_market_sell(self, symbol: str, current_price: float,
                          reason: str = "signal",
                          fill_qty: Optional[float] = None) -> Optional[dict]:
        position = self.positions.pop(symbol, None)
        if position is None:
            return None

        # A live partial fill closes only ``fill_qty`` of the position; the
        # remainder is re-opened so the book stays consistent with the exchange.
        sold_qty = position.qty if fill_qty is None else min(fill_qty, position.qty)
        cost_basis = position.amount_usdt * (sold_qty / position.qty) if position.qty else position.amount_usdt

        if fill_qty is None:
            # Paper mode: model slippage (worse exit) + taker fee on proceeds.
            exit_price = current_price * (1 - settings.SLIPPAGE_PCT)
            proceeds = sold_qty * exit_price * (1 - settings.FEE_PCT)
        else:
            # Live: proceeds are the actual exchange fill, already net of fees.
            exit_price = current_price
            proceeds = sold_qty * exit_price
        pnl      = proceeds - cost_basis
        pnl_pct  = (pnl / cost_basis) * 100 if cost_basis else 0.0

        self.balance_usdt += proceeds
        self._daily_pnl  += pnl

        remaining_qty = position.qty - sold_qty
        if remaining_qty > 1e-12:
            position.qty = remaining_qty
            position.amount_usdt -= cost_basis
            self.positions[symbol] = position

        record = {
            "order_id":    position.order_id,
            "symbol":      symbol,
            "entry_price": position.entry_price,
            "exit_price":  exit_price,
            "qty":         sold_qty,
            "amount_usdt":  cost_basis,
            "proceeds":    proceeds,
            "pnl":         pnl,
            "pnl_pct":     pnl_pct,
            "reason":      reason,
            "bucket":      position.bucket,
            "strategy":    position.strategy,
            "regime":      position.regime,
            "entry_score": position.entry_score,
            "duration_s":  time.time() - position.entry_time,
        }
        self.closed_trades.append(record)
        return record

    # ── Per-bucket views (capital-allocation feature) ──────────────────────────

    def deployed_in(self, bucket: str) -> float:
        """USDT currently deployed (cost basis of open positions) in a bucket."""
        return sum(p.amount_usdt for p in self.positions.values() if p.bucket == bucket)

    def unrealized_in(self, bucket: str, prices: dict[str, float]) -> float:
        total = 0.0
        for p in self.positions.values():
            if p.bucket != bucket:
                continue
            price = prices.get(p.symbol, p.entry_price)
            total += p.qty * price - p.amount_usdt
        return total

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
        return self.balance_usdt + open_value

    def summary(self, prices: dict[str, float]) -> dict:
        total_value = self.portfolio_value(prices)
        return {
            "balance_usdt":    round(self.balance_usdt, 2),
            "open_positions": self.open_position_count,
            "portfolio_value": round(total_value, 2),
            "total_pnl":      round(total_value - self._cfg.initial_capital_usdt, 2),
            "daily_pnl":      round(self._daily_pnl, 2),
            "total_trades":   len(self.closed_trades),
        }
