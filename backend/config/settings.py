"""
Central configuration for the trading bot.
All tunable parameters live here — no magic numbers scattered in code.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Mode ──────────────────────────────────────────────────────────────────────
MODE = os.getenv("MODE", "paper")          # "paper" | "live"
LIVE = MODE == "live"

# ── Exchange ──────────────────────────────────────────────────────────────────
COINDCX_API_KEY    = os.getenv("COINDCX_API_KEY", "")
COINDCX_API_SECRET = os.getenv("COINDCX_API_SECRET", "")

# ── Sentiment APIs ────────────────────────────────────────────────────────────
CRYPTOPANIC_API_KEY  = os.getenv("CRYPTOPANIC_API_KEY", "")
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT", "crypto_bot/1.0")

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Coin Selection ────────────────────────────────────────────────────────────
QUOTE_CURRENCY  = "INR"          # Only trade INR pairs
TOP_N_COINS     = 10             # How many top-momentum coins to analyse each cycle
SCAN_INTERVAL_S = 300            # Seconds between each full scan (5 minutes)

# ── Technical Analysis ────────────────────────────────────────────────────────
TIMEFRAME        = "1h"          # Candle timeframe passed to ccxt
CANDLE_LIMIT     = 100           # Number of candles to fetch per coin
EMA_FAST         = 9
EMA_SLOW         = 21
RSI_PERIOD       = 14
RSI_LOWER        = 45            # RSI must be ABOVE this for a buy signal
RSI_UPPER        = 65            # RSI must be BELOW this for a buy signal (not overbought)
MACD_FAST        = 12
MACD_SLOW        = 26
MACD_SIGNAL      = 9
VOLUME_MULT      = 1.5           # Volume must be > VOLUME_MULT × 20-bar average

# ── Signal Scoring ────────────────────────────────────────────────────────────
# Weights must sum to 1.0
TECHNICAL_WEIGHT  = 0.70
SENTIMENT_WEIGHT  = 0.30

BUY_THRESHOLD  = 65    # Composite score (0-100) above which we buy
SELL_THRESHOLD = 35    # Score below which we exit an open position

# ── Risk Management ───────────────────────────────────────────────────────────
INITIAL_CAPITAL_INR  = 10_000.0   # Starting paper balance (or real balance cap)
MAX_POSITION_INR     = 2_000.0    # Max INR value per single trade
MAX_OPEN_POSITIONS   = 2          # Max simultaneous open trades
STOP_LOSS_PCT        = 0.03       # 3%  below entry price
TAKE_PROFIT_PCT      = 0.06       # 6%  above entry price
TRAILING_STOP_TRIGGER= 0.03       # Activate trailing stop after +3% gain
TRAILING_STOP_OFFSET = 0.02       # Trail 2% below the highest price seen
DAILY_LOSS_LIMIT_INR = 1_000.0    # Bot pauses for the day if daily loss exceeds this

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "trades.db")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FILE  = os.path.join(os.path.dirname(__file__), "..", "data", "bot.log")

# ── API Server ────────────────────────────────────────────────────────────────
# PORT is injected by Railway automatically; defaults to 8000 locally
API_PORT         = int(os.getenv("PORT", "8000"))
API_CORS_ORIGINS = os.getenv(
    "API_CORS_ORIGINS",
    "http://localhost:3000",          # local Next.js dev server
)

# ── Clerk Authentication ──────────────────────────────────────────────────────
# JWKS URL format: https://<your-clerk-domain>/.well-known/jwks.json
# Find it in Clerk Dashboard → API Keys → Advanced
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")
