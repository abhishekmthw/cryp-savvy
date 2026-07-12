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


def bucket_mults(bucket: str) -> tuple[float, float]:
    """(sl_mult, tp_mult) for a bucket."""
    if bucket == LONG:
        return settings.ATR_SL_MULT_LONG, settings.ATR_TP_MULT_LONG
    return settings.ATR_SL_MULT_DAY, settings.ATR_TP_MULT_DAY


def atr_stops(entry_price: float, atr_val: float, bucket: str) -> tuple[float, float]:
    """ATR-based stop-loss / take-profit for a long entry, scaled by bucket
    (tighter for day-trades, wider for long-term holds).

    The stop is floored at entry×(1−MAX_STOP_DISTANCE_PCT_*) — a hard per-trade
    loss cap so one high-ATR entry can't risk -8..-14%. The TP is never
    adjusted, so the entry ATR stays derivable from (tp − entry) / tp_mult.
    """
    if bucket == LONG:
        sl_mult, tp_mult = settings.ATR_SL_MULT_LONG, settings.ATR_TP_MULT_LONG
        max_dist = settings.MAX_STOP_DISTANCE_PCT_LONG
    else:
        sl_mult, tp_mult = settings.ATR_SL_MULT_DAY, settings.ATR_TP_MULT_DAY
        max_dist = settings.MAX_STOP_DISTANCE_PCT_DAY
    stop = entry_price - sl_mult * atr_val
    if max_dist is not None:
        stop = max(stop, entry_price * (1 - max_dist))
    return (stop, entry_price + tp_mult * atr_val)


def entry_atr_from_stops(entry_price: float, take_profit: float, bucket: str) -> float:
    """Recover the ATR that was in effect at entry from the persisted, immutable
    (entry_price, take_profit) pair. atr_stops never adjusts the TP, so
    tp = entry + tp_mult·atr holds exactly — this makes ATR-based trailing
    restart-safe with no schema change. Returns 0.0 for fixed-pct positions."""
    _, tp_mult = bucket_mults(bucket)
    if tp_mult <= 0:
        return 0.0
    return (take_profit - entry_price) / tp_mult


def trail_stop(entry_price: float, take_profit: float, trailing_high: float,
               bucket: str, cfg_trigger: float, cfg_offset: float) -> float | None:
    """Candidate trailing stop for a long position, or None while unarmed.

    Shared by the paper trader and the backtest engine so live exits and the
    validation gate are the same math by construction. The caller must ratchet:
    stop = max(stop, candidate).

    "atr_r" mode arms once the high is +TRAIL_ARM_R × R above entry
    (R = sl_mult·ATR, the initial risk) and trails TRAIL_ATR_MULT_*×ATR below
    the high — at the arming moment with trail mult == sl_mult that is exactly
    breakeven. "fixed_pct" mode is the legacy percent trigger/offset.
    """
    if settings.TRAILING_MODE == "atr_r":
        atr_val = entry_atr_from_stops(entry_price, take_profit, bucket)
        if atr_val > 0:
            sl_mult, _ = bucket_mults(bucket)
            arm_gain = settings.TRAIL_ARM_R * sl_mult * atr_val
            if trailing_high - entry_price >= arm_gain:
                trail_mult = (settings.TRAIL_ATR_MULT_LONG if bucket == LONG
                              else settings.TRAIL_ATR_MULT_DAY)
                return trailing_high - trail_mult * atr_val
            return None
        # Fixed-pct position (ATR unavailable at entry) — fall through to legacy.
    gain_pct = (trailing_high - entry_price) / entry_price if entry_price else 0.0
    if gain_pct >= cfg_trigger:
        return trailing_high * (1 - cfg_offset)
    return None
