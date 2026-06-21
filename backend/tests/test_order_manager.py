"""
Tests for OrderManager — the live/paper sync contract.

Regression target: the prior bug where a LIVE buy placed an exchange order but
never recorded a position in the paper book, so it could never be exited.
No network or DB access — a fake live client and a fake order store are used.
"""

import sys, os
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.bot.config import BotConfig
from src.exchange.paper_trader import PaperTrader
from src.trading.order_manager import OrderManager


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeStore:
    def __init__(self):
        self.orders = {}

    def create_order(self, *, client_order_id, symbol, side, mode, quote_currency, **kw):
        self.orders[client_order_id] = {
            "status": "pending", "symbol": symbol, "side": side, "mode": mode, **kw,
        }

    def update_order(self, client_order_id, **fields):
        self.orders.setdefault(client_order_id, {}).update(fields)

    def only(self):
        assert len(self.orders) == 1
        return next(iter(self.orders.values()))


class FakeLiveClient:
    has_keys = True

    def __init__(self, buy_fill=None, sell_fill=None, status_fill=None, raise_exc=None):
        self.buy_fill = buy_fill
        self.sell_fill = sell_fill
        self.status_fill = status_fill
        self.raise_exc = raise_exc
        self.buys = 0
        self.sells = 0

    def place_market_buy(self, symbol, amount, client_order_id=None):
        self.buys += 1
        if self.raise_exc:
            raise self.raise_exc
        return self.buy_fill

    def place_market_sell(self, symbol, qty, client_order_id=None):
        self.sells += 1
        if self.raise_exc:
            raise self.raise_exc
        return self.sell_fill

    def fetch_order_status(self, exchange_order_id):
        return self.status_fill


def _fill(price, qty, confirmed=True, oid="ex1"):
    return {"exchange_order_id": oid, "status": "filled",
            "fill_price": price, "fill_qty": qty, "confirmed": confirmed}


@pytest.fixture
def paper():
    t = PaperTrader(BotConfig.defaults())
    t.balance_usdt = 10_000.0
    return t


# ── Paper mode ────────────────────────────────────────────────────────────────

def test_paper_buy_books_position_and_logs_filled(paper):
    store = FakeStore()
    om = OrderManager(paper, mode="paper", user_id="u", order_store=store)
    order = om.buy("BTC/INR", 2_000, current_price=100)
    assert order is not None
    assert "BTC/INR" in paper.positions
    assert store.only()["status"] == "filled"


def test_paper_sell_closes_and_logs(paper):
    store = FakeStore()
    om = OrderManager(paper, mode="paper", user_id="u", order_store=store)
    om.buy("BTC/INR", 2_000, current_price=100)
    trade = om.sell("BTC/INR", 110, reason="signal")
    assert trade is not None
    assert "BTC/INR" not in paper.positions


# ── Live mode: the regression that this whole phase exists for ────────────────

def test_live_buy_records_position_from_actual_fill(paper):
    store = FakeStore()
    live = FakeLiveClient(buy_fill=_fill(price=105.0, qty=0.5))
    om = OrderManager(paper, mode="live", live_client=live, user_id="u", order_store=store)

    order = om.buy("BTC/INR", 2_000, current_price=100)

    assert order is not None
    # THE FIX: a live buy must create a tracked position
    assert "BTC/INR" in paper.positions
    pos = paper.positions["BTC/INR"]
    assert pos.entry_price == 105.0      # actual fill price, not the pre-trade estimate
    assert pos.qty == 0.5
    assert store.only()["status"] == "filled"
    assert store.only()["exchange_order_id"] == "ex1"


def test_live_buy_timeout_does_not_book_position(paper):
    store = FakeStore()
    live = FakeLiveClient(raise_exc=requests.Timeout())
    om = OrderManager(paper, mode="live", live_client=live, user_id="u", order_store=store)

    order = om.buy("BTC/INR", 2_000, current_price=100)

    assert order is None
    assert "BTC/INR" not in paper.positions          # never guess on an ambiguous timeout
    assert store.only()["status"] == "unconfirmed"


def test_live_buy_reconciles_when_create_unconfirmed(paper):
    store = FakeStore()
    live = FakeLiveClient(
        buy_fill=_fill(price=None, qty=None, confirmed=False, oid="ex9"),
        status_fill=_fill(price=107.0, qty=0.4, confirmed=True, oid="ex9"),
    )
    om = OrderManager(paper, mode="live", live_client=live, user_id="u", order_store=store)

    om.buy("BTC/INR", 2_000, current_price=100)

    pos = paper.positions["BTC/INR"]
    assert pos.entry_price == 107.0      # filled in via fetch_order_status
    assert store.only()["status"] == "filled"


def test_live_sell_partial_fill_keeps_remainder(paper):
    store = FakeStore()
    paper.place_market_buy("BTC/INR", 1_000, current_price=100, fill_qty=10)  # qty = 10
    live = FakeLiveClient(sell_fill=_fill(price=110.0, qty=4.0, oid="exs"))
    om = OrderManager(paper, mode="live", live_client=live, user_id="u", order_store=store)

    trade = om.sell("BTC/INR", 100, reason="signal")

    assert trade["qty"] == 4.0
    assert "BTC/INR" in paper.positions                 # remainder stays open
    assert paper.positions["BTC/INR"].qty == pytest.approx(6.0)


def test_live_sell_failure_keeps_position(paper):
    store = FakeStore()
    paper.place_market_buy("BTC/INR", 1_000, current_price=100, fill_qty=10)
    live = FakeLiveClient(raise_exc=ValueError("exchange rejected"))
    om = OrderManager(paper, mode="live", live_client=live, user_id="u", order_store=store)

    trade = om.sell("BTC/INR", 100, reason="signal")

    assert trade is None
    assert "BTC/INR" in paper.positions                 # not ghost-closed
    assert store.only()["status"] == "failed"
