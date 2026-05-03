"""
Tests for the technical indicator and signal scoring logic.
These run without any live exchange or network access.
"""

import sys, os
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.analysis.technical import compute_indicators
from src.analysis.signal_engine import Signal
from src.data.sentiment import sentiment_to_score_0_100


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ohlcv(n: int = 100, trend: str = "up") -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame with a clear trend."""
    rng = np.random.default_rng(42)
    base = 50_000.0
    if trend == "up":
        closes = base + np.cumsum(rng.normal(200, 100, n))
    elif trend == "down":
        closes = base + np.cumsum(rng.normal(-200, 100, n))
    else:
        closes = base + rng.normal(0, 300, n)

    closes = np.clip(closes, 1, None)
    opens  = closes * rng.uniform(0.998, 1.002, n)
    highs  = np.maximum(opens, closes) * rng.uniform(1.000, 1.005, n)
    lows   = np.minimum(opens, closes) * rng.uniform(0.995, 1.000, n)
    volume = rng.uniform(1_000, 10_000, n)

    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volume},
        index=idx,
    ).astype(float)


# ── compute_indicators ────────────────────────────────────────────────────────

class TestComputeIndicators:
    def test_returns_none_on_short_df(self):
        df = _make_ohlcv(10)
        assert compute_indicators(df) is None

    def test_returns_dict_on_sufficient_data(self):
        df = _make_ohlcv(100)
        result = compute_indicators(df)
        assert result is not None
        assert "technical_total" in result

    def test_score_range(self):
        for trend in ("up", "down", "sideways"):
            df = _make_ohlcv(100, trend=trend)
            result = compute_indicators(df)
            assert result is not None
            assert 0 <= result["technical_total"] <= 100

    def test_uptrend_scores_higher_than_downtrend(self):
        up_score   = compute_indicators(_make_ohlcv(100, "up"))["technical_total"]
        down_score = compute_indicators(_make_ohlcv(100, "down"))["technical_total"]
        # Uptrend should consistently produce a higher EMA signal
        assert up_score >= down_score


# ── sentiment_to_score_0_100 ──────────────────────────────────────────────────

class TestSentimentScoring:
    def test_neutral_maps_to_50(self):
        assert sentiment_to_score_0_100(0.0) == 50.0

    def test_full_positive_maps_to_100(self):
        assert sentiment_to_score_0_100(1.0) == 100.0

    def test_full_negative_maps_to_0(self):
        assert sentiment_to_score_0_100(-1.0) == 0.0

    def test_midpoint_values(self):
        assert sentiment_to_score_0_100(0.5) == 75.0
        assert sentiment_to_score_0_100(-0.5) == 25.0


# ── Signal constants ──────────────────────────────────────────────────────────

class TestSignalConstants:
    def test_signal_values_are_strings(self):
        assert isinstance(Signal.BUY,  str)
        assert isinstance(Signal.SELL, str)
        assert isinstance(Signal.HOLD, str)

    def test_signal_values_distinct(self):
        assert len({Signal.BUY, Signal.SELL, Signal.HOLD}) == 3
