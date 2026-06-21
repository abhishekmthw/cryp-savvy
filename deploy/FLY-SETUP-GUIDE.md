# CrypSavvy Backend — Fly.io Setup Guide

A short, beginner-friendly walkthrough to host the backend on **Fly.io** in the
**Mumbai** region, with automatic deploys on every `git push`.

> This is the **recommended** path. A self-hosted VM alternative (Oracle Cloud / EC2)
> lives in [README.md](README.md), but Fly is simpler:
> it gives you an `https://`/`wss://` URL out of the box, so there's no Cloudflare Tunnel
> and no server to maintain.

**What you'll have at the end:**
- The bot running 24/7 on a Mumbai machine (~$3/month).
- A URL like `https://crypsavvy-backend.fly.dev` for your Vercel dashboard.
- Every push to `main` auto-redeploys the backend.

**Time:** ~20–30 minutes. **You'll need:** a card (Fly requires one), and your Supabase
`DATABASE_URL` + the **same** `MASTER_ENCRYPTION_KEY` you used on Railway.

The config file [`backend/fly.toml`](../backend/fly.toml) is already in the repo — these
steps just wire it up.

---

## Part 1 — Install the Fly CLI and sign in

Install `flyctl` (the Fly command-line tool):

```powershell
# Windows (PowerShell):
iwr https://fly.io/install.ps1 -useb | iex
```
```bash
# macOS / Linux:
curl -L https://fly.io/install.sh | sh
```

Then create your account and log in (this opens a browser; add a card when prompted):

```bash
fly auth signup     # or: fly auth login  (if you already have an account)
```

---

## Part 2 — Create the app

From the repo, go into the backend folder and create the app using the existing config:

```bash
cd crypto-savvy/backend
fly apps create crypsavvy-backend
```

> If the name `crypsavvy-backend` is taken, pick another (e.g. `crypsavvy-backend-abhi`)
> and change the `app = "…"` line at the top of `fly.toml` to match.

---

## Part 3 — Add your secrets

These are injected as environment variables into the app (they are **not** stored in
`fly.toml`). Run this once, substituting your real values:

```bash
fly secrets set \
  DATABASE_URL="postgresql+psycopg://...your Supabase pooler URL..." \
  MASTER_ENCRYPTION_KEY="...the SAME key you used on Railway..." \
  CLERK_JWKS_URL="https://<your-domain>.clerk.accounts.dev/.well-known/jwks.json" \
  API_CORS_ORIGINS="http://localhost:3000,https://<your-app>.vercel.app" \
  LIVE_TRADING_ENABLED="false"
```

⚠️ **`MASTER_ENCRYPTION_KEY` must be identical to Railway's**, or existing users' saved
CoinDCX/Telegram credentials can't be decrypted.

> 🔒 **`LIVE_TRADING_ENABLED` stays `false`** until you've completed the
> [VALIDATION-RUNBOOK.md](VALIDATION-RUNBOOK.md) (backtest GO + a healthy paper-trade
> window). While it's false the API refuses to switch any user to live mode. Flip it
> later with `fly secrets set LIVE_TRADING_ENABLED=true`.

*(Optional, for Reddit sentiment — skip if you don't use it:)*
```bash
fly secrets set REDDIT_CLIENT_ID="..." REDDIT_CLIENT_SECRET="..." REDDIT_USER_AGENT="crypto_bot/1.0 by <you>"
```

---

## Part 4 — Run the database migrations (once)

Same as before — point Alembic at Supabase from your own machine. Fly doesn't do this
for you (this is intentional). Skip if your tables already exist from the Railway setup.

```bash
cd crypto-savvy/backend
pip install -r requirements.txt
$env:DATABASE_URL="<your Supabase URL>"   # bash: export DATABASE_URL='...'
alembic upgrade head
```

---

## Part 5 — Deploy 🚀

```bash
cd crypto-savvy/backend
fly deploy
```

Wait ~2–3 minutes. When it finishes, see it running:

```bash
fly status
fly logs        # should show "API server starting on port 8000" + a scan every ~5 min
```

Your backend is now live at **`https://crypsavvy-backend.fly.dev`** (Fly prints the exact
hostname; it's `https://<app-name>.fly.dev`).

---

## Part 6 — Point the dashboard at it (Vercel)

In **Vercel → Settings → Environment Variables**, set these and **Redeploy**:

```
NEXT_PUBLIC_API_URL = https://crypsavvy-backend.fly.dev
NEXT_PUBLIC_WS_URL  = wss://crypsavvy-backend.fly.dev
```

Make sure that exact Vercel URL is in the `API_CORS_ORIGINS` secret from Part 3. To change
it later:

```bash
fly secrets set API_CORS_ORIGINS="http://localhost:3000,https://<your-app>.vercel.app"
```
(Setting a secret automatically redeploys.)

---

## Part 7 — Turn on auto-deploy (GitHub Actions)

So future `git push`es deploy themselves (the workflow is already in the repo at
`.github/workflows/fly-deploy.yml`):

1. Create a deploy token:
   ```bash
   fly tokens create deploy -x 8760h
   ```
2. Copy the whole token (starts with `FlyV1 …`).
3. On GitHub: **repo → Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `FLY_API_TOKEN`
   - Value: the token.

Done. Now every push to `main` touching `backend/` rebuilds and redeploys automatically.

---

## Part 8 — Check it works ✅

- [ ] **Health:** `curl -i https://crypsavvy-backend.fly.dev/health` → **`200`**
  `{"status":"ok"}` (this is what the Fly health check polls).
- [ ] **Reachable:** `curl -i https://crypsavvy-backend.fly.dev/api/status` → a **`401`** is
  correct (it just wants a login token).
- [ ] **Dashboard:** open your Vercel site, sign in — data loads.
- [ ] **Live feed:** live prices/P&L update within ~15 s (fast price loop); the `wss://`
  WebSocket shows `price_update` events without full refetches.
- [ ] **Auto-deploy:** push a small change under `backend/` → the GitHub Action deploys it.

Once these pass, **delete your old Railway service**.

---

## Handy commands & troubleshooting

```bash
fly status                 # is it running, in which region
fly logs                   # live logs
fly deploy                 # manual deploy
fly secrets list           # names only (values hidden)
fly scale memory 1024      # give it 1 GB if you see out-of-memory restarts
fly scale count 1          # keep exactly ONE instance (never run 2 — see note below)
```

| Symptom | Fix |
|---|---|
| App restarts repeatedly, logs mention `Killed` / OOM | 512 MB too tight for pandas — `fly scale memory 1024`. |
| `bom` region "no capacity" on deploy | Retry shortly, or temporarily deploy to `sin` (Singapore) by editing `primary_region`. |
| Dashboard shows CORS errors | Add the exact Vercel URL to the `API_CORS_ORIGINS` secret (Part 6). |
| Two machines appeared after a deploy | Run `fly scale count 1`. This bot keeps state in memory and must run as a **single** instance. |
| Deploy works locally but Action fails | `FLY_API_TOKEN` secret missing/expired — redo Part 7. |

> ⚠️ **Single instance only.** The bot holds the market-scanner cache and per-user state
> in memory, so it must run as exactly one machine. The `fly.toml` is set up for this
> (`min_machines_running = 1`, `auto_stop_machines = "off"`); don't scale it past 1.
