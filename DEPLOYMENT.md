# Deployment Guide

Step-by-step instructions to deploy **CrypSavvy** end-to-end.
Estimated total time: **2–4 hours** (excluding the 1–3 day CoinDCX KYC wait).

---

## Architecture

```
┌─────────────────┐         REST + WebSocket         ┌──────────────────┐
│  Vercel         │ ◄──────────────────────────────► │  Railway         │
│  (frontend/)    │                                  │  (backend/)      │
│  Next.js +      │     Clerk JWT auth on every      │  Python bot +    │
│  Clerk          │     request and WS connection    │  FastAPI server  │
└─────────────────┘                                  └────────┬─────────┘
        ▲                                       Postgres │  market data │
        │                                       (encrypted creds) │     │
        │                                              ▼              ▼
   ┌────┴─────┐    ┌──────────────┐            ┌─────────┐    ┌──────────┐
   │  Clerk   │    │   Supabase   │ ◄──────────│ CoinDCX │    │CryptoPan.│
   │  Auth    │    │  Postgres    │            │ exchange│    │  Reddit  │
   └──────────┘    └──────────────┘            └─────────┘    └──────────┘
```

> **Multi-tenant note:** Each user signs up via Clerk, then pastes their own CoinDCX (and optional Telegram) credentials in **Settings**. Those credentials are encrypted with AES-256-GCM and stored in Supabase Postgres — the database holds only ciphertext. Sentiment APIs (CryptoPanic + Reddit) are operator-shared and stay in Railway env vars.

> **Monorepo note:** backend and frontend live in the same GitHub repo. Vercel and Railway both handle this cleanly via their **Root Directory** setting (`frontend` for Vercel, `backend` for Railway). Each platform builds only its subdirectory and ignores the other. By default, both rebuild on every push to `main` — see the optional optimization tips in Phase 3.2 (Railway Watch Paths) and Phase 4.1 (Vercel Ignored Build Step) to skip rebuilds when only the other project changed.

You will need **7 free operator accounts**, plus end users supply their own CoinDCX/Telegram via the dashboard:

| # | Service | Purpose | Cost |
|---|---|---|---|
| 1 | GitHub | Source code hosting | Free |
| 2 | CryptoPanic | News sentiment data (operator-shared) | Free |
| 3 | Reddit | Community sentiment data (operator-shared) | Free |
| 4 | Clerk | User authentication | Free tier |
| 5 | Supabase | Postgres for users + encrypted credentials | Free (500 MB) |
| 6 | Railway | Backend hosting | $5/month free credit |
| 7 | Vercel | Frontend hosting | Free |
| — | CoinDCX | **Per-user** — each end user adds their own via Settings | Free + KYC |
| — | Telegram | **Per-user** — each end user adds their own via Settings | Free |

---

## Phase 1 — Get all the credentials

### 1.1 GitHub

1. Sign up at [github.com](https://github.com) if you don't have an account
2. Create a **new repository** called `cryp-savvy` (private is fine)
3. Don't initialise with README — we'll push the existing code

### 1.2 CoinDCX — per-user, not operator

**Operators do not need to create a CoinDCX account or API key.** Each end user
who signs up to your service will paste their own keys via the in-app Settings
page; those keys are encrypted at rest with their account's data key.

If **you** also want to use the bot yourself, complete the steps below. Each of
your end users will follow the same steps for their own account — share this
section with them when they sign up.

1. Sign up at [coindcx.com](https://coindcx.com)
2. Complete **KYC** (PAN + Aadhaar) — takes 1–3 business days
3. Once verified: **Profile → API Dashboard → Create New API Key**
4. Save **API Key** and **API Secret** — you won't see the secret again
5. Restrict the key to **trading + read** (not withdrawals)

### 1.3 CryptoPanic (free tier)

1. Sign up at [cryptopanic.com](https://cryptopanic.com)
2. Go to **Account → Developers → API Auth Token**
3. Copy the token

### 1.4 Reddit

1. Sign in at [reddit.com](https://reddit.com)
2. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
3. Scroll to bottom → **"create another app"**
4. Fill in:
   - **name**: `crypto-bot`
   - **type**: select **"script"**
   - **redirect uri**: `http://localhost:8080` (not used but required)
5. Click **create app**
6. From the resulting page, copy:
   - **client_id**: the string under "personal use script" (right under the app name)
   - **client_secret**: the value next to "secret"

### 1.5 Telegram — per-user, not operator

**Operators do not need to create a Telegram bot.** Each end user creates
their own bot+chat and pastes the credentials in Settings — alerts go to
their own private chat. If you also want to use the bot yourself, follow
the steps below for your own account.

**Create the bot:**
1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow the prompts
3. Save the **bot token** (looks like `1234567890:ABC-DEF...`)

**Get your chat ID:**
1. In Telegram, search **@userinfobot** → start it
2. It will reply with your numeric chat ID — save it

**Test it:**
- Send any message to your new bot first (otherwise it can't message you)

### 1.6 Clerk (authentication)

1. Sign up at [clerk.com](https://clerk.com) → **Add Application**
2. Application name: `CrypSavvy Dashboard`
3. **Sign-in options**: enable Email + Google (or whatever you prefer)
4. Click **Create application**
5. From the dashboard, go to **API Keys**:
   - Copy `Publishable key` → frontend env var `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
   - Copy `Secret key` → frontend env var `CLERK_SECRET_KEY`
6. Get the **JWKS URL** for backend verification:
   - **API Keys → Show JWKS Public Key → copy the JWKS URL**
   - Format: `https://<your-app>.clerk.accounts.dev/.well-known/jwks.json`
   - Save as backend env var `CLERK_JWKS_URL`

**Invite additional users (optional):**
- Clerk Dashboard → **Users → Invite User**

### 1.7 Supabase (Postgres)

CrypSavvy stores users, per-user trades, positions, and **encrypted API
credentials** in Postgres. Supabase's free tier (500 MB, free forever)
covers this without consuming Railway's $5/month credit.

1. Sign up at [supabase.com](https://supabase.com) — GitHub login is fine
2. Click **New Project**:
   - Name: `crypsavvy`
   - Database password: generate a strong one and save it
   - Region: pick the one nearest your Railway region (typically `ap-south-1` for India)
3. Wait ~2 minutes for the project to provision
4. Once ready, go to **Project Settings → Database → Connection string**
5. Choose the **Connection pooling** tab (not "Direct connection") and copy the `psql` URI:
   ```
   postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
   ```
6. Convert it to the SQLAlchemy/psycopg3 form by swapping the scheme:
   ```
   postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
   ```
   Save this — you'll paste it into Railway as `DATABASE_URL` in step 3.3.

> ⚠️ **Use port `6543` (pooler)**, not `5432` (direct). Railway's environment opens lots of short-lived connections; the direct port runs out of slots quickly on the free tier. The pooler handles this automatically.

### 1.8 Railway

1. Sign up at [railway.app](https://railway.app) using your GitHub account
2. Authorize Railway to access your GitHub repos
3. (No credit card needed for the free tier)

### 1.9 Vercel

1. Sign up at [vercel.com](https://vercel.com) using your GitHub account
2. Authorize Vercel to access your GitHub repos
3. (No credit card needed for the Hobby tier)

---

## Phase 2 — Push code to GitHub

From the project root:

```bash
cd c:/Users/abhis/OneDrive/Desktop/Projects/Own/crypsavvy
git init
git branch -M main
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-username>/cryp-savvy.git
git push -u origin main
```

> The `.gitignore` automatically excludes `.env`, `data/`, `node_modules/`, and `.next/`.

---

## Phase 3 — Deploy the backend (Railway)

### 3.1 Create the service

1. Railway dashboard → **New Project → Deploy from GitHub repo**
2. Select your `cryp-savvy` repo
3. Railway will start building — **let it fail the first time**, we need to configure it

### 3.2 Configure root directory

1. Click the service → **Settings** tab
2. Scroll to **Service → Root Directory**
3. Set to: `backend`
4. Click **Save**

> **Optional — skip rebuilds on frontend-only changes:** in the same Settings tab, find **Watch Paths** and set it to `backend/**`. Railway will then only rebuild when files inside `backend/` change. Safe to set this up after your first successful deploy.

### 3.3 Generate the master encryption key

The backend refuses to start without `MASTER_ENCRYPTION_KEY`. It's the single
key that wraps every user's per-account data key (DEK). Generate one fresh,
random 32-byte value and treat it as a secret comparable to a database
master password.

On any machine with Python installed:

```bash
python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Copy the printed string. You'll paste it into Railway in the next step.

> ⚠️ **Do not commit this value, store it in `.env`, or paste it into chat.**
> If you lose this key, every user's saved CoinDCX/Telegram credentials
> become unrecoverable. Save a copy in a password manager.

### 3.4 Add environment variables

Go to the **Variables** tab → **+ New Variable** and add each of these:

```
# ── Database ────────────────────────────────────────────────────────────────
DATABASE_URL=<connection-pooler URL from step 1.7, port 6543, with postgresql+psycopg:// scheme>

# ── Encryption ──────────────────────────────────────────────────────────────
MASTER_ENCRYPTION_KEY=<output of the python command in step 3.3>
# Leave MASTER_ENCRYPTION_KEY_PREVIOUS unset for now — only used during key rotation

# ── Operator-shared sentiment APIs ──────────────────────────────────────────
CRYPTOPANIC_API_KEY=<from step 1.3>

REDDIT_CLIENT_ID=<from step 1.4>
REDDIT_CLIENT_SECRET=<from step 1.4>
REDDIT_USER_AGENT=crypto_bot/1.0 by <your_reddit_username>

# ── Auth + CORS ─────────────────────────────────────────────────────────────
CLERK_JWKS_URL=<from step 1.6>

API_CORS_ORIGINS=http://localhost:3000
# Note: we'll add the Vercel URL to this AFTER deploying the frontend
```

> Per-user secrets — `COINDCX_API_KEY`/`SECRET`, `TELEGRAM_BOT_TOKEN`/`CHAT_ID`,
> `MODE` — are **no longer Railway env vars**. Each end user supplies their
> own via the dashboard Settings page; the backend stores them encrypted in
> Postgres.

### 3.5 Run the database migrations

Before the backend can start, the Postgres schema needs to exist. Run Alembic
locally pointing at your Supabase database — Railway doesn't need to do this
itself.

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL='<the same URL you set on Railway>'   # PowerShell: $env:DATABASE_URL='...'
alembic upgrade head
```

You should see `Running upgrade  -> 0001_multi_tenant_initial`. Verify in
Supabase → **Table Editor**: you should see the 5 tables `users`,
`user_credentials`, `user_bot_config`, `trades`, `positions`.

> Re-run `alembic upgrade head` whenever a new migration ships in `backend/migrations/versions/`.

### 3.6 Redeploy

1. **Deployments** tab → **⋮ menu on latest → Redeploy**
2. Wait ~3 minutes for the build
3. Once deployed, go to **Settings → Networking → Generate Domain**
4. Copy the URL (e.g. `https://crypsavvy-production-xxxx.up.railway.app`)
5. **Test the API:**
   ```bash
   curl https://your-railway-url.up.railway.app/api/status
   # Should return 401 Unauthorized (this is correct — needs Clerk JWT)
   ```

---

## Phase 4 — Deploy the frontend (Vercel)

### 4.1 Create the project

1. Vercel → **Add New → Project**
2. Import your `cryp-savvy` GitHub repo
3. Vercel auto-detects **Next.js**
4. Set **Root Directory** to `frontend` (click Edit on Root Directory)

> **Optional — skip rebuilds on backend-only changes:** after deploy, go to **Project → Settings → Git → Ignored Build Step** and paste:
> ```
> git diff --quiet HEAD^ HEAD -- frontend/
> ```
> Vercel skips the build when nothing inside `frontend/` changed. Safe to set this up after your first successful deploy.

### 4.2 Add environment variables

In the same import screen, expand **Environment Variables** and paste:

```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<from step 1.6>
CLERK_SECRET_KEY=<from step 1.6>

NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/dashboard

NEXT_PUBLIC_API_URL=https://<your-railway-url>.up.railway.app
NEXT_PUBLIC_WS_URL=wss://<your-railway-url>.up.railway.app
```

> ⚠️ Use `wss://` (secure WebSocket), not `ws://`, for the production WS URL.

### 4.3 Deploy

1. Click **Deploy** — takes ~2 minutes
2. Once done, copy the production URL (e.g. `https://crypsavvy-xxx.vercel.app`)

### 4.4 Update Clerk allowed origins

1. Clerk Dashboard → **Domains → + Add domain**
2. Add your Vercel URL (without `https://`)
3. Save

### 4.5 Update backend CORS

1. Railway → backend service → **Variables**
2. Edit `API_CORS_ORIGINS` and append the Vercel URL:
   ```
   API_CORS_ORIGINS=http://localhost:3000,https://crypsavvy-xxx.vercel.app
   ```
3. Save → Railway redeploys automatically

---

## Phase 5 — Verify everything works

1. Open your Vercel URL → you should be redirected to `/sign-in`
2. Sign up with email or Google → after sign-up you should land on `/onboarding` (not `/dashboard`)
3. **Onboarding wizard:**
   - **Step 1 — CoinDCX:** paste your API key + secret. Saving runs a read-only `fetch_balance` round-trip; an invalid key shows an inline error and saves nothing
   - **Step 2 — Telegram (optional):** paste bot token + chat ID. Saving sends a confirmation message to your chat. You can skip this step
   - **Done:** click **Open dashboard**
4. On the dashboard, click **Start bot** in the top control bar. The badge should switch to **RUNNING · PAPER** and you should see ₹10,000 balance
5. After ~5 minutes the first scan completes and signals appear; trades appear over hours/days as conditions match

**Sanity-check encryption at rest** — open a Supabase SQL editor and run:

```sql
SELECT user_id, provider, last4, encode(ciphertext, 'hex') AS hex_blob
FROM user_credentials LIMIT 5;
```

The `hex_blob` should be random hex bytes — your real CoinDCX key string must
not appear anywhere in plaintext.

**Sanity-check multi-tenancy** — sign up a second Clerk user (incognito
window). Save different credentials, start that user's bot. Both users'
`/api/positions` and `/api/trades` should be disjoint; their dashboards
should never show each other's data.

---

## Phase 6 — Going live (only after 1–2 weeks of paper trading)

> ⚠️ **Do not skip the paper trading phase.** Validate that the bot is profitable before risking real money. Going live is now a **per-user** action — you toggle your own account, not the operator's deployment.

For each user who wants to switch from paper to live:

1. **Settings page** → confirm CoinDCX shows "Verified ✓" with the right last-4. If not, save the keys again.
2. **Dashboard** → in the paper/live toggle next to the Start button, click **LIVE**
3. A browser confirm dialog will warn you that real CoinDCX funds will be used. Click OK
4. The backend requires the body `{ "confirm": "I_ACCEPT_LIVE_RISK" }` for the live switch (the dashboard handles this for you), then restarts your bot in live mode
5. Start with **half** your capital — keep the rest in reserve
6. Watch the dashboard daily for the first week

> **No Railway env-var changes are needed to go live.** Each user's mode is
> stored in `users.mode` in Postgres. Operators do not have the ability to
> turn live mode on for someone else — it requires that user to be signed in.

> **Trade history is in Postgres, not on the local disk.** No persistent
> Railway volume is needed — Supabase preserves trades and positions across
> redeploys automatically.

---

## Troubleshooting

### Backend won't start on Railway
- Check **Deployments → View Logs**
- Common cause: missing env var → Variables tab → add the missing one
- Specifically check: `MASTER_ENCRYPTION_KEY` (must decode to 32 bytes), `DATABASE_URL` (must use port 6543 pooler, scheme `postgresql+psycopg://`), `CLERK_JWKS_URL`
- If logs show `relation "users" does not exist` — you forgot to run `alembic upgrade head` (Phase 3.5)

### "Cannot start bot — missing config or credentials"
- This 400 from `/api/bot/start` means the user has not saved CoinDCX credentials yet
- Send the user to `/settings` (or `/onboarding`) to paste their CoinDCX API key + secret
- The Save button only succeeds after a live `fetch_balance` call returns 200, so a successful save = working keys

### Frontend shows "Offline" badge
- WebSocket connection failed
- Check `NEXT_PUBLIC_WS_URL` uses `wss://` not `ws://`
- Check backend CORS includes your Vercel URL
- Open browser DevTools → Network → WS tab to see the error

### "401 Unauthorized" on every API call
- Clerk JWT not reaching backend
- Verify `CLERK_JWKS_URL` is correct on Railway
- Try signing out and back in on the dashboard

### Bot is running but no trades happen
- Normal in the first hours — momentum signals need time to develop
- Check Railway logs for `SCAN COMPLETE` lines every 5 minutes
- View the **Signals** page — if all coins show low scores, market conditions are weak

### Telegram alerts not arriving
- Make sure you sent at least one message to your bot first (Telegram requirement)
- Verify `TELEGRAM_CHAT_ID` is your numeric ID (from @userinfobot), not a username

### Railway free credit running low
- Check **Usage** tab — a paper-trading bot typically uses ₹40–100 worth of credits/month
- Free tier provides $5/month, more than enough for this app

---

## Maintenance

### Redeploying after code changes

```bash
git add .
git commit -m "describe your change"
git push
```

Railway and Vercel both auto-deploy on push to `main`.

### Adding more users

Two paths:

- **Self-serve:** if your Clerk app allows public sign-ups (default), share the
  Vercel URL. Anyone can sign up, will land on `/onboarding`, paste their own
  CoinDCX/Telegram keys, and start their own bot.
- **Invite-only:** Clerk Dashboard → **Users → Invite User** → enter their
  email. They get a sign-up link and the same onboarding flow.

Each user is fully isolated:
- Their CoinDCX/Telegram keys are encrypted with their own per-account DEK
- Their trades, positions, and P&L are scoped to their `clerk_user_id`
- Their bot starts/stops/mode-toggles independently from yours

### Running migrations after a code update

If a future change adds a new Alembic revision, run it once against the same
Supabase DB you set up in step 1.7:

```bash
cd backend
export DATABASE_URL='<your supabase pooler URL>'
alembic upgrade head
```

Railway redeploys do **not** run migrations automatically — this is intentional
to avoid concurrent-migration race conditions across deployments.

### Rotating the master encryption key

If you suspect `MASTER_ENCRYPTION_KEY` has leaked or you want to rotate
proactively:

1. Generate a new key with the Phase 3.3 command
2. Set `MASTER_ENCRYPTION_KEY_PREVIOUS=<the old key>` and
   `MASTER_ENCRYPTION_KEY=<the new key>` on Railway
3. Redeploy — every decrypt now tries the new key first, then falls back to
   the old. Existing data keeps working without re-encryption
4. (Recommended once rotation is verified) write a small one-shot script that
   iterates `users` and calls `CredentialVault.rewrap_dek(wrapped_dek, dek_nonce)`
   for each row, then writes the new wrapped values back. After it completes:
5. **Remove** `MASTER_ENCRYPTION_KEY_PREVIOUS` from Railway and redeploy. The
   old key is now untrusted; if it leaks later, no ciphertext is recoverable

### Stopping the bot

Railway → service → **⋮ menu → Pause Deployment**
Resume the same way when ready.

---

## Cost expectations

| Service | Cost (steady-state) |
|---|---|
| Railway | ~$0.50–$1.00/month (well within $5 free credit) |
| Vercel | ₹0 — free tier covers this entirely |
| Clerk | ₹0 — free tier covers up to 10,000 monthly active users |
| Supabase | ₹0 — free tier (500 MB Postgres) easily handles thousands of users + trades |
| Everything else | ₹0 — all free tiers |

**Effective monthly cost: ₹0** (assuming you stay within Railway's free credit, which is very likely).
