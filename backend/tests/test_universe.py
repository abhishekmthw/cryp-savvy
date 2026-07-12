"""Universe selection: BTC/ETH always eligible + 24h volume floor."""

import sys, os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.exchange.coindcx_client import CoinDCXClient
from config import settings


def _fake_universe(monkeypatch, c: CoinDCXClient, fake: dict) -> None:
    monkeypatch.setattr(c, "get_quote_symbols", lambda: list(fake.keys()))
    monkeypatch.setattr(c, "get_tickers", lambda syms: {s: fake[s] for s in syms if s in fake})


def test_universe_includes_core_and_applies_volume_floor(monkeypatch):
    c = CoinDCXClient()
    fake = {
        "BTC/USDT":    {"percentage": -1.0, "quoteVolume": 1e9},  # core, kept despite negative
        "ETH/USDT":    {"percentage":  0.5, "quoteVolume": 1e9},  # core
        "LOWVOL/USDT": {"percentage":  5.0, "quoteVolume": 100.0},  # below floor → dropped
        "MOVER/USDT":  {"percentage":  3.0, "quoteVolume": 5e6},   # liquid mover → kept
        "FALLER/USDT": {"percentage": -2.0, "quoteVolume": 5e6},   # negative momentum → dropped
    }
    _fake_universe(monkeypatch, c, fake)

    out = c.get_top_momentum_symbols(n=10)

    assert out[:2] == settings.CORE_SYMBOLS        # core symbols first, always present
    assert "MOVER/USDT" in out
    assert "LOWVOL/USDT" not in out                # excluded by MIN_24H_QUOTE_VOLUME
    assert "FALLER/USDT" not in out                # excluded by change > 0 filter


def test_universe_excludes_already_pumped_coins(monkeypatch):
    c = CoinDCXClient()
    fake = {
        "BTC/USDT":    {"percentage": 0.5, "quoteVolume": 1e9},
        "ETH/USDT":    {"percentage": 0.5, "quoteVolume": 1e9},
        "PUMP/USDT":   {"percentage": settings.MAX_24H_CHANGE_PCT + 20, "quoteVolume": 5e6},
        "STEADY/USDT": {"percentage": 5.0, "quoteVolume": 5e6},
    }
    _fake_universe(monkeypatch, c, fake)
    out = c.get_top_momentum_symbols(n=10)
    assert "PUMP/USDT" not in out       # anti-chase: already up too much in 24h
    assert "STEADY/USDT" in out


def test_universe_spread_filter(monkeypatch):
    c = CoinDCXClient()
    wide = 100 * settings.MAX_SPREAD_PCT * 4      # spread ≈ 4× the cap
    fake = {
        "BTC/USDT":  {"percentage": 0.5, "quoteVolume": 1e9},
        "ETH/USDT":  {"percentage": 0.5, "quoteVolume": 1e9},
        "WIDE/USDT": {"percentage": 3.0, "quoteVolume": 5e6,
                      "bid": 100.0, "ask": 100.0 + wide},
        "TIGHT/USDT": {"percentage": 3.0, "quoteVolume": 5e6,
                       "bid": 100.0, "ask": 100.05},
        "NOBOOK/USDT": {"percentage": 3.0, "quoteVolume": 5e6},  # no bid/ask → passes
    }
    _fake_universe(monkeypatch, c, fake)
    out = c.get_top_momentum_symbols(n=10)
    assert "WIDE/USDT" not in out
    assert "TIGHT/USDT" in out
    assert "NOBOOK/USDT" in out         # a data gap must not empty the universe


def test_universe_weights_volume_over_change(monkeypatch):
    # With MOMENTUM_CHANGE_WEIGHT=0.3 a liquid modest mover must outrank a
    # thin big mover (legacy 50/50 ranked the big mover first).
    c = CoinDCXClient()
    fake = {
        "BTC/USDT":    {"percentage": 0.5, "quoteVolume": 1e9},
        "ETH/USDT":    {"percentage": 0.5, "quoteVolume": 1e9},
        "LIQUID/USDT": {"percentage": 4.0, "quoteVolume": 5e8},
        "THIN/USDT":   {"percentage": 15.0, "quoteVolume": 2e6},
    }
    _fake_universe(monkeypatch, c, fake)
    out = c.get_top_momentum_symbols(n=1)
    momentum_picks = [s for s in out if s not in settings.CORE_SYMBOLS]
    assert momentum_picks == ["LIQUID/USDT"]
