"""
Per-user bot configuration as a simple dataclass.

Replaces direct reads of `config.settings.*` throughout the trading classes
so they can be instantiated per-user with values from `UserBotConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    initial_capital_usdt:    float
    max_position_usdt:       float
    max_open_positions:     int
    stop_loss_pct:          float
    take_profit_pct:        float
    trailing_stop_trigger:  float
    trailing_stop_offset:   float
    daily_loss_limit_usdt:   float

    @classmethod
    def from_user_row(cls, row) -> "BotConfig":
        return cls(
            initial_capital_usdt=float(row.initial_capital_usdt),
            max_position_usdt=float(row.max_position_usdt),
            max_open_positions=int(row.max_open_positions),
            stop_loss_pct=float(row.stop_loss_pct),
            take_profit_pct=float(row.take_profit_pct),
            trailing_stop_trigger=float(row.trailing_stop_trigger),
            trailing_stop_offset=float(row.trailing_stop_offset),
            daily_loss_limit_usdt=float(row.daily_loss_limit_usdt),
        )

    @classmethod
    def defaults(cls) -> "BotConfig":
        """Used by tests + as a fallback."""
        from config import settings
        return cls(
            initial_capital_usdt=settings.INITIAL_CAPITAL_USDT,
            max_position_usdt=settings.MAX_POSITION_USDT,
            max_open_positions=settings.MAX_OPEN_POSITIONS,
            stop_loss_pct=settings.STOP_LOSS_PCT,
            take_profit_pct=settings.TAKE_PROFIT_PCT,
            trailing_stop_trigger=settings.TRAILING_STOP_TRIGGER,
            trailing_stop_offset=settings.TRAILING_STOP_OFFSET,
            daily_loss_limit_usdt=settings.DAILY_LOSS_LIMIT_USDT,
        )
