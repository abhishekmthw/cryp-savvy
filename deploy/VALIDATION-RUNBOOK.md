# CrypSavvy — Validation → Live Runbook

This is the gate between "the bot works in paper mode" and "the bot trades real
USDT." Do **not** skip steps. Live trading is hard-gated by the
`LIVE_TRADING_ENABLED` env var (default `false`) — the API refuses to switch a
user to live mode until you set it.

## 0. Pre-requisites

- Backend deployed (Fly.io Mumbai) with migrations applied:
  `alembic upgrade head` (chain: `0001 → 0002 → 0003 → 0004`).
- `DATABASE_URL`, `MASTER_ENCRYPTION_KEY`, `CLERK_JWKS_URL`, `API_CORS_ORIGINS` set.
- Frontend deployed on Vercel; you can sign in and reach the dashboard.

## 1. Backtest gate (offline, no keys)

Run the walk-forward backtest on the core symbols:

```bash
cd backend
python -m src.backtest.run BTC/USDT ETH/USDT
```

- It fetches public OHLCV, runs an expanding-window backtest with **fees +
  slippage**, then a **walk-forward** (out-of-sample) report.
- **GO** requires: average OOS Sharpe ≥ 0.5 and worst OOS drawdown ≤ 35%.
- If **NO-GO**: do not proceed. Tune `config/settings.py` strategy params
  (regime SMAs, Donchian period, ATR multipliers, thresholds) and re-run. If the
  edge only appears in-sample and collapses out-of-sample, the strategy is
  overfit — keep iterating in paper mode.

## 2. Paper-trade window (1–2 weeks, real-time)

1. Sign in → **Allocation** page → allocate a notional USDT amount with a
   day/long split (e.g. 30/70). Confirm the per-bucket cards populate.
2. Start the bot in **paper** mode. Leave it running 1–2 weeks.
3. Watch on the dashboard / `/api/portfolio`:
   - live prices update within ~15 s (fast price loop) — no 5-minute lag;
   - stop-losses fire promptly (not only on the 5-min scan);
   - per-bucket drawdown states stay `normal`/`reduced` (not `paused`);
   - realized P&L roughly tracks the backtest expectancy (paper models fees +
     slippage, so it should be close, not wildly better).
4. Restart the backend mid-window and confirm open positions + today's P&L are
   **restored from the DB** (no reset of the daily loss-limit).

Proceed only if paper results are consistent with the backtest and nothing looks
broken.

## 3. Exchange key hygiene (before live)

On CoinDCX, create a **trade-only** API key for the bot:

- Permissions: **spot trading + read** — **NO withdrawal**. This caps worst-case
  damage from a compromise to trading losses, never fund theft.
- **IP-allowlist** the bot's egress IP. On Fly.io, allocate a dedicated egress
  IP (`fly ips allocate-v4`) and add it to the CoinDCX key allowlist so the key
  is useless from anywhere else.
- Save the key in the dashboard **Settings → Credentials** (stored encrypted via
  envelope encryption; validated read-only before saving).

## 4. Enable live + small-cap ramp

1. Set the gate on the backend: `fly secrets set LIVE_TRADING_ENABLED=true`
   (this is the only switch that lets the API accept a live-mode request).
2. On the Allocation page, allocate a **small** amount first (e.g. $50–100).
3. Dashboard → switch mode to **live** (confirms the risk dialog).
4. Watch the first few live trades closely:
   - the `orders` table shows `pending → filled` with **actual fill price/qty**
     reconciled (not the pre-trade estimate);
   - paper book and the CoinDCX balance stay in sync (no orphaned/ghost
     positions);
   - no `unconfirmed` orders pile up (those need manual reconciliation).
5. Scale the allocation up gradually as confidence grows. Profit compounds inside
   each bucket — the bot never withdraws it.

## 5. Rollback / kill switch

- **Stop the bot** from the dashboard (stops new entries; existing positions stay
  on the exchange — close them manually if needed).
- **Pause an allocation** (Allocation page) to halt new entries while keeping
  positions.
- **Disable live globally**: `fly secrets set LIVE_TRADING_ENABLED=false` and
  restart — every user drops back to paper-only.
- The per-bucket drawdown circuit-breaker auto-pauses a bucket at the configured
  threshold (default 35%).

## Known follow-ups (tracked, not blockers)

- `allocate_all` currently stores the flag; wire it to read the live CoinDCX
  USDT balance at allocation time.
- Monte-Carlo entry-shuffle significance test in the backtester.
- DCA + threshold-rebalancing sub-strategies for the long bucket.
- Rolling credential re-decryption TTL (today: cleared on bot stop).
- Replace the 200 ms WS drain with a fully push-based loop; optional CoinDCX
  Socket.io gateway if its feed proves reliable from Mumbai.
