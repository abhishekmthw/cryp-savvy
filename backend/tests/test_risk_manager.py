"""
Tests for the risk manager and paper trader logic.
No network access required.
"""

import sys, os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.bot.config import BotConfig
from src.exchange.paper_trader import PaperTrader
from src.trading.risk_manager import RiskManager
from config import settings


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg():
    return BotConfig.defaults()


@pytest.fixture
def trader(cfg):
    t = PaperTrader(cfg)
    # Override balance to a known value for deterministic tests
    t.balance_usdt = 10_000.0
    return t


@pytest.fixture
def risk(trader, cfg):
    return RiskManager(trader, cfg)


# ── PaperTrader: buy ──────────────────────────────────────────────────────────

class TestPaperTraderBuy:
    def test_buy_creates_position(self, trader):
        pos = trader.place_market_buy("BTC/INR", 2_000, current_price=5_000_000)
        assert pos is not None
        assert "BTC/INR" in trader.positions

    def test_buy_deducts_balance(self, trader):
        before = trader.balance_usdt
        pos = trader.place_market_buy("BTC/INR", 2_000, current_price=5_000_000)
        assert trader.balance_usdt == pytest.approx(before - pos.amount_usdt, abs=1e-6)

    def test_buy_sets_stop_loss_and_take_profit(self, trader):
        # No ATR passed → falls back to fixed-pct stops off the (slipped) entry.
        pos = trader.place_market_buy("BTC/INR", 2_000, current_price=100)
        assert pos.stop_loss  == pytest.approx(pos.entry_price * (1 - settings.STOP_LOSS_PCT),   rel=1e-4)
        assert pos.take_profit == pytest.approx(pos.entry_price * (1 + settings.TAKE_PROFIT_PCT), rel=1e-4)

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
        assert pos.amount_usdt <= settings.MAX_POSITION_USDT


# ── PaperTrader: sell ─────────────────────────────────────────────────────────

class TestPaperTraderSell:
    def test_sell_closes_position(self, trader):
        trader.place_market_buy("BTC/INR", 1_000, current_price=100)
        trade = trader.place_market_sell("BTC/INR", 110)
        assert trade is not None
        assert "BTC/INR" not in trader.positions

    def test_sell_returns_proceeds(self, trader):
        pos = trader.place_market_buy("BTC/INR", 1_000, current_price=100)
        trade = trader.place_market_sell("BTC/INR", 110)
        # proceeds are net of fee + slippage (~0.15%), so close to qty*110 but a touch under
        assert trade["proceeds"] == pytest.approx(pos.qty * 110, rel=0.01)
        assert trade["proceeds"] < pos.qty * 110

    def test_profitable_sell_adds_to_balance(self, trader):
        before = trader.balance_usdt
        trader.place_market_buy("BTC/INR", 1_000, current_price=100)
        trader.place_market_sell("BTC/INR", 110)
        assert trader.balance_usdt > before

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
        pos = trader.place_market_buy("BTC/INR", 10_000, current_price=100)
        # Sell at a price that loses > the daily limit on this position's size.
        loss_needed = settings.DAILY_LOSS_LIMIT_USDT + 1
        crash_price = pos.entry_price - (loss_needed / pos.qty)
        trader.place_market_sell("BTC/INR", crash_price)
        assert trader.is_daily_limit_hit

    def test_buy_blocked_when_limit_hit(self, trader, risk):
        trader._daily_pnl = -settings.DAILY_LOSS_LIMIT_USDT - 1
        allowed, _ = risk.can_open_position("BTC/INR")
        assert not allowed


# ── RiskManager ───────────────────────────────────────────────────────────────

class TestRiskManager:
    def test_position_allowed_when_clear(self, risk):
        allowed, reason = risk.can_open_position("BTC/INR")
        assert allowed
        assert reason == "ok"

    def test_position_size_respects_cap(self, risk, trader):
        size = risk.position_size_usdt()
        assert size <= settings.MAX_POSITION_USDT
        assert size <= trader.balance_usdt


# ── Churn control: cooldowns + daily per-symbol cap ───────────────────────────

class TestChurnControl:
    def _backdate_exit(self, trader, symbol, seconds):
        ts, reason = trader.last_exit[symbol]
        trader.last_exit[symbol] = (ts - seconds, reason)

    def test_stopout_cooldown_blocks_then_expires(self, trader, risk):
        trader.place_market_buy("BTC/USDT", 200, current_price=100)
        trader.place_market_sell("BTC/USDT", 98, reason="stop_loss")

        allowed, reason = risk.can_open_position("BTC/USDT")
        assert not allowed and "cooldown" in reason

        self._backdate_exit(trader, "BTC/USDT", settings.STOPOUT_COOLDOWN_S + 1)
        allowed, _ = risk.can_open_position("BTC/USDT")
        assert allowed

    def test_reentry_cooldown_after_any_exit(self, trader, risk):
        trader.place_market_buy("ETH/USDT", 200, current_price=100)
        trader.place_market_sell("ETH/USDT", 102, reason="sell_signal")

        allowed, reason = risk.can_open_position("ETH/USDT")
        assert not allowed and "cooldown" in reason

        # The shorter re-entry window applies to non-stop-loss exits.
        self._backdate_exit(trader, "ETH/USDT", settings.REENTRY_COOLDOWN_S + 1)
        allowed, _ = risk.can_open_position("ETH/USDT")
        assert allowed

    def test_daily_per_symbol_cap(self, trader, risk):
        for _ in range(settings.MAX_TRADES_PER_SYMBOL_PER_DAY):
            trader.place_market_buy("SOL/USDT", 200, current_price=100)
            trader.place_market_sell("SOL/USDT", 101, reason="sell_signal")
            self._backdate_exit(trader, "SOL/USDT", settings.REENTRY_COOLDOWN_S + 1)

        allowed, reason = risk.can_open_position("SOL/USDT")
        assert not allowed and "daily trade cap" in reason
        # Other symbols are unaffected.
        assert risk.can_open_position("AAVE/USDT")[0]

    def test_cap_counter_resets_on_new_day(self, trader):
        trader.symbol_trades_today["SOL/USDT"] = 99
        trader._day_start -= 86_400 * 2       # pretend last activity was 2 days ago
        trader.reset_daily_pnl_if_new_day()
        assert trader.symbol_trades_today == {}

    def test_seed_churn_state_from_trade_rows(self, trader):
        import time as _time
        from src.exchange.paper_trader import _utc_day_start
        now = _time.time()
        # Entry at the midpoint of today's UTC day — always ≥ day start.
        held_s = max(1.0, (now - _utc_day_start()) / 2)
        trader.seed_churn_state([
            {"symbol": "BTC/USDT", "ts": now, "reason": "stop_loss",
             "duration_s": held_s},
            {"symbol": "ETH/USDT", "ts": now - 86_400 * 3, "reason": "sell_signal",
             "duration_s": 3600},
        ])
        assert trader.last_exit["BTC/USDT"][1] == "stop_loss"
        # BTC was entered today → counts toward the daily cap.
        assert trader.symbol_trades_today.get("BTC/USDT") == 1
        # ETH closed 3 days ago → no daily-cap count.
        assert "ETH/USDT" not in trader.symbol_trades_today


# ── Kelly: rolling lookback + negative-edge de-risking ────────────────────────

class TestKellyDeRisking:
    def test_negative_edge_scales_risk_down(self, trader, risk):
        # 25 trades (≥ KELLY_MIN_TRADES), 20% win rate at 0.5 payoff → Kelly < 0.
        trader.closed_trades = [{"pnl": -10.0}] * 20 + [{"pnl": 5.0}] * 5
        assert risk._risk_fraction() == pytest.approx(
            settings.RISK_PER_TRADE * settings.NEGATIVE_EDGE_RISK_MULT)

    def test_lookback_window_tracks_recent_edge(self, trader, risk):
        # Long profitable history followed by a bad recent run: the rolling
        # window (last KELLY_LOOKBACK_TRADES) must dominate, not lifetime stats.
        trader.closed_trades = ([{"pnl": 20.0}] * 50
                                + [{"pnl": -10.0}] * 28 + [{"pnl": 1.0}] * 2)
        assert risk._risk_fraction() == pytest.approx(
            settings.RISK_PER_TRADE * settings.NEGATIVE_EDGE_RISK_MULT)

    def test_small_sample_uses_base_risk(self, trader, risk):
        trader.closed_trades = [{"pnl": -10.0}] * (settings.KELLY_MIN_TRADES - 1)
        assert risk._risk_fraction() == pytest.approx(settings.RISK_PER_TRADE)
