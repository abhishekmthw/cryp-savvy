"""
Regime-aware strategy ensemble.

Given an OHLCV frame and the technical sub-scores, pick an entry/exit using the
sub-strategy appropriate to the current market regime, and tag it with the
capital bucket it belongs to:

    bull regime     → Donchian breakout (DAY) or trend-following (LONG)
    sideways regime → RSI mean-reversion (DAY)
    bear regime     → no new longs (spot-only); exits still allowed

The signal engine layers a composite-score quality gate on top of this.
"""

from __future__ import annotations

import sys
import os

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.analysis.indicators import donchian, latest_atr
from src.analysis.regime import detect_regime, BULL, BEAR, SIDEWAYS

# Action strings deliberately match signal_engine.Signal values to avoid a
# circular import.
BUY, SELL, HOLD = "BUY", "SELL", "HOLD"

# Capital buckets (consumed by the allocation feature).
DAY = "day"
LONG = "long"


def evaluate(df: pd.DataFrame, tech: dict) -> dict:
    regime = detect_regime(df)
    atr_val = latest_atr(df, settings.ATR_PERIOD)
    close = float(df["close"].iloc[-1])
    upper, lower = donchian(df, settings.DONCHIAN_PERIOD)

    rsi = float(tech.get("rsi_value", 50.0))
    ema_bull = tech.get("ema_score", 0) > 0
    macd_bull = tech.get("macd_score", 0) > 0
    vol_ok = tech.get("volume_score", 0) > 0

    action, bucket, strategy = HOLD, None, "none"

    if regime == BULL:
        if upper is not None and close > upper and vol_ok:
            action, bucket, strategy = BUY, DAY, "donchian_breakout"
        elif ema_bull and macd_bull:
            action, bucket, strategy = BUY, LONG, "trend_following"
        elif rsi >= settings.RSI_OVERBOUGHT and not macd_bull:
            action, strategy = SELL, "overbought_exit"
    elif regime == SIDEWAYS:
        if rsi <= settings.RSI_OVERSOLD:
            action, bucket, strategy = BUY, DAY, "rsi_mean_reversion"
        elif rsi >= settings.RSI_OVERBOUGHT:
            action, strategy = SELL, "rsi_mean_reversion_exit"
    else:  # BEAR — capital preservation: no new longs on spot, exits still allowed
        if rsi >= settings.RSI_OVERBOUGHT:
            action, strategy = SELL, "bear_exit"
        else:
            action, strategy = HOLD, "bear_no_entry"

    return {
        "regime":   regime,
        "atr":      atr_val,
        "action":   action,
        "bucket":   bucket,
        "strategy": strategy,
        "donchian_upper": upper,
        "donchian_lower": lower,
    }


def atr_stops(entry_price: float, atr_val: float, bucket: str) -> tuple[float, float]:
    """ATR-based stop-loss / take-profit for a long entry, scaled by bucket
    (tighter for day-trades, wider for long-term holds)."""
    if bucket == LONG:
        sl_mult, tp_mult = settings.ATR_SL_MULT_LONG, settings.ATR_TP_MULT_LONG
    else:
        sl_mult, tp_mult = settings.ATR_SL_MULT_DAY, settings.ATR_TP_MULT_DAY
    return (entry_price - sl_mult * atr_val, entry_price + tp_mult * atr_val)
