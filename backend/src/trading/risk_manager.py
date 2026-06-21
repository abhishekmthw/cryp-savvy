"""
Risk manager.
Decides whether a proposed trade is permitted given the current portfolio
state, position limits, and daily loss cap.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.bot.config import BotConfig


class RiskManager:
    def __init__(self, trader, config: BotConfig, allocation=None):
        self._trader = trader
        self._cfg = config
        self._alloc = allocation   # AllocationManager or None (single-pool fallback)

    def _bucket_state(self, bucket: str) -> str:
        if self._alloc is None:
            return "normal"
        b = self._alloc.get(bucket)
        return b.drawdown_state if b else "normal"

    def can_open_position(self, symbol: str, bucket: str = "day") -> tuple[bool, str]:
        if self._trader.is_daily_limit_hit:
            return False, f"Daily loss limit of ${self._cfg.daily_loss_limit_usdt} reached — bot paused for today"

        if self._trader.open_position_count >= self._cfg.max_open_positions:
            return False, f"Max open positions ({self._cfg.max_open_positions}) reached"

        if symbol in self._trader.positions:
            return False, f"Already have an open position in {symbol}"

        if self._alloc is not None:
            state = self._bucket_state(bucket)
            if state in ("halted", "paused"):
                return False, f"{bucket} bucket {state} by drawdown circuit-breaker"
            deployed = self._trader.deployed_in(bucket)
            if self._alloc.available(bucket, deployed) < settings.MIN_TRADE_USDT:
                return False, f"{bucket} bucket budget exhausted"
            return True, "ok"

        if self._trader.balance_usdt < settings.MIN_TRADE_USDT:
            return False, f"Insufficient balance (${self._trader.balance_usdt:.2f})"
        return True, "ok"

    def position_size_usdt(self, price: float | None = None,
                           atr: float | None = None, bucket: str = "day",
                           drawdown_state: str | None = None) -> float:
        """
        Volatility-targeted sizing: risk a fixed fraction of the *bucket's*
        capital per trade, translated into a notional via the ATR stop distance,
        then capped by ``max_position_usdt`` and the bucket's available budget.
        Reduced by fractional Kelly and the bucket's drawdown state.
        """
        if drawdown_state is None:
            drawdown_state = self._bucket_state(bucket)

        # Capital base + spendable headroom depend on whether buckets are active.
        if self._alloc is not None and self._alloc.get(bucket) is not None:
            base_capital = self._alloc.get(bucket).capital
            available = self._alloc.available(bucket, self._trader.deployed_in(bucket))
        else:
            base_capital = self._trader.balance_usdt
            available = self._trader.balance_usdt

        risk_frac = self._risk_fraction()
        if drawdown_state == "reduced":
            risk_frac *= 0.5
        elif drawdown_state in ("halted", "paused"):
            return 0.0

        cap = min(self._cfg.max_position_usdt, available)
        if settings.USE_ATR_STOPS and atr and price:
            sl_mult = (settings.ATR_SL_MULT_LONG if bucket == "long"
                       else settings.ATR_SL_MULT_DAY)
            sl_distance = sl_mult * atr
            if sl_distance > 0:
                qty = (base_capital * risk_frac) / sl_distance
                return float(min(qty * price, cap))

        return float(cap)

    def _risk_fraction(self) -> float:
        """Base risk-per-trade, reduced by fractional Kelly once the closed-trade
        sample is large enough to estimate an edge."""
        base = settings.RISK_PER_TRADE
        trades = getattr(self._trader, "closed_trades", [])
        if settings.KELLY_FRACTION <= 0 or len(trades) < settings.KELLY_MIN_TRADES:
            return base
        wins = [t for t in trades if (t.get("pnl") or 0) > 0]
        losses = [t for t in trades if (t.get("pnl") or 0) < 0]
        if not wins or not losses:
            return base
        win_rate = len(wins) / len(trades)
        avg_win = sum(t["pnl"] for t in wins) / len(wins)
        avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses))
        if avg_loss <= 0:
            return base
        payoff = avg_win / avg_loss
        kelly = win_rate - (1 - win_rate) / payoff
        frac = settings.KELLY_FRACTION * max(0.0, kelly)
        return float(min(base, frac)) if frac > 0 else base * 0.5

    def should_exit(self, symbol: str, current_price: float) -> tuple[bool, str]:
        reason = self._trader.check_exit_conditions(symbol, current_price)
        if reason:
            return True, reason
        return False, ""
