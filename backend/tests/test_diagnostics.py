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
