"""
Tests for restart-recovery + partial-fill bookkeeping in PaperTrader, and the
bounded event queue in UserBotState.
"""

import sys, os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings
from src.bot.config import BotConfig
from src.exchange.paper_trader import PaperTrader, _utc_day_start
from src.api.state import UserBotState


@pytest.fixture
def trader():
    t = PaperTrader(BotConfig.defaults())
    t.balance_usdt = 10_000.0
    return t


# ── Partial-fill sells ────────────────────────────────────────────────────────

def test_partial_sell_keeps_remainder(trader):
    trader.place_market_buy("BTC/INR", 1_000, current_price=100, fill_qty=10)  # qty 10
    trade = trader.place_market_sell("BTC/INR", 120, fill_qty=4.0)
    assert trade["qty"] == 4.0
    assert trade["pnl"] == pytest.approx(4.0 * (120 - 100))
    pos = trader.positions["BTC/INR"]
    assert pos.qty == pytest.approx(6.0)
    assert pos.amount_usdt == pytest.approx(600.0)


def test_full_sell_closes(trader):
    trader.place_market_buy("BTC/INR", 1_000, current_price=100)
    trader.place_market_sell("BTC/INR", 120)
    assert "BTC/INR" not in trader.positions


# ── Live fill price/qty override ──────────────────────────────────────────────

def test_buy_uses_explicit_fill_price_and_qty(trader):
    pos = trader.place_market_buy("ETH/INR", 2_000, current_price=100,
                                  fill_price=105.0, fill_qty=0.5)
    assert pos.entry_price == 105.0
    assert pos.qty == 0.5
    assert pos.amount_usdt == pytest.approx(52.5)


# ── Restart recovery ──────────────────────────────────────────────────────────

def test_restore_position_and_daily_pnl():
    t = PaperTrader(BotConfig.defaults())
    t.restore_position({
        "symbol": "BTC/INR", "qty": 0.1, "entry_price": 5000.0,
        "entry_time": 1.0, "amount_usdt": 500.0, "stop_loss": 4850.0,
        "take_profit": 5300.0, "trailing_high": 5000.0, "order_id": "abc",
    })
    assert "BTC/INR" in t.positions
    assert t.positions["BTC/INR"].order_id == "abc"

    limit = settings.DAILY_LOSS_LIMIT_USDT
    t.restore_daily_pnl(-limit * 0.5)
    assert t.daily_pnl == -limit * 0.5
    assert not t.is_daily_limit_hit      # below the limit
    t.restore_daily_pnl(-limit * 1.5)
    assert t.is_daily_limit_hit          # circuit-breaker survives a restart


def test_daily_window_resets_on_new_utc_day(trader):
    trader._daily_pnl = -500.0
    trader._day_start = _utc_day_start() - 86_400 * 2   # pretend last activity was 2 days ago
    assert trader.daily_pnl == 0.0       # rolled into a new day


# ── Bounded event queue ───────────────────────────────────────────────────────

def test_event_queue_is_bounded_and_keeps_newest():
    s = UserBotState(user_id="u")
    for i in range(600):
        s.push_event("tick", {"i": i})
    assert s.event_queue.qsize() <= 500
    # the most recent event must still be present (oldest dropped, not newest)
    drained = []
    while not s.event_queue.empty():
        drained.append(s.event_queue.get_nowait()["data"]["i"])
    assert 599 in drained
    assert max(drained) == 599


def test_drain_queue_empties():
    s = UserBotState(user_id="u")
    for i in range(10):
        s.push_event("tick", {"i": i})
    s.drain_queue()
    assert s.event_queue.empty()
