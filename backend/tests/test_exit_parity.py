"""
Gate-fidelity contract: the live PaperTrader and the backtest engine must make
IDENTICAL exit decisions for the same price path, in both trailing modes.
Both call strategies.trail_stop / strategies.atr_stops, so this test pins the
shared-helper wiring on each side (same exit step, reason, and stop level).
"""

import sys, os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings
from src.analysis import strategies
from src.bot.config import BotConfig
from src.exchange.paper_trader import PaperTrader

ENTRY, ATR, BUCKET = 100.0, 2.0, "day"
# 2×ATR stop = 96 (4% — inside the 5% cap), 3×ATR take = 106.


def _paper_run(prices):
    """Drive PaperTrader.check_exit_conditions along the path; return the
    (step, reason, stop_at_exit) of the first exit."""
    t = PaperTrader(BotConfig.defaults())
    stop, take = strategies.atr_stops(ENTRY, ATR, BUCKET)
    t.restore_position({
        "symbol": "X/USDT", "qty": 1.0, "entry_price": ENTRY, "entry_time": 1.0,
        "amount_usdt": ENTRY, "stop_loss": stop, "take_profit": take,
        "trailing_high": ENTRY,
    })
    for i, p in enumerate(prices):
        reason = t.check_exit_conditions("X/USDT", p)
        if reason:
            return i, reason, t.positions["X/USDT"].stop_loss
    return None, None, t.positions["X/USDT"].stop_loss


def _engine_run(prices):
    """Replicate the engine's per-bar exit mechanics (intrabar SL/TP against
    the bar, trailing ratchet applies from the next bar) on 1-price bars."""
    stop, take = strategies.atr_stops(ENTRY, ATR, BUCKET)
    trail_high = ENTRY
    for i, p in enumerate(prices):
        if p <= stop:
            return i, "stop_loss", stop
        if p >= take:
            return i, "take_profit", stop
        hi = max(trail_high, p)
        candidate = strategies.trail_stop(ENTRY, take, hi, BUCKET,
                                          settings.TRAILING_STOP_TRIGGER,
                                          settings.TRAILING_STOP_OFFSET)
        if candidate is not None:
            stop = max(stop, candidate)
        trail_high = hi
    return None, None, stop


PATHS = {
    "trailed_stopout": [100, 102, 105, 103, 100.5],   # arm → pull back into trail
    "take_profit":     [100, 102, 105, 106.5],        # arm → run to target
    "initial_stopout": [100, 98, 95.5],               # straight into the entry stop
    "never_exits":     [100, 101, 102, 101, 102],
}


@pytest.mark.parametrize("mode", ["atr_r", "fixed_pct"])
@pytest.mark.parametrize("path", list(PATHS))
def test_paper_and_engine_exit_identically(monkeypatch, mode, path):
    monkeypatch.setattr(settings, "TRAILING_MODE", mode)
    prices = PATHS[path]
    paper = _paper_run(prices)
    engine = _engine_run(prices)
    assert paper[0] == engine[0]                      # same exit bar (or None)
    assert paper[1] == engine[1]                      # same reason
    if paper[1] != "take_profit":
        # The stop level decides stop exits; on a TP exit it's irrelevant (the
        # paper trader ratchets the trail on the exit tick, the engine doesn't).
        assert paper[2] == pytest.approx(engine[2])


def test_atr_r_mode_arms_at_breakeven(monkeypatch):
    # With TRAIL_ARM_R=1.0 and trail mult == SL mult, the stop must sit exactly
    # at entry (breakeven) the moment the trail arms at +1R.
    monkeypatch.setattr(settings, "TRAILING_MODE", "atr_r")
    r = settings.ATR_SL_MULT_DAY * ATR                # 1R = 4.0
    _, take = strategies.atr_stops(ENTRY, ATR, BUCKET)
    candidate = strategies.trail_stop(ENTRY, take, ENTRY + r, BUCKET, 0.03, 0.02)
    assert candidate == pytest.approx(ENTRY)


def test_fixed_mode_matches_legacy_formula(monkeypatch):
    monkeypatch.setattr(settings, "TRAILING_MODE", "fixed_pct")
    _, take = strategies.atr_stops(ENTRY, ATR, BUCKET)
    high = ENTRY * 1.05                               # +5% ≥ 3% trigger
    candidate = strategies.trail_stop(ENTRY, take, high, BUCKET, 0.03, 0.02)
    assert candidate == pytest.approx(high * 0.98)    # bit-identical to July
    # Below the trigger the trail stays unarmed.
    assert strategies.trail_stop(ENTRY, take, ENTRY * 1.02, BUCKET, 0.03, 0.02) is None
