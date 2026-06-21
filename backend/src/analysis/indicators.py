"""
Pure indicator helpers used by the strategy engine, regime detection, ATR-based
stops, and the backtester. All functions operate on an OHLCV DataFrame with
columns: open, high, low, close, volume (oldest-first).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder). Returns a Series aligned to df."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Wilder's smoothing ≈ EMA with alpha = 1/period
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def latest_atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    if len(df) < period + 1:
        return None
    val = atr(df, period).iloc[-1]
    return None if pd.isna(val) else float(val)


def donchian(df: pd.DataFrame, period: int = 20) -> tuple[Optional[float], Optional[float]]:
    """Return (upper, lower) Donchian channel over the *prior* `period` bars
    (excludes the current bar so a breakout is a genuine new extreme)."""
    if len(df) < period + 1:
        return None, None
    window = df.iloc[-(period + 1):-1]
    return float(window["high"].max()), float(window["low"].min())
