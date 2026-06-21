"""
Phase-5 tests: AllocationManager (bucket isolation, compounding, drawdown
breakers) and RiskManager bucket-aware gating/sizing.
"""

import sys, os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings
from src.bot.config import BotConfig
from src.exchange.paper_trader import PaperTrader
from src.trading.allocation import AllocationManager, DAY, LONG
from src.trading.risk_manager import RiskManager


# ── AllocationManager ─────────────────────────────────────────────────────────

def test_buckets_are_isolated():
    a = AllocationManager.from_budgets(day_budget=300, long_budget=700)
    assert a.can_open(DAY, size=300, deployed=0) is True
    assert a.can_open(DAY, size=301, deployed=0) is False     # can't exceed day budget
    assert a.can_open(LONG, size=700, deployed=0) is True
    # a day-bucket can't borrow the long bucket's headroom
    assert a.can_open(DAY, size=400, deployed=0) is False


def test_profit_compounds_in_bucket():
    a = AllocationManager.from_budgets(day_budget=300, long_budget=700)
    a.record_close(DAY, 150)                  # +150 realized
    assert a.get(DAY).capital == 450
    assert a.can_open(DAY, size=450, deployed=0) is True   # compounded headroom


def test_drawdown_circuit_breaker_tiers():
    a = AllocationManager.from_budgets(day_budget=1000, long_budget=1000)
    # peak gets seeded to capital (1000); equity drops to trigger each tier
    assert a.update_drawdown(DAY, 1000 * (1 - settings.DRAWDOWN_REDUCE_PCT)) == "reduced"
    assert a.update_drawdown(DAY, 1000 * (1 - settings.DRAWDOWN_HALT_PCT)) == "halted"
    assert a.update_drawdown(DAY, 1000 * (1 - settings.DRAWDOWN_PAUSE_PCT)) == "paused"


def test_halted_bucket_cannot_open():
    a = AllocationManager.from_budgets(day_budget=1000, long_budget=1000)
    a.get(DAY).drawdown_state = "halted"
    assert a.can_open(DAY, size=10, deployed=0) is False


# ── RiskManager with an allocation ────────────────────────────────────────────

@pytest.fixture
def trader():
    t = PaperTrader(BotConfig.defaults())
    t.balance_usdt = 1_000.0
    return t


def test_risk_blocks_entry_when_bucket_budget_exhausted(trader):
    alloc = AllocationManager.from_budgets(day_budget=100, long_budget=900)
    risk = RiskManager(trader, BotConfig.defaults(), allocation=alloc)
    # fill the day bucket
    trader.place_market_buy("BTC/USDT", 100, current_price=100, fill_qty=1.0, bucket="day")
    # re-tag deployed: position cost ~100 → day bucket near-exhausted
    allowed, reason = risk.can_open_position("ETH/USDT", bucket="day")
    assert allowed is False
    assert "budget" in reason


def test_risk_sizes_against_bucket_capital(trader):
    alloc = AllocationManager.from_budgets(day_budget=100, long_budget=900)
    risk = RiskManager(trader, BotConfig.defaults(), allocation=alloc)
    size = risk.position_size_usdt(price=100, atr=2.0, bucket="day")
    # cannot exceed the day bucket's available budget (100), even if balance is 1000
    assert size <= 100 + 1e-6


def test_no_allocation_falls_back_to_single_pool(trader):
    risk = RiskManager(trader, BotConfig.defaults())   # allocation=None
    allowed, _ = risk.can_open_position("BTC/USDT")
    assert allowed is True
    size = risk.position_size_usdt()
    assert size <= trader.balance_usdt
