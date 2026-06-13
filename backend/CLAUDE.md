# CLAUDE.md — backend/

## What this is

Python service for **CrypSavvy** that does two things in one process:
1. **Trading bot loop** — scans CoinDCX every 5 min, scores coins, executes trades
2. **FastAPI server** — exposes REST + WebSocket for the Next.js dashboard (runs in a daemon thread)

Deploys to **Railway** (set Root Directory = `backend`).

---

## Architecture

```
config/settings.py              All tunable parameters + env var loading
src/
  exchange/
    coindcx_client.py           CoinDCX REST API via ccxt
    paper_trader.py             Simulation engine (fake balance/positions)
  data/
    market_data.py              OHLCV fetcher with 60s cache
    sentiment.py                RSS news feeds + Reddit → score [-1, +1]
  analysis/
    technical.py                EMA/RSI/MACD/Volume → score 0–100
    signal_engine.py            Weighted combiner → BUY/SELL/HOLD
  trading/
    risk_manager.py             Position limits, daily loss cap
    order_manager.py            Routes orders to paper or live
    portfolio.py                SQLite trade history + pnl_history()
  monitoring/
    logger.py                   Rich (TTY) or plain stdout (Railway)
    alerts.py                   Telegram fire-and-forget
    dashboard.py                Rich table (TTY) or one-line log (headless)
  api/
    state.py                    BotState — thread-safe shared memory
    auth.py                     Clerk JWKS verification (cached 1 h)
    main.py                     FastAPI app: REST routes + WebSocket
  bot.py                        Entry point — starts API thread, runs bot loop
tests/
  test_signals.py
  test_risk_manager.py
data/                           Created at runtime (SQLite + log file)
Dockerfile
railway.toml
```

---

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in keys
python src/runner.py
# API available at http://localhost:8000
```

## Running tests

```bash
pytest tests/ -v   # no network or API keys required
```

---

## Environment Variables

| Variable | Required | Notes |
|---|---|---|
| `MODE` | Yes | `paper` or `live` |
| `COINDCX_API_KEY` / `SECRET` | Live only | CoinDCX REST credentials |
| `REDDIT_CLIENT_ID` / `SECRET` | Optional | Free script app |
| `REDDIT_USER_AGENT` | Optional | |
| `TELEGRAM_BOT_TOKEN` / `CHAT_ID` | Optional | Trade alerts |
| `API_CORS_ORIGINS` | Yes (prod) | Comma-separated frontend URLs |
| `CLERK_JWKS_URL` | Yes (prod) | `https://<domain>/.well-known/jwks.json` |
| `PORT` | Auto (Railway) | Injected by Railway; defaults to 8000 |

---

## API Endpoints

All routes require `Authorization: Bearer <clerk_jwt>`.

| Method | Path | Returns |
|---|---|---|
| GET | `/api/status` | Bot running state, mode, last scan time |
| GET | `/api/portfolio` | Summary + stats |
| GET | `/api/portfolio/history` | P&L history for chart |
| GET | `/api/positions` | Open positions with live prices |
| GET | `/api/trades?limit=50` | Trade history |
| GET | `/api/signals` | Last scan results |
| WS  | `/ws?token=<jwt>` | Real-time events |

## WebSocket Events

```json
{"type": "snapshot",        "data": {...}}
{"type": "scan_complete",   "data": {"signals": [...], "open_positions": 1}}
{"type": "trade_buy",       "data": {"symbol": "BTC/INR", "price": ..., "score": ...}}
{"type": "trade_sell",      "data": {"symbol": "BTC/INR", "pnl": ..., "reason": ...}}
{"type": "daily_limit_hit", "data": {"timestamp": ...}}
```

---

## Key Design Rules

- **All params in `config/settings.py`** — never hardcode thresholds.
- **`BotState`** is the only bridge between the bot thread and the API thread. Use `bot_state.lock` when reading `paper_trader` from the API handlers.
- **Sentiment is graceful** — missing keys return neutral score (50/100); bot continues.
- **Paper trader is always the source of truth** for positions, even in live mode.
- **JWKS is cached 1 hour** in `src/api/auth.py` — do not bypass the cache.

---

## Railway Deployment

1. Push repo to GitHub
2. Railway → New Project → Deploy from GitHub
3. Service Settings → **Root Directory = `backend`**
4. Add all env vars from `.env.example` in the Variables tab
5. Railway auto-detects `railway.toml` and builds the Dockerfile

**SQLite persistence**: add a Railway Volume mounted at `/app/data` before going live.

---

## Warnings

- Never commit `.env`
- Never set `MODE=live` without 1–2 weeks of paper trading validation
- CoinDCX KYC takes 1–3 business days in India
