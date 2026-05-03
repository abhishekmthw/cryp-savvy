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

# ── Encryption (KEK = master Key Encryption Key) ──────────────────────────────
# Base64-encoded 32-byte key. Required at startup.
MASTER_ENCRYPTION_KEY          = os.getenv("MASTER_ENCRYPTION_KEY", "")
# Optional decrypt-only fallback during rotation.
MASTER_ENCRYPTION_KEY_PREVIOUS = os.getenv("MASTER_ENCRYPTION_KEY_PREVIOUS", "")

# ── Operator-owned sentiment APIs (shared across all users) ───────────────────
CRYPTOPANIC_API_KEY  = os.getenv("CRYPTOPANIC_API_KEY", "")
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT", "crypto_bot/1.0")

# ── Legacy (Phase 3 removes references) ───────────────────────────────────────
# These remain importable so the existing single-tenant call sites still resolve
# until Phase 3 refactors them to read from per-user state instead. They default
# to empty/paper so a fresh deployment without them set behaves correctly.
MODE  = os.getenv("MODE", "paper")
LIVE  = MODE == "live"
COINDCX_API_KEY    = os.getenv("COINDCX_API_KEY", "")
COINDCX_API_SECRET = os.getenv("COINDCX_API_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "trades.db")

# ── Coin Selection ────────────────────────────────────────────────────────────
QUOTE_CURRENCY  = "INR"          # Only trade INR pairs
TOP_N_COINS     = 10             # How many top-momentum coins to analyse each cycle
SCAN_INTERVAL_S = 300            # Seconds between each full scan (5 minutes)

# ── Technical Analysis ────────────────────────────────────────────────────────
TIMEFRAME        = "1h"
CANDLE_LIMIT     = 100
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
TECHNICAL_WEIGHT  = 0.70
SENTIMENT_WEIGHT  = 0.30

BUY_THRESHOLD  = 65
SELL_THRESHOLD = 35

# ── Risk-Management Defaults (copied to UserBotConfig on user signup) ─────────
INITIAL_CAPITAL_INR  = 10_000.0
MAX_POSITION_INR     = 2_000.0
MAX_OPEN_POSITIONS   = 2
STOP_LOSS_PCT        = 0.03
TAKE_PROFIT_PCT      = 0.06
TRAILING_STOP_TRIGGER= 0.03
TRAILING_STOP_OFFSET = 0.02
DAILY_LOSS_LIMIT_INR = 1_000.0

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FILE  = os.path.join(os.path.dirname(__file__), "..", "data", "bot.log")

# ── API Server ────────────────────────────────────────────────────────────────
API_PORT         = int(os.getenv("PORT", "8000"))
API_CORS_ORIGINS = os.getenv("API_CORS_ORIGINS", "http://localhost:3000")

# ── Clerk Authentication ──────────────────────────────────────────────────────
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")
