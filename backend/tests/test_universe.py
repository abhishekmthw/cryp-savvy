"""Universe selection: BTC/ETH always eligible + 24h volume floor."""

import sys, os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.exchange.coindcx_client import CoinDCXClient
from config import settings


def test_universe_includes_core_and_applies_volume_floor(monkeypatch):
    c = CoinDCXClient()
    fake = {
        "BTC/USDT":    {"percentage": -1.0, "quoteVolume": 1e9},  # core, kept despite negative
        "ETH/USDT":    {"percentage":  0.5, "quoteVolume": 1e9},  # core
        "LOWVOL/USDT": {"percentage":  5.0, "quoteVolume": 100.0},  # below floor → dropped
        "MOVER/USDT":  {"percentage":  3.0, "quoteVolume": 5e6},   # liquid mover → kept
        "FALLER/USDT": {"percentage": -2.0, "quoteVolume": 5e6},   # negative momentum → dropped
    }
    monkeypatch.setattr(c, "get_quote_symbols", lambda: list(fake.keys()))
    monkeypatch.setattr(c, "get_tickers", lambda syms: {s: fake[s] for s in syms if s in fake})

    out = c.get_top_momentum_symbols(n=10)

    assert out[:2] == settings.CORE_SYMBOLS        # core symbols first, always present
    assert "MOVER/USDT" in out
    assert "LOWVOL/USDT" not in out                # excluded by MIN_24H_QUOTE_VOLUME
    assert "FALLER/USDT" not in out                # excluded by change > 0 filter
