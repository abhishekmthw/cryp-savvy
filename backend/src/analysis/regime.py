"""
Market-regime detection — the meta-layer that selects which sub-strategy is
active. Using a bull strategy in a bear regime (or mean-reversion in a strong
trend) is the single biggest documented failure mode, so every entry decision
is gated on the regime first.

Regimes: "bull" | "bear" | "sideways".
Method: fast vs slow SMA with a flat band. When the SMAs are within
``REGIME_FLAT_BAND`` of each other the market is treated as sideways
(range-bound) rather than trending.
"""

from __future__ import annotations

import sys
import os

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.analysis.indicators import sma

BULL = "bull"
BEAR = "bear"
SIDEWAYS = "sideways"


def detect_regime(df: pd.DataFrame,
                  fast: int = None, slow: int = None,
                  flat_band: float = None) -> str:
    fast = fast or settings.REGIME_FAST_SMA
    slow = slow or settings.REGIME_SLOW_SMA
    flat_band = settings.REGIME_FLAT_BAND if flat_band is None else flat_band

    if len(df) < slow + 1:
        return SIDEWAYS  # not enough data → assume range-bound (most conservative)

    close = df["close"]
    fast_sma = sma(close, fast).iloc[-1]
    slow_sma = sma(close, slow).iloc[-1]
    if pd.isna(fast_sma) or pd.isna(slow_sma) or slow_sma == 0:
        return SIDEWAYS

    gap = (fast_sma - slow_sma) / slow_sma
    if abs(gap) < flat_band:
        return SIDEWAYS
    return BULL if gap > 0 else BEAR
