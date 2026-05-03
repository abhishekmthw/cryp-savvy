"""
Tests for the risk manager and paper trader logic.
No network access required.
"""

import sys, os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.exchange.paper_trader import PaperTrader
from src.trading.risk_manager import RiskManager
from config import settings


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def trader():
    t = PaperTrader()
    # Override balance to a known value for deterministic tests
    t.balance_inr = 10_000.0
    return t


@pytest.fixture
def risk(trader):
    return RiskManager(trader)


# ── PaperTrader: buy ──────────────────────────────────────────────────────────

class TestPaperTraderBuy:
    def test_buy_creates_position(self, trader):
        pos = trader.place_market_buy("BTC/INR", 2_000, current_price=5_000_000)
        assert pos is not None
        assert "BTC/INR" in trader.positions

    def test_buy_deducts_balance(self, trader):
        trader.place_market_buy("BTC/INR", 2_000, current_price=5_000_000)
        assert trader.balance_inr == pytest.approx(8_000.0, abs=1)

    def test_buy_sets_stop_loss_and_take_profit(self, trader):
        pos = trader.place_market_buy("BTC/INR", 2_000, current_price=100)
        assert pos.stop_loss  == pytest.approx(100 * (1 - settings.STOP_LOSS_PCT),   rel=1e-4)
        assert pos.take_profit == pytest.approx(100 * (1 + settings.TAKE_PROFIT_PCT), rel=1e-4)

    def test_duplicate_buy_rejected(self, trader):
        trader.place_market_buy("BTC/INR", 2_000, current_price=100)
        second = trader.place_market_buy("BTC/INR", 2_000, current_price=100)
        assert second is None

    def test_max_position_limit(self, trader):
        for i in range(settings.MAX_OPEN_POSITIONS):
            trader.place_market_buy(f"COIN{i}/INR", 500, current_price=100)
        extra = trader.place_market_buy("EXTRA/INR", 500, current_price=100)
        assert extra is None

    def test_buy_capped_at_max_position_inr(self, trader):
        pos = trader.place_market_buy("BTC/INR", 999_999, current_price=100)
        assert pos is not None
        assert pos.amount_inr <= settings.MAX_POSITION_INR


# ── PaperTrader: sell ─────────────────────────────────────────────────────────

class TestPaperTraderSell:
    def test_sell_closes_position(self, trader):
        trader.place_market_buy("BTC/INR", 1_000, current_price=100)
        trade = trader.place_market_sell("BTC/INR", 110)
        assert trade is not None
        assert "BTC/INR" not in trader.positions

    def test_sell_returns_proceeds(self, trader):
        trader.place_market_buy("BTC/INR", 1_000, current_price=100)
        trade = trader.place_market_sell("BTC/INR", 110)
        assert trade["proceeds"] == pytest.approx(1_100.0, rel=1e-3)

    def test_profitable_sell_adds_to_balance(self, trader):
        before = trader.balance_inr
        trader.place_market_buy("BTC/INR", 1_000, current_price=100)
        trader.place_market_sell("BTC/INR", 110)
        assert trader.balance_inr > before

    def test_sell_nonexistent_position_returns_none(self, trader):
        result = trader.place_market_sell("GHOST/INR", 100)
        assert result is None


# ── Stop-loss / Take-profit ───────────────────────────────────────────────────

class TestExitConditions:
    def test_stop_loss_triggers(self, trader):
        pos = trader.place_market_buy("BTC/INR", 1_000, current_price=100)
        exit_reason = trader.check_exit_conditions("BTC/INR", pos.stop_loss * 0.99)
        assert exit_reason == "stop_loss"

    def test_take_profit_triggers(self, trader):
        pos = trader.place_market_buy("BTC/INR", 1_000, current_price=100)
        exit_reason = trader.check_exit_conditions("BTC/INR", pos.take_profit * 1.01)
        assert exit_reason == "take_profit"

    def test_no_exit_at_normal_price(self, trader):
        trader.place_market_buy("BTC/INR", 1_000, current_price=100)
        exit_reason = trader.check_exit_conditions("BTC/INR", 102)
        assert exit_reason is None


# ── Daily loss limit ──────────────────────────────────────────────────────────

class TestDailyLossLimit:
    def test_limit_not_hit_initially(self, trader):
        assert not trader.is_daily_limit_hit

    def test_limit_hit_after_large_loss(self, trader):
        trader.place_market_buy("BTC/INR", 2_000, current_price=100)
        # Sell at a price that causes > DAILY_LOSS_LIMIT_INR loss
        crash_price = 100 * (1 - settings.DAILY_LOSS_LIMIT_INR / 2_000 - 0.01)
        trader.place_market_sell("BTC/INR", crash_price)
        assert trader.is_daily_limit_hit

    def test_buy_blocked_when_limit_hit(self, trader, risk):
        trader._daily_pnl = -settings.DAILY_LOSS_LIMIT_INR - 1
        allowed, _ = risk.can_open_position("BTC/INR")
        assert not allowed


# ── RiskManager ───────────────────────────────────────────────────────────────

class TestRiskManager:
    def test_position_allowed_when_clear(self, risk):
        allowed, reason = risk.can_open_position("BTC/INR")
        assert allowed
        assert reason == "ok"

    def test_position_size_respects_cap(self, risk, trader):
        size = risk.position_size_inr()
        assert size <= settings.MAX_POSITION_INR
        assert size <= trader.balance_inr
