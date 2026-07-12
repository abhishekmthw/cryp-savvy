"""
Tests for the paper-data wipe: the repository functions (count_live_orders,
clear_paper_data) and the DELETE /api/bot/paper-data endpoint flow — the
live-order guard, the stop → wipe → restart ordering, and the
wipe-succeeded-but-restart-failed warning path.
"""

import asyncio
import sys
import os
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# src.api.control imports src.db.engine, which builds the engine at import
# time and refuses to start without DATABASE_URL. The engine is never used
# here (session_scope is monkeypatched) and never connects — it just has to
# construct, and the pool kwargs it passes require a Postgres-style URL.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.api import control
from src.bot.errors import BotStartError
from src.db import repositories as repo
from src.db.models import (
    Allocation, Base, BucketState, Order, Position, Trade, UserBotConfig,
)


# ── Fixtures / seed helpers (plain db.add — the repo upserts are pg-only) ─────

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


_ID = [0]  # SQLite won't auto-increment a BigInteger PK — assign ids explicitly.


def _trade(db, uid="u1", **kw):
    _ID[0] += 1
    row = dict(id=_ID[0], user_id=uid, symbol="BTC/USDT", side="sell",
               pnl=1.0, ts=time.time())
    row.update(kw)
    db.add(Trade(**row))


def _position(db, uid="u1", symbol="ETH/USDT"):
    db.add(Position(user_id=uid, symbol=symbol, qty=1, entry_price=100.0,
                    entry_time=time.time(), amount_usdt=100.0,
                    stop_loss=95.0, take_profit=110.0))


def _order(db, uid="u1", mode="paper"):
    _ID[0] += 1
    db.add(Order(id=f"{uid}-o{_ID[0]}", user_id=uid, symbol="BTC/USDT",
                 side="buy", mode=mode))


def _bucket(db, uid="u1", bucket="day"):
    db.add(BucketState(user_id=uid, bucket=bucket,
                       realized_pnl=5.0, peak_equity=105.0))


def _seed_all(db, uid="u1"):
    _trade(db, uid)
    _position(db, uid)
    _order(db, uid, mode="paper")
    _bucket(db, uid)
    db.flush()


def _counts(db, uid):
    return {
        "trades": db.query(Trade).filter_by(user_id=uid).count(),
        "positions": db.query(Position).filter_by(user_id=uid).count(),
        "orders": db.query(Order).filter_by(user_id=uid).count(),
        "bucket_states": db.query(BucketState).filter_by(user_id=uid).count(),
    }


# ── Repository level ──────────────────────────────────────────────────────────

def test_clear_wipes_only_target_user(db):
    _seed_all(db, "u1")
    _seed_all(db, "u2")

    deleted = repo.clear_paper_data(db, "u1")

    assert deleted == {"trades": 1, "positions": 1, "orders": 1, "bucket_states": 1}
    assert _counts(db, "u1") == {"trades": 0, "positions": 0, "orders": 0, "bucket_states": 0}
    assert _counts(db, "u2") == {"trades": 1, "positions": 1, "orders": 1, "bucket_states": 1}


def test_clear_keeps_live_orders(db):
    _order(db, "u1", mode="paper")
    _order(db, "u1", mode="live")
    db.flush()

    deleted = repo.clear_paper_data(db, "u1")

    assert deleted["orders"] == 1
    remaining = db.query(Order).filter_by(user_id="u1").all()
    assert [o.mode for o in remaining] == ["live"]


def test_clear_keeps_allocation_and_config(db):
    _seed_all(db, "u1")
    db.add(Allocation(user_id="u1", total_allocated=1000.0,
                      day_budget=300.0, long_budget=700.0))
    db.add(UserBotConfig(user_id="u1", initial_capital_usdt=1000.0,
                         max_position_usdt=100.0, max_open_positions=5,
                         stop_loss_pct=0.05, take_profit_pct=0.1,
                         trailing_stop_trigger=0.05, trailing_stop_offset=0.02,
                         daily_loss_limit_usdt=50.0))
    db.flush()

    repo.clear_paper_data(db, "u1")

    assert db.get(Allocation, "u1") is not None
    assert db.get(UserBotConfig, "u1") is not None


def test_clear_empty_user_returns_zero_counts(db):
    assert repo.clear_paper_data(db, "ghost") == {
        "trades": 0, "positions": 0, "orders": 0, "bucket_states": 0,
    }


def test_count_live_orders(db):
    assert repo.count_live_orders(db, "u1") == 0
    _order(db, "u1", mode="paper")
    db.flush()
    assert repo.count_live_orders(db, "u1") == 0
    _order(db, "u1", mode="live")
    _order(db, "u1", mode="live")
    _order(db, "u2", mode="live")
    db.flush()
    assert repo.count_live_orders(db, "u1") == 2


# ── Endpoint flow (coroutine called directly; session_scope monkeypatched) ────

class FakeOrch:
    def __init__(self, running=False, start_result=True, start_exc=None):
        self.running = running
        self.start_result = start_result
        self.start_exc = start_exc
        self.calls = []
        self.on_start = None  # hook to observe DB state when restart happens

    def is_running(self, user_id):
        self.calls.append("is_running")
        return self.running

    def stop(self, user_id):
        self.calls.append("stop")
        self.running = False

    def start(self, user_id):
        self.calls.append("start")
        if self.on_start:
            self.on_start()
        if self.start_exc:
            raise self.start_exc
        self.running = self.start_result
        return self.start_result


def _call_endpoint(db, monkeypatch, orch):
    @contextmanager
    def fake_scope():
        yield db

    monkeypatch.setattr(control, "session_scope", fake_scope)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(orchestrator=orch)))
    user = SimpleNamespace(clerk_user_id="u1")
    return asyncio.run(control.clear_paper_data(request, user))


def test_endpoint_refuses_when_live_orders_exist(db, monkeypatch):
    _seed_all(db, "u1")
    _order(db, "u1", mode="live")
    db.flush()
    orch = FakeOrch(running=True)

    with pytest.raises(HTTPException) as exc:
        _call_endpoint(db, monkeypatch, orch)

    assert exc.value.status_code == 409
    assert orch.calls == []  # bot never touched
    assert _counts(db, "u1")["trades"] == 1  # nothing deleted


def test_endpoint_stop_wipe_restart_order(db, monkeypatch):
    _seed_all(db, "u1")
    orch = FakeOrch(running=True)
    trades_at_restart = []
    orch.on_start = lambda: trades_at_restart.append(db.query(Trade).count())

    result = _call_endpoint(db, monkeypatch, orch)

    assert orch.calls == ["is_running", "stop", "start"]
    assert trades_at_restart == [0]  # wipe completed before the restart
    assert result["ok"] is True
    assert result["was_running"] is True
    assert result["bot_restarted"] is True
    assert result["warning"] is None
    assert result["deleted"] == {"trades": 1, "positions": 1, "orders": 1, "bucket_states": 1}
    assert _counts(db, "u1") == {"trades": 0, "positions": 0, "orders": 0, "bucket_states": 0}


def test_endpoint_not_running_skips_lifecycle(db, monkeypatch):
    _seed_all(db, "u1")
    orch = FakeOrch(running=False)

    result = _call_endpoint(db, monkeypatch, orch)

    assert orch.calls == ["is_running"]
    assert result["was_running"] is False
    assert result["bot_restarted"] is False
    assert result["warning"] is None
    assert _counts(db, "u1")["trades"] == 0


def test_endpoint_restart_failure_still_reports_wipe(db, monkeypatch):
    _seed_all(db, "u1")
    orch = FakeOrch(running=True, start_exc=BotStartError("decrypt failed"))

    result = _call_endpoint(db, monkeypatch, orch)

    assert result["ok"] is True
    assert result["bot_restarted"] is False
    assert "could not restart" in result["warning"]
    assert "decrypt failed" in result["warning"]
    assert _counts(db, "u1") == {"trades": 0, "positions": 0, "orders": 0, "bucket_states": 0}
