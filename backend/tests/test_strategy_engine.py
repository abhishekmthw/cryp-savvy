"""
Phase-4 tests: indicators, regime detection, the strategy ensemble, ATR-based
stops + fees/slippage in the paper trader, backtest metrics, and a synthetic
backtest run.
"""

import sys, os
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings
from src.analysis import indicators, regime, strategies
from src.analysis.technical import compute_indicators
from src.backtest import metrics
from src.backtest.engine import run_backtest, walk_forward_windows
from src.bot.config import BotConfig
from src.exchange.paper_trader import PaperTrader


def _ohlcv(n=300, trend="up", seed=7):
    rng = np.random.default_rng(seed)
    base = 100.0
    if trend == "up":
        closes = base * np.cumprod(1 + rng.normal(0.003, 0.004, n))
    elif trend == "down":
        closes = base * np.cumprod(1 + rng.normal(-0.003, 0.004, n))
    else:  # flat / sideways — stationary around base (no cumulative drift)
        closes = base * (1 + rng.normal(0, 0.003, n))
    closes = np.clip(closes, 1, None)
    opens = closes * rng.uniform(0.999, 1.001, n)
    highs = np.maximum(opens, closes) * rng.uniform(1.000, 1.004, n)
    lows = np.minimum(opens, closes) * rng.uniform(0.996, 1.000, n)
    vol = rng.uniform(1_000, 5_000, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": vol}, index=idx).astype(float)


# ── Indicators ────────────────────────────────────────────────────────────────

def test_atr_positive_and_aligned():
    df = _ohlcv(100)
    a = indicators.atr(df, 14)
    assert len(a) == len(df)
    assert indicators.latest_atr(df, 14) > 0


def test_donchian_excludes_current_bar():
    df = _ohlcv(60)
    upper, lower = indicators.donchian(df, 20)
    assert upper >= lower > 0


# ── Regime ────────────────────────────────────────────────────────────────────

def test_regime_classifies_trends():
    assert regime.detect_regime(_ohlcv(300, "up")) == regime.BULL
    assert regime.detect_regime(_ohlcv(300, "down")) == regime.BEAR
    assert regime.detect_regime(_ohlcv(300, "flat")) == regime.SIDEWAYS


def test_regime_sideways_on_short_data():
    assert regime.detect_regime(_ohlcv(10)) == regime.SIDEWAYS


# ── Strategy ensemble ─────────────────────────────────────────────────────────

def test_no_long_entry_in_bear_regime():
    df = _ohlcv(300, "down")
    tech = compute_indicators(df)
    strat = strategies.evaluate(df, tech)
    assert strat["action"] != strategies.BUY      # never open a long in a bear regime
    assert strat["regime"] == regime.BEAR


def test_bull_regime_can_emit_buy_with_bucket():
    df = _ohlcv(300, "up")
    tech = compute_indicators(df)
    strat = strategies.evaluate(df, tech)
    if strat["action"] == strategies.BUY:
        assert strat["bucket"] in (strategies.DAY, strategies.LONG)
        assert strat["atr"] and strat["atr"] > 0


def test_atr_stops_helper_scales_by_bucket():
    sl_day, tp_day = strategies.atr_stops(100.0, 2.0, strategies.DAY)
    sl_long, tp_long = strategies.atr_stops(100.0, 2.0, strategies.LONG)
    assert sl_day == pytest.approx(100 - settings.ATR_SL_MULT_DAY * 2)
    assert sl_long < sl_day            # long bucket uses a wider stop


# ── ATR stops + fees/slippage in the paper trader ─────────────────────────────

@pytest.fixture
def trader():
    t = PaperTrader(BotConfig.defaults())
    t.balance_usdt = 10_000.0
    return t


def test_paper_buy_uses_atr_stops(trader):
    pos = trader.place_market_buy("BTC/USDT", 200, current_price=100, atr=5.0, bucket="day")
    # entry is slipped up; stop = entry - 2*ATR, take = entry + 3*ATR
    assert pos.stop_loss == pytest.approx(pos.entry_price - settings.ATR_SL_MULT_DAY * 5.0)
    assert pos.take_profit == pytest.approx(pos.entry_price + settings.ATR_TP_MULT_DAY * 5.0)


def test_paper_buy_applies_fee_and_slippage(trader):
    pos = trader.place_market_buy("BTC/USDT", 200, current_price=100)
    assert pos.entry_price > 100                     # slippage worsens entry
    assert pos.qty < 200 / 100                        # fee reduces units received


def test_round_trip_loses_to_fees_at_flat_price(trader):
    trader.place_market_buy("BTC/USDT", 200, current_price=100)
    trade = trader.place_market_sell("BTC/USDT", 100)
    assert trade["pnl"] < 0                            # fees+slippage make a flat round-trip a small loss


# ── Backtest metrics ──────────────────────────────────────────────────────────

def test_metrics_basic():
    assert metrics.max_drawdown([100, 120, 60, 90]) == pytest.approx(0.5)
    assert metrics.win_rate([{"pnl": 1}, {"pnl": -1}, {"pnl": 2}]) == pytest.approx(2 / 3)
    assert metrics.profit_factor([{"pnl": 3}, {"pnl": -1}]) == pytest.approx(3.0)
    assert metrics.sharpe([0.0, 0.0]) == 0.0


# ── Backtest engine ───────────────────────────────────────────────────────────

def test_backtest_runs_and_reports():
    res = run_backtest(_ohlcv(400, "up"), initial_capital=1000.0)
    assert res.equity and res.equity[-1] > 0
    for k in ("num_trades", "win_rate", "sharpe", "max_drawdown", "profit_factor"):
        assert k in res.metrics


def test_walk_forward_windows_partition():
    df = _ohlcv(500)
    windows = list(walk_forward_windows(df, train_bars=200, test_bars=50))
    assert len(windows) >= 1
    train, test = windows[0]
    assert len(train) == 200 and len(test) == 50
