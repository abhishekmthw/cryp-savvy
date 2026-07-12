# CLAUDE.md — backend/

## What this is

Python service for **CrypSavvy** that does three things in one process:
1. **Market scanner** — a shared thread that ranks the USDT universe every 5 min
   AND a fast price-monitor (~15 s) that keeps live prices fresh.
2. **Per-user trading bots** — one worker thread per active user; scores coins,
   routes entries to a day/long capital bucket, executes trades.
3. **FastAPI server** — REST + WebSocket for the Next.js dashboard (daemon thread).

Trades **USDT-quoted pairs** on CoinDCX (BTC/USDT, ETH/USDT, …). Deploys to
**Fly.io** (Mumbai) via [`fly.toml`](fly.toml) — see [../deploy/FLY-SETUP-GUIDE.md](../deploy/FLY-SETUP-GUIDE.md).

---

## Architecture

```
config/settings.py              All tunable params + env loading (USDT, ATR, Kelly,
                                drawdown breakers, regime, fees/slippage, live gate)
src/
  exchange/
    coindcx_client.py           CoinDCX REST (retry/backoff + circuit breaker;
                                idempotent order create; fill reconciliation)
    paper_trader.py             Per-user sim book (ATR stops, fees/slippage,
                                per-bucket accounting, restart restore)
  data/
    market_data.py              OHLCV fetcher with 60s cache
    sentiment.py                RSS news + Reddit → score (weight capped ≤10%)
  analysis/
    indicators.py               ATR, Donchian, ROC, SMA (pure helpers)
    regime.py                   bull / bear / sideways detection (meta-layer)
    strategies.py               regime-aware ensemble → action + day/long bucket
    technical.py                EMA/RSI/MACD/Volume sub-scores
    signal_engine.py            strategy + composite-score quality gate
  trading/
    risk_manager.py             bucket-aware gating + fractional-Kelly/ATR sizing
    order_manager.py            order state machine (pending→filled), live/paper sync
    portfolio.py                DB facade (trades, positions, orders, allocation)
    allocation.py               AllocationManager — day/long buckets, drawdown breakers
  bot/
    config.py                   BotConfig dataclass (per-user, from DB row)
    scanner.py                  MarketDataScanner (slow universe scan + fast price loop)
    user_worker.py              UserBot: main tick + fast SL/TP loop + bucket routing
    orchestrator.py             BotOrchestrator — per-user worker pool
  backtest/
    engine.py                   historical replay + walk-forward (models trailing,
                                cooldowns, stop floor — same helpers as live)
    metrics.py                  Sharpe, max-DD, profit factor, win-rate, expectancy
    run.py                      validation gate runner (GO / NO-GO); --profile
                                legacy|improved A/B + exit-reason histogram
  monitoring/                   logger, Telegram alerts, report.py (diagnostics
                                export report builder + settings_snapshot)
  security/crypto.py            envelope encryption (KEK→DEK) for user credentials
  db/
    engine.py                   SQLAlchemy engine + session_scope (TLS-enforced)
    models.py                   users, user_credentials, user_bot_config, trades,
                                positions, orders, allocations, bucket_state
    repositories.py             the only place user-scoped queries live
  api/
    state.py                    UserBotState — thread-safe shared memory (bounded queue)
    auth.py                     Clerk JWKS verification (cached 30 min, kid-miss refresh)
    deps.py                     get_current_user (+ Clerk sub validation), get_vault
    ratelimit.py                per-IP sliding-window limiter
    ws_tickets.py               single-use WebSocket handshake tickets
    credentials.py              per-user CoinDCX/Telegram credential CRUD + validate
    control.py                  start/stop/mode (live mode hard-gated)
    allocation.py               capital-allocation endpoints
    diagnostics.py              trade diagnostics + export report (md/json)
    validation.py               read-only credential validation (sanitized errors)
    main.py                     FastAPI app: middleware, /health, REST, WS
  runner.py                     Entry point — scanner + orchestrator + API thread
migrations/                     Alembic (0001 multi-tenant → 0006 diagnostics v2)
tests/                          pytest (no network/keys; uses fakes)
Dockerfile / fly.toml
```

---

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in keys (DATABASE_URL + MASTER_ENCRYPTION_KEY required)
python src/runner.py   # API on http://localhost:8000
```

## Running tests / backtest

```bash
pytest tests/ -v                       # no network or API keys required
python -m src.backtest.run BTC/USDT ETH/USDT   # walk-forward GO/NO-GO gate (needs network)
# A/B the post-July strategy changes: legacy = July parameterisation
python -m src.backtest.run --profile legacy   BTC/USDT ETH/USDT AAVE/USDT
python -m src.backtest.run --profile improved BTC/USDT ETH/USDT AAVE/USDT
```

---

## Environment Variables

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | Postgres/Supabase. TLS (`sslmode=require`) auto-enforced for remote hosts |
| `MASTER_ENCRYPTION_KEY` | Yes | Base64 32-byte KEK; app refuses to start without it. **Reuse the same key** or stored credentials can't be decrypted |
| `MASTER_ENCRYPTION_KEY_PREVIOUS` | No | Decrypt-only fallback during KEK rotation |
| `CLERK_JWKS_URL` | Yes (prod) | `https://<domain>/.well-known/jwks.json` |
| `API_CORS_ORIGINS` | Yes (prod) | Comma-separated frontend URLs (also used for the Origin/CSRF check) |
| `LIVE_TRADING_ENABLED` | No | **Default `false`.** Live mode is refused until set `true` (validation gate) |
| `REDDIT_CLIENT_ID` / `SECRET` / `USER_AGENT` | No | Optional sentiment |
| `PORT` | No | uvicorn bind port; defaults to 8000 |

Per-user CoinDCX/Telegram keys are **not** env vars — they live encrypted in the
`user_credentials` table, entered via the dashboard.

---

## API Endpoints

All `/api/*` routes require `Authorization: Bearer <clerk_jwt>`. `/health` is public.

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | 200 if scanner thread alive (Fly health check) |
| GET | `/api/status` | Bot running state, mode, last scan, daily P&L |
| GET | `/api/portfolio` (+`/history`) | Summary + stats; P&L history |
| GET | `/api/portfolio/diagnostics` | Loss-attribution analytics (edge, R:R, MAE/MFE, churn, breakdowns) |
| GET | `/api/portfolio/diagnostics/export?format=markdown\|json` | Self-describing diagnostics report — the markdown is built to paste into Claude Code |
| GET | `/api/positions` | Open positions with live prices |
| GET | `/api/trades?limit=` | Trade history |
| GET | `/api/signals` | Last scan results (incl. regime + bucket) |
| POST | `/api/ws/token` | Mint a single-use WS handshake ticket |
| POST | `/api/bot/start` · `/stop` · PUT `/mode` | Lifecycle (live mode gated) |
| PUT/DELETE/POST | `/api/credentials/*` | CoinDCX/Telegram CRUD + test (rate-limited) |
| GET/POST | `/api/allocation` · `/pause` · `/resume` · `/confirm-shift` | Capital allocation |
| WS | `/ws?ticket=<ticket>` | Real-time events (ticket, **not** JWT, in the URL) |

## WebSocket Events

```json
{"type": "snapshot",        "data": {...}}
{"type": "scan_complete",   "data": {"signals": [...], "open_positions": 1}}
{"type": "price_update",    "data": {"prices": {...}, "portfolio_value": ..., "daily_pnl": ...}}
{"type": "trade_buy",       "data": {"symbol": "BTC/USDT", "price": ..., "amount_usdt": ...}}
{"type": "trade_sell",      "data": {"symbol": "BTC/USDT", "pnl": ..., "reason": ...}}
{"type": "shift_suggestion","data": {"regime": "bull", "suggested_day_pct": 25, ...}}
{"type": "bucket_drawdown", "data": {"bucket": "day", "state": "paused"}}
{"type": "daily_limit_hit", "data": {"timestamp": ...}}
```

---

## Key Design Rules

- **All params in `config/settings.py`** — never hardcode thresholds.
- **USDT only** (`QUOTE_CURRENCY`). Money fields are `*_usdt`; DB money columns are
  `Numeric` (never `Float`). Candle pairs use the `B-` prefix for USDT (`I-` for INR).
- **Paper trader is the source of truth for positions, even in live mode** — live
  fills are reconciled (actual price/qty) and mirrored into the paper book.
- **Orders are idempotent**: a row is written `pending` before the exchange call
  (UUID client-order-id); an ambiguous timeout is marked `unconfirmed`, never retried.
- **Capital buckets**: every entry is tagged `day` or `long`; `AllocationManager`
  isolates each bucket's budget, compounds its realized P&L, and runs a per-bucket
  drawdown circuit-breaker (reduce → halt → pause). The bot never moves funds
  between buckets without a user-confirmed shift.
- **Sizing** is fractional-Kelly + ATR risk, capped by the bucket budget and
  `max_position_usdt`. Stops are ATR-based (bucket-scaled), not fixed-pct.
- **State persists**: open positions + daily P&L are restored on restart so the
  loss-limit can't be reset by bouncing the process.
- **`BotState`/`UserBotState`** is the only bridge between the bot thread and the
  API thread. Hold `state.lock` for all `paper_trader` reads/writes.
- **Live mode is hard-gated** by `LIVE_TRADING_ENABLED` (+ per-request confirm).
- **JWKS is cached 30 min** in `src/api/auth.py`; a kid-miss forces one refresh.

---

## Deployment

**Primary: Fly.io** (Mumbai). Walkthrough: [../deploy/FLY-SETUP-GUIDE.md](../deploy/FLY-SETUP-GUIDE.md).
Validation before live: [../deploy/VALIDATION-RUNBOOK.md](../deploy/VALIDATION-RUNBOOK.md).

- Config is [`fly.toml`](fly.toml): builds this `Dockerfile`, region `bom`, always-on,
  `shared-cpu-1x` / 512 MB, `/health` check.
- Secrets set with `fly secrets set …`: `DATABASE_URL`, `MASTER_ENCRYPTION_KEY`,
  `CLERK_JWKS_URL`, `API_CORS_ORIGINS`, `LIVE_TRADING_ENABLED`, `REDDIT_*`.
- **Single instance only** — the in-memory scanner cache / per-user threads can't be
  horizontally scaled. Persist state to the DB rather than going multi-worker.
- Run migrations from your machine: `alembic upgrade head` (chain `0001 → 0006`).

**Alternative (self-hosted VM)**: OCI/EC2 + Cloudflare Tunnel — see [../deploy/README.md](../deploy/README.md).

---

## Warnings

- Never commit `.env`.
- **Never set `LIVE_TRADING_ENABLED=true` until the backtest passes and you've
  paper-traded 1–2 weeks** (the runbook is the checklist).
- Use **trade-only (no-withdrawal)** CoinDCX keys, IP-allowlisted to the Fly egress IP.
- CoinDCX KYC takes 1–3 business days in India.
