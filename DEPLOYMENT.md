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
        ▲                                                     │
        │                                              ┌──────┴───────┐
        │                                              ▼              ▼
   ┌────┴─────┐                                  ┌─────────┐    ┌──────────┐
   │  Clerk   │                                  │ CoinDCX │    │CryptoPan.│
   │  Auth    │                                  │ exchange│    │Reddit/TG │
   └──────────┘                                  └─────────┘    └──────────┘
```

> **Monorepo note:** backend and frontend live in the same GitHub repo. Vercel and Railway both handle this cleanly via their **Root Directory** setting (`frontend` for Vercel, `backend` for Railway). Each platform builds only its subdirectory and ignores the other. By default, both rebuild on every push to `main` — see the optional optimization tips in Phase 3.2 (Railway Watch Paths) and Phase 4.1 (Vercel Ignored Build Step) to skip rebuilds when only the other project changed.

You will need **8 free accounts**:

| # | Service | Purpose | Cost |
|---|---|---|---|
| 1 | GitHub | Source code hosting | Free |
| 2 | CoinDCX | Crypto exchange (live trading only) | Free + KYC |
| 3 | CryptoPanic | News sentiment data | Free |
| 4 | Reddit | Community sentiment data | Free |
| 5 | Telegram | Trade alerts | Free |
| 6 | Clerk | User authentication | Free tier |
| 7 | Railway | Backend hosting | $5/month free credit |
| 8 | Vercel | Frontend hosting | Free |

---

## Phase 1 — Get all the credentials

### 1.1 GitHub

1. Sign up at [github.com](https://github.com) if you don't have an account
2. Create a **new repository** called `cryp-savvy` (private is fine)
3. Don't initialise with README — we'll push the existing code

### 1.2 CoinDCX (only needed when going live)

1. Sign up at [coindcx.com](https://coindcx.com)
2. Complete **KYC** (PAN + Aadhaar) — takes 1–3 business days
3. Once verified: **Profile → API Dashboard → Create New API Key**
4. Save **API Key** and **API Secret** — you won't see the secret again
5. Restrict the key to **trading + read** (not withdrawals)

> **Skip this for now** if you're only doing paper trading. The bot works fully in paper mode without CoinDCX credentials.

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

### 1.5 Telegram (for trade alerts)

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

### 1.7 Railway

1. Sign up at [railway.app](https://railway.app) using your GitHub account
2. Authorize Railway to access your GitHub repos
3. (No credit card needed for the free tier)

### 1.8 Vercel

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

### 3.3 Add environment variables

Go to the **Variables** tab → **+ New Variable** and add each of these:

```
MODE=paper

CRYPTOPANIC_API_KEY=<from step 1.3>

REDDIT_CLIENT_ID=<from step 1.4>
REDDIT_CLIENT_SECRET=<from step 1.4>
REDDIT_USER_AGENT=crypto_bot/1.0 by <your_reddit_username>

TELEGRAM_BOT_TOKEN=<from step 1.5>
TELEGRAM_CHAT_ID=<from step 1.5>

CLERK_JWKS_URL=<from step 1.6>

API_CORS_ORIGINS=http://localhost:3000
# Note: we'll add the Vercel URL to this AFTER deploying the frontend
```

Skip CoinDCX vars for now (paper mode).

### 3.4 Redeploy

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
2. Sign up with email or Google → you'll land on `/dashboard`
3. The dashboard should show:
   - **Live** badge in top-left (means WebSocket is connected)
   - **RUNNING · PAPER** badge
   - Stat cards with `₹10,000.00` balance
   - "Awaiting first scan…" — wait 5 minutes for the first scan to complete
4. Check Telegram — you should have received a "CrypSavvy Started" message
5. After 5 minutes, the dashboard refreshes with signals; over hours/days you'll see trades

---

## Phase 6 — Going live (only after 1–2 weeks of paper trading)

> ⚠️ **Do not skip the paper trading phase.** Validate that the bot is profitable before risking real money.

1. Add CoinDCX credentials to Railway env vars:
   ```
   COINDCX_API_KEY=<from step 1.2>
   COINDCX_API_SECRET=<from step 1.2>
   ```
2. Add a **persistent volume** so trade history survives redeploys:
   - Railway service → **Settings → Volumes → + New Volume**
   - Mount path: `/app/data`
   - Size: 1 GB (free tier limit)
3. Change `MODE` from `paper` to `live`
4. Start with **half** your capital — keep the rest in reserve
5. Watch the dashboard daily for the first week

---

## Troubleshooting

### Backend won't start on Railway
- Check **Deployments → View Logs**
- Common cause: missing env var → Variables tab → add the missing one

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

Clerk Dashboard → **Users → Invite User** → enter their email.
They'll get a sign-up link and can immediately access your dashboard.

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
| Everything else | ₹0 — all free tiers |

**Effective monthly cost: ₹0** (assuming you stay within Railway's free credit, which is very likely).
