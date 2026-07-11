"""
The live bot must decide entries/exits on the last CLOSED candle, not the
still-forming one — otherwise it chases intrabar spikes that reverse by the
close (the main reason live diverged from the closed-bar backtest).
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings
from src.analysis import signal_engine
from src.analysis.signal_engine import analyse_symbol


class _FakeMarketData:
    def __init__(self, df):
        self._df = df
    def get_ohlcv(self, symbol):
        return self._df


def _base_ohlcv(n=100):
    rng = np.random.default_rng(7)
    closes = 100 + np.cumsum(rng.normal(0.5, 1.0, n))
    closes = np.clip(closes, 1, None)
    opens = closes * rng.uniform(0.999, 1.001, n)
    highs = np.maximum(opens, closes) * rng.uniform(1.000, 1.003, n)
    lows = np.minimum(opens, closes) * rng.uniform(0.997, 1.000, n)
    vol = rng.uniform(1_000, 5_000, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": vol}, index=idx).astype(float)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    # analyse_symbol calls sentiment → stub it so the test never hits the network.
    monkeypatch.setattr(signal_engine, "get_sentiment_score", lambda *_a, **_k: 0.0)


def test_forming_candle_is_ignored_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "SIGNAL_ON_CLOSED_CANDLE", True)
    base = _base_ohlcv(100)

    # Two versions that differ ONLY in the last (forming) bar: one a violent
    # upside spike, one a violent dump. With closed-candle decisions the last bar
    # is dropped, so both must yield the identical signal.
    spike = base.copy()
    spike.iloc[-1, spike.columns.get_loc("close")] = base["close"].iloc[-2] * 5
    spike.iloc[-1, spike.columns.get_loc("high")] = base["close"].iloc[-2] * 5

    dump = base.copy()
    dump.iloc[-1, dump.columns.get_loc("close")] = base["close"].iloc[-2] * 0.2
    dump.iloc[-1, dump.columns.get_loc("low")] = base["close"].iloc[-2] * 0.2

    a = analyse_symbol("X/USDT", _FakeMarketData(spike))
    b = analyse_symbol("X/USDT", _FakeMarketData(dump))
    assert a["action"] == b["action"]
    assert a["technical_score"] == b["technical_score"]
    assert a["composite_score"] == b["composite_score"]


def test_forming_candle_changes_result_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "SIGNAL_ON_CLOSED_CANDLE", False)
    base = _base_ohlcv(100)
    spike = base.copy()
    spike.iloc[-1, spike.columns.get_loc("close")] = base["close"].iloc[-2] * 5
    spike.iloc[-1, spike.columns.get_loc("high")] = base["close"].iloc[-2] * 5
    dump = base.copy()
    dump.iloc[-1, dump.columns.get_loc("close")] = base["close"].iloc[-2] * 0.2
    dump.iloc[-1, dump.columns.get_loc("low")] = base["close"].iloc[-2] * 0.2

    a = analyse_symbol("X/USDT", _FakeMarketData(spike))
    b = analyse_symbol("X/USDT", _FakeMarketData(dump))
    # Acting on the forming bar, a 5× spike vs an 80% dump must NOT look identical.
    assert a["technical_score"] != b["technical_score"]
