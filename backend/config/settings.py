"""
Central configuration for the trading bot.

Split into:
- **Operator config** (env vars) — shared across all users
- **Strategy defaults** (constants) — copied into each user's UserBotConfig on signup
- **Database + crypto** (env vars) — multi-tenant infrastructure

Per-user secrets (CoinDCX keys, Telegram bot/chat) are NOT here — they live
encrypted in the `user_credentials` table.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")
# SQLAlchemy's bare `postgresql://` scheme resolves to psycopg2; we ship psycopg
# v3 (`psycopg[binary]`) instead, so rewrite the scheme to select the v3 driver.
# Also normalise Supabase's legacy `postgres://` prefix.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]


def _enforce_db_tls(url: str) -> str:
    """
    Require TLS for remote Postgres so credentials never cross the wire in the
    clear. Local dev databases (localhost/127.0.0.1) are exempt.
    """
    if not url or "sslmode=" in url:
        return url
    lowered = url.lower()
    if "@localhost" in lowered or "@127.0.0.1" in lowered or "@db:" in lowered:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


DATABASE_URL = _enforce_db_tls(DATABASE_URL)

# ── Encryption (KEK = master Key Encryption Key) ──────────────────────────────
# Base64-encoded 32-byte key. Required at startup.
MASTER_ENCRYPTION_KEY          = os.getenv("MASTER_ENCRYPTION_KEY", "")
# Optional decrypt-only fallback during rotation.
MASTER_ENCRYPTION_KEY_PREVIOUS = os.getenv("MASTER_ENCRYPTION_KEY_PREVIOUS", "")

# ── Operator-owned sentiment APIs (shared across all users) ───────────────────
# News is pulled from public RSS feeds (no key needed) — see src/data/sentiment.py.
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT", "crypto_bot/1.0")

# ── Coin Selection ────────────────────────────────────────────────────────────
QUOTE_CURRENCY  = "USDT"         # Trade USDT-quoted pairs (BTC/USDT, ETH/USDT, …)
TOP_N_COINS     = 10             # How many top-momentum coins to analyse each cycle
SCAN_INTERVAL_S = 300            # Seconds between each full scan (5 minutes)
# Fast price/exit monitor cadence. The 5-min scan ranks the universe; this short
# loop refreshes live prices and checks SL/TP/trailing on held positions so a
# stop-loss isn't ignored for up to 5 minutes. One /ticker call returns every
# symbol, so this is a single cheap request per cycle.
FAST_POLL_S     = 15

# Always-eligible large caps — kept in the universe regardless of momentum rank
# so the bot can always act on BTC/ETH (deep liquidity, tight spreads).
CORE_SYMBOLS    = ["BTC/USDT", "ETH/USDT"]
# Skip thinly-traded pairs: minimum 24h quote (USDT) volume to be eligible.
MIN_24H_QUOTE_VOLUME = 250_000.0
# Minimum notional per order (USDT). CoinDCX min-notional is a few dollars;
# this also stops dust trades from the paper trader.
MIN_TRADE_USDT  = 5.0

# ── Technical Analysis ────────────────────────────────────────────────────────
TIMEFRAME        = "1h"
CANDLE_LIMIT     = 100
# Evaluate entry/exit SIGNALS on the last CLOSED candle, not the still-forming
# one. The live feed's most recent 1h bar is incomplete, so deciding on it makes
# the bot chase intrabar spikes — Donchian "breakouts" that fail by the close —
# and buy short-term tops that revert into the stop. This was the main reason
# live diverged from (and badly underperformed) the closed-bar backtest. SL/TP/
# trailing still react to live prices via the fast loop, so exits stay prompt.
SIGNAL_ON_CLOSED_CANDLE = True
EMA_FAST         = 9
EMA_SLOW         = 21
RSI_PERIOD       = 14
RSI_LOWER        = 45
RSI_UPPER        = 65
MACD_FAST        = 12
MACD_SLOW        = 26
MACD_SIGNAL      = 9
VOLUME_MULT      = 1.5

# ── Signal Scoring ────────────────────────────────────────────────────────────
# Sentiment is held to ≤10% until it's validated against forward returns by the
# backtester; technical drives the decision.
TECHNICAL_WEIGHT  = 0.90
SENTIMENT_WEIGHT  = 0.10

BUY_THRESHOLD  = 60

# ── Regime detection (meta-layer) ─────────────────────────────────────────────
# Classifies bull / bear / sideways so the bot uses the right sub-strategy.
REGIME_FAST_SMA = 20
REGIME_SLOW_SMA = 50
REGIME_FLAT_BAND = 0.005   # |fast-slow|/slow below this ⇒ sideways

# ── Strategies (day vs long-term buckets) ─────────────────────────────────────
DONCHIAN_PERIOD     = 20    # breakout lookback (day bucket)
RSI_OVERSOLD        = 30    # mean-reversion buy trigger in sideways regime
RSI_OVERBOUGHT      = 70

# ── ATR-based dynamic stops ───────────────────────────────────────────────────
USE_ATR_STOPS   = True
ATR_PERIOD      = 14
ATR_SL_MULT_DAY = 2.0      # tighter stops for day-trades
ATR_TP_MULT_DAY = 3.0
ATR_SL_MULT_LONG= 3.0      # wider stops for long-term holds
ATR_TP_MULT_LONG= 6.0

# ── Position sizing (fractional Kelly + ATR risk) — AGGRESSIVE profile ─────────
RISK_PER_TRADE   = 0.04    # risk ~4% of bucket capital per trade
KELLY_FRACTION   = 0.6     # fraction of full Kelly to apply (0 disables Kelly)
KELLY_MIN_TRADES = 20      # don't trust Kelly until this many closed trades

# ── Drawdown circuit-breakers (per bucket) — AGGRESSIVE thresholds ────────────
DRAWDOWN_REDUCE_PCT = 0.15  # halve sizing
DRAWDOWN_HALT_PCT   = 0.25  # stop new entries
DRAWDOWN_PAUSE_PCT  = 0.35  # pause + alert

# ── Execution realism (paper trader + backtester) ─────────────────────────────
FEE_PCT      = 0.001       # 0.10% taker fee per side
SLIPPAGE_PCT = 0.0005      # 0.05% slippage per side

# ── Risk-Management Defaults (copied to UserBotConfig on user signup) ─────────
# Denominated in USDT. These are paper-mode starting defaults; the live
# capital a bot may use is set per-user via the allocation feature (Phase 5).
INITIAL_CAPITAL_USDT  = 1_000.0
MAX_POSITION_USDT     = 200.0
MAX_OPEN_POSITIONS   = 3
STOP_LOSS_PCT        = 0.03
TAKE_PROFIT_PCT      = 0.06
TRAILING_STOP_TRIGGER= 0.03
TRAILING_STOP_OFFSET = 0.02
DAILY_LOSS_LIMIT_USDT = 100.0

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FILE  = os.path.join(os.path.dirname(__file__), "..", "data", "bot.log")

# ── API Server ────────────────────────────────────────────────────────────────
API_PORT         = int(os.getenv("PORT", "8000"))
API_CORS_ORIGINS = os.getenv("API_CORS_ORIGINS", "http://localhost:3000")

# ── Clerk Authentication ──────────────────────────────────────────────────────
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")

# ── Live-trading gate ─────────────────────────────────────────────────────────
# Hard operational gate: live mode is REFUSED unless this is explicitly enabled.
# Flip to "true" only after the backtest walk-forward passes and 1–2 weeks of
# paper trading look healthy (see deploy/VALIDATION-RUNBOOK.md).
LIVE_TRADING_ENABLED = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
