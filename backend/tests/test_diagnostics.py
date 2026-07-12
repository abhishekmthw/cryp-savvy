"""
Tests for trade diagnostics (loss-attribution analytics) and the entry-
attribution instrumentation (strategy/regime/entry_score) threaded from a buy
through to the closed-trade record and the persisted-position round-trip.
"""

import sys
import os
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.bot.config import BotConfig
from src.db.models import Base, Trade
from src.db import repositories as repo
from src.exchange.paper_trader import PaperTrader


# ── DB fixture (in-memory SQLite; diagnostics uses only portable SELECTs) ─────

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


_ID = [0]  # SQLite won't auto-increment a BigInteger PK — assign ids explicitly.


def _add(db, **kw):
    _ID[0] += 1
    row = dict(id=_ID[0], user_id="u1", symbol="BTC/USDT", side="sell", ts=time.time())
    row.update(kw)
    db.add(Trade(**row))


# ── trade_diagnostics ─────────────────────────────────────────────────────────

def test_diagnostics_empty(db):
    assert repo.trade_diagnostics(db, "u1") == {"total_trades": 0}


def test_diagnostics_edge_and_breakdowns(db):
    # 2 winners (+30, take_profit, long/trend) and 3 losers (-10, stop_loss, day/rsi)
    for _ in range(2):
        _add(db, pnl=30, pnl_pct=3.0, reason="take_profit", bucket="long",
             strategy="trend_following", regime="bull",
             amount_usdt=1000, duration_s=7200)
    for _ in range(3):
        _add(db, pnl=-10, pnl_pct=-1.0, reason="stop_loss", bucket="day",
             strategy="rsi_mean_reversion", regime="sideways",
             amount_usdt=1000, duration_s=3600)
    db.flush()

    d = repo.trade_diagnostics(db, "u1", initial_capital=1000)
    assert d["total_trades"] == 5

    e = d["edge"]
    assert e["win_rate"] == 40.0            # 2/5
    assert e["total_pnl_usdt"] == 30.0      # +60 − 30
    assert e["profit_factor"] == 2.0        # 60/30
    assert e["avg_win_usdt"] == 30.0
    assert e["avg_loss_usdt"] == -10.0
    assert e["payoff_ratio"] == 3.0         # 30/10
    assert e["breakeven_win_rate"] == 25.0  # 1/(1+3)
    assert e["expectancy_usdt"] == 6.0      # 30/5

    # by_reason: worst bleeder first, stop_loss is 0% win
    assert d["by_reason"][0]["key"] == "stop_loss"
    by_reason = {r["key"]: r for r in d["by_reason"]}
    assert by_reason["stop_loss"]["total_pnl"] == -30.0
    assert by_reason["stop_loss"]["win_rate"] == 0.0
    assert by_reason["take_profit"]["total_pnl"] == 60.0

    # by_bucket populated (fully attributed)
    assert d["coverage"]["attributed_trades"] == 5
    by_bucket = {r["key"]: r for r in d["by_bucket"]}
    assert by_bucket["day"]["total_pnl"] == -30.0
    assert by_bucket["long"]["total_pnl"] == 60.0

    # hold-time: winners 2h, losers 1h
    assert d["duration"]["avg_win_hours"] == 2.0
    assert d["duration"]["avg_loss_hours"] == 1.0

    # fee-drag estimate is populated
    assert d["fees"]["est_total_cost_usdt"] > 0


def test_diagnostics_unattributed_historical(db):
    # Pre-instrumentation trades have NULL bucket/strategy/regime → 'unknown'.
    _add(db, pnl=-5, pnl_pct=-0.5, reason="stop_loss", amount_usdt=500)
    db.flush()
    d = repo.trade_diagnostics(db, "u1")
    assert d["coverage"]["unattributed_trades"] == 1
    assert d["coverage"]["attributed_trades"] == 0
    assert d["by_strategy"][0]["key"] == "unknown"


# ── entry-attribution instrumentation (no DB) ─────────────────────────────────

def test_buy_records_entry_attribution():
    t = PaperTrader(BotConfig.defaults())
    t.balance_usdt = 10_000
    pos = t.place_market_buy("BTC/USDT", 1_000, current_price=100,
                             strategy="donchian_breakout", regime="bull",
                             entry_score=72.5)
    assert (pos.strategy, pos.regime, pos.entry_score) == ("donchian_breakout", "bull", 72.5)

    trade = t.place_market_sell("BTC/USDT", 120, reason="take_profit")
    assert trade["strategy"] == "donchian_breakout"
    assert trade["regime"] == "bull"
    assert trade["entry_score"] == 72.5
    assert trade["reason"] == "take_profit"


def test_position_as_dict_round_trips_attribution():
    t = PaperTrader(BotConfig.defaults())
    t.balance_usdt = 10_000
    t.place_market_buy("ETH/USDT", 1_000, current_price=100,
                       strategy="trend_following", regime="bull", entry_score=64.0)
    snap = t.position_as_dict("ETH/USDT")
    assert (snap["strategy"], snap["regime"], snap["entry_score"]) == ("trend_following", "bull", 64.0)

    t2 = PaperTrader(BotConfig.defaults())
    t2.restore_position(snap)
    p = t2.positions["ETH/USDT"]
    assert (p.strategy, p.regime, p.entry_score) == ("trend_following", "bull", 64.0)


# ── Diagnostics v2: watermarks, planned stops, fees (no DB) ───────────────────

def test_watermarks_and_planned_stops_captured():
    t = PaperTrader(BotConfig.defaults())
    t.balance_usdt = 10_000
    pos = t.place_market_buy("BTC/USDT", 1_000, current_price=100,
                             scores={"ema": 25, "composite": 66.0})
    entry = pos.entry_price
    planned_sl, planned_tp = pos.planned_stop_loss, pos.planned_take_profit
    assert planned_sl == pos.stop_loss and planned_tp == pos.take_profit
    assert pos.scores == {"ema": 25, "composite": 66.0}

    # Fast-loop price touches advance the excursion watermarks.
    for p in (108.0, 95.0, 103.0):
        t.check_exit_conditions("BTC/USDT", p)
    assert pos.high_water == 108.0
    assert pos.low_water == 95.0

    # Simulate a trailing ratchet — the PLANNED stop must not move.
    pos.stop_loss = entry * 1.01
    trade = t.place_market_sell("BTC/USDT", 103.0, reason="sell_signal")
    assert trade["planned_stop_loss"] == pytest.approx(planned_sl)
    assert trade["planned_take_profit"] == pytest.approx(planned_tp)
    assert trade["mfe_pct"] == pytest.approx((108.0 / entry - 1) * 100)
    assert trade["mae_pct"] == pytest.approx((95.0 / entry - 1) * 100)
    assert trade["entry_ts"] == pos.entry_time
    assert trade["scores"] == {"ema": 25, "composite": 66.0}


def test_paper_fees_recorded_live_fees_null():
    from config import settings as s
    t = PaperTrader(BotConfig.defaults())
    t.balance_usdt = 10_000

    # Paper: modeled entry+exit fee/slippage recorded on the trade.
    pos = t.place_market_buy("BTC/USDT", 1_000, current_price=100)
    spend = pos.amount_usdt
    assert pos.entry_fee_usdt == pytest.approx(spend * s.FEE_PCT)
    trade = t.place_market_sell("BTC/USDT", 110)
    expected_exit_fee = trade["qty"] * trade["exit_price"] * s.FEE_PCT
    assert trade["fee_usdt"] == pytest.approx(pos.entry_fee_usdt + expected_exit_fee)
    assert trade["slippage_usdt"] > 0

    # Live-style fills are already net of real fees → costs stay unknown.
    t.place_market_buy("ETH/USDT", 1_000, current_price=100,
                       fill_price=100.0, fill_qty=2.0)
    assert t.positions["ETH/USDT"].entry_fee_usdt is None
    live_trade = t.place_market_sell("ETH/USDT", 105, fill_qty=2.0)
    assert live_trade["fee_usdt"] is None
    assert live_trade["slippage_usdt"] is None


def test_position_round_trips_v2_fields():
    t = PaperTrader(BotConfig.defaults())
    t.balance_usdt = 10_000
    t.place_market_buy("SOL/USDT", 1_000, current_price=100, atr=1.5,
                       scores={"rsi": 25})
    t.check_exit_conditions("SOL/USDT", 104.0)   # move the watermarks
    snap = t.position_as_dict("SOL/USDT")

    t2 = PaperTrader(BotConfig.defaults())
    t2.restore_position(snap)
    p, q = t.positions["SOL/USDT"], t2.positions["SOL/USDT"]
    assert q.high_water == p.high_water
    assert q.low_water == p.low_water
    assert q.planned_stop_loss == p.planned_stop_loss
    assert q.planned_take_profit == p.planned_take_profit
    assert q.entry_fee_usdt == pytest.approx(p.entry_fee_usdt)
    assert q.entry_slippage_usdt == pytest.approx(p.entry_slippage_usdt)
    assert q.scores == {"rsi": 25}


# ── Diagnostics v2: aggregations over instrumented rows ──────────────────────

def test_diagnostics_v2_sections(db):
    now = time.time()
    # Winner: 2% planned risk, 3% planned reward (1.5 R:R), realized +3% = +1.5R.
    _add(db, pnl=30, pnl_pct=3.0, reason="take_profit", bucket="day",
         strategy="donchian_breakout", regime="bull", amount_usdt=1000,
         duration_s=3600, ts=now - 7200, entry_ts=now - 10_800,
         entry_price=100.0, planned_stop_loss=98.0, planned_take_profit=103.0,
         mae_pct=-0.5, mfe_pct=3.5, fee_usdt=2.1, slippage_usdt=1.05,
         scores={"composite": 70.0})
    # Loser: re-entered the same symbol 1h after the winner's exit; was +1.5%
    # in profit (≥1% and ≥50% of the 3% target) before losing the full 1R.
    _add(db, pnl=-20, pnl_pct=-2.0, reason="stop_loss", bucket="day",
         strategy="donchian_breakout", regime="bull", amount_usdt=1000,
         duration_s=3600, ts=now, entry_ts=now - 3600,
         entry_price=100.0, planned_stop_loss=98.0, planned_take_profit=103.0,
         mae_pct=-2.2, mfe_pct=1.5, fee_usdt=2.0, slippage_usdt=1.0)
    # Legacy row: no v2 columns → excluded from v2 sections, kept in edge.
    # Different symbol + old timestamp so it can't register as churn.
    _add(db, symbol="OLD/USDT", pnl=-5, pnl_pct=-0.5, reason="stop_loss",
         amount_usdt=500, duration_s=1800, ts=now - 86_400 * 5)
    db.flush()

    d = repo.trade_diagnostics(db, "u1", initial_capital=1000)
    assert d["total_trades"] == 3

    rr = d["rr"]
    assert rr["coverage"] == 2
    assert rr["avg_planned_rr"] == pytest.approx(1.5)
    assert rr["avg_realized_r"] == pytest.approx((1.5 - 1.0) / 2)
    assert rr["stop_overshoot_pct"] == 0.0        # -2.0% within the 2% plan

    mm = d["mae_mfe"]
    assert mm["coverage"] == 2
    assert mm["losers_profitable_1pct"] == 100.0  # the one loser peaked at +1.5%
    assert mm["losers_reached_half_tp"] == 100.0  # 1.5% ≥ half of the 3% target
    assert mm["avg_mfe_winners_pct"] == pytest.approx(3.5)

    fees = d["fees"]
    assert fees["trades_with_fee_data"] == 2
    assert fees["actual_fee_usdt"] == pytest.approx(4.1)
    assert fees["actual_total_cost_usdt"] == pytest.approx(4.1 + 2.05)

    churn = d["churn"]
    assert churn["reentries_within_window"] == 1  # loser re-entered 1h after exit
    assert churn["top_reentered"][0]["symbol"] == "BTC/USDT"

    assert "sharpe_daily_ann" in d["risk"]
    assert d["by_hour"]                            # hour-of-day breakdown exists
    assert d["coverage"]["instrumented_trades"] == 2

    # v1 keys keep working with mixed legacy/instrumented rows.
    assert d["edge"]["total_pnl_usdt"] == pytest.approx(5.0)
    assert {g["key"] for g in d["by_reason"]} == {"take_profit", "stop_loss"}
