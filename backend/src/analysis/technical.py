"""
Technical indicator calculations using pandas-ta.
Returns individual sub-scores (0–100) for each indicator.
"""

import pandas as pd
import pandas_ta as ta
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


def compute_indicators(df: pd.DataFrame) -> Optional[dict]:
    """
    Given an OHLCV DataFrame, compute all indicators and return a dict
    of sub-scores. Returns None if the DataFrame is too short.
    """
    min_rows = max(settings.EMA_SLOW, settings.MACD_SLOW, settings.RSI_PERIOD) + 10
    if len(df) < min_rows:
        return None

    df = df.copy()

    # EMA crossover
    df.ta.ema(length=settings.EMA_FAST, append=True)
    df.ta.ema(length=settings.EMA_SLOW, append=True)
    ema_fast_col = f"EMA_{settings.EMA_FAST}"
    ema_slow_col = f"EMA_{settings.EMA_SLOW}"

    # RSI
    df.ta.rsi(length=settings.RSI_PERIOD, append=True)
    rsi_col = f"RSI_{settings.RSI_PERIOD}"

    # MACD
    df.ta.macd(
        fast=settings.MACD_FAST,
        slow=settings.MACD_SLOW,
        signal=settings.MACD_SIGNAL,
        append=True,
    )
    macd_hist_col = f"MACDh_{settings.MACD_FAST}_{settings.MACD_SLOW}_{settings.MACD_SIGNAL}"

    # Volume SMA
    df["volume_sma20"] = df["volume"].rolling(20).mean()

    last = df.iloc[-1]

    # ── EMA score (0 or 25) ───────────────────────────────────────────────────
    try:
        ema_bullish = float(last[ema_fast_col]) > float(last[ema_slow_col])
    except (KeyError, TypeError, ValueError):
        ema_bullish = False
    ema_score = 25 if ema_bullish else 0

    # ── RSI score (0, 15, or 25) ──────────────────────────────────────────────
    try:
        rsi = float(last[rsi_col])
    except (KeyError, TypeError, ValueError):
        rsi = 50.0

    if settings.RSI_LOWER <= rsi <= settings.RSI_UPPER:
        rsi_score = 25    # Sweet-spot: momentum without being overbought
    elif rsi < settings.RSI_LOWER:
        rsi_score = 10    # Weak momentum — caution
    else:
        rsi_score = 0     # Overbought — avoid chasing

    # ── MACD histogram score (0 or 25) ────────────────────────────────────────
    try:
        macd_hist = float(last[macd_hist_col])
        macd_score = 25 if macd_hist > 0 else 0
    except (KeyError, TypeError, ValueError):
        macd_score = 0

    # ── Volume score (0 or 25) ────────────────────────────────────────────────
    try:
        vol_ratio = float(last["volume"]) / float(last["volume_sma20"])
        volume_score = 25 if vol_ratio >= settings.VOLUME_MULT else 0
    except (ZeroDivisionError, TypeError, ValueError):
        volume_score = 0

    total = ema_score + rsi_score + macd_score + volume_score   # max 100

    return {
        "ema_score":    ema_score,
        "rsi_score":    rsi_score,
        "macd_score":   macd_score,
        "volume_score": volume_score,
        "technical_total": total,   # 0–100
        "rsi_value":    round(rsi, 2),
        "ema_fast":     round(float(last.get(ema_fast_col, 0)), 4),
        "ema_slow":     round(float(last.get(ema_slow_col, 0)), 4),
    }
