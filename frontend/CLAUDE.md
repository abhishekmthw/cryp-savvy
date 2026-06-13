# CLAUDE.md — frontend/

## What this is

Next.js 14 (App Router) dashboard for **CrypSavvy**.
Authentication via **Clerk**. Real-time data via **WebSocket** + **TanStack Query**.
Deploys to **Vercel** (set Root Directory = `frontend`).

---

## Architecture

```
app/
  layout.tsx                    Root layout — ClerkProvider + Providers
  (auth)/
    sign-in/[[...sign-in]]/     Clerk sign-in page (public)
    sign-up/[[...sign-up]]/     Clerk sign-up page (public)
  (dashboard)/                  Route group — shared Sidebar+Navbar layout, no URL prefix
    layout.tsx                  Protected layout — Sidebar + Navbar
    page.tsx                    Main dashboard at /   (stat cards, positions, chart, feeds)
    trades/page.tsx             Full trade history table at /trades
    signals/page.tsx            Full signal scanner table at /signals
    settings/page.tsx           Per-user credentials + bot config at /settings
    onboarding/page.tsx         First-run setup wizard at /onboarding
components/
  providers.tsx                 QueryClientProvider (client component)
  layout/
    sidebar.tsx                 Left nav (Dashboard / Trades / Signals)
    navbar.tsx                  Top bar — BotStatus + Clerk UserButton
  dashboard/
    bot-status.tsx              Running indicator + WS connection badge
    stat-cards.tsx              Balance, portfolio value, total P&L, daily P&L
    positions-table.tsx         Live open positions with unrealised P&L
    pnl-chart.tsx               Portfolio value area chart (Recharts)
    trades-feed.tsx             Last 10 trades widget
    live-events.tsx             Real-time WebSocket event feed
    signals-table.tsx           Top 6 signals widget
    full-trades-table.tsx       Paginated trade history (Trades page)
    full-signals-table.tsx      All signals with score bars (Signals page)
hooks/
  use-api.ts                    React Query hooks for every API endpoint
  use-websocket.ts              WebSocket connection + query invalidation
lib/
  api.ts                        Typed fetch client — all API calls live here
  ws.ts                         WebSocket factory with auto-reconnect
  utils.ts                      cn(), formatINR(), formatPct(), formatTs()
middleware.ts                   Clerk auth middleware — protects /dashboard/*
```

---

## Running locally

```bash
npm install
cp .env.example .env.local   # fill in Clerk keys + backend URL
npm run dev                  # http://localhost:3000
```

The backend must be running at `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000`).

---

## Environment Variables (`.env.local`)

| Variable | Required | Notes |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Yes | From Clerk Dashboard → API Keys |
| `CLERK_SECRET_KEY` | Yes | Server-side Clerk key |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | Yes | `/sign-in` |
| `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | Yes | `/sign-up` |
| `NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL` | Yes | `/dashboard` |
| `NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL` | Yes | `/dashboard` |
| `NEXT_PUBLIC_API_URL` | Yes | Backend URL (`https://api.<domain>` in prod, via Cloudflare Tunnel) |
| `NEXT_PUBLIC_WS_URL` | Yes | WebSocket URL (`wss://` in prod) |

---

## Authentication Flow

```
User visits /dashboard
  → middleware.ts checks Clerk session
  → Not signed in → redirect to /sign-in
  → Clerk issues session + JWT
  → Dashboard loads

API calls (lib/api.ts):
  → useAuth().getToken() → Clerk JWT
  → fetch(API_URL + path, { Authorization: Bearer <jwt> })
  → Python backend verifies JWT via JWKS

WebSocket (lib/ws.ts):
  → wss://backend/ws?token=<clerk_jwt>
  → Python backend verifies token on connect
```

---

## Data Flow

```
React Query (30s polling) ←──── REST API (portfolio, positions, trades, signals)
                                       ↑
                             Clerk JWT on every request

WebSocket events ──────────────────→ invalidate React Query cache
  scan_complete  → invalidates signals, status
  trade_buy/sell → invalidates portfolio, positions, trades, portfolioHistory
```

---

## Vercel Deployment

1. Push repo to GitHub
2. Vercel → New Project → Import Git repo
3. Framework Preset: **Next.js** (auto-detected)
4. **Root Directory = `frontend`**
5. Add all env vars from `.env.example` in the Environment Variables section
6. Deploy

After deploy, update `API_CORS_ORIGINS` in the backend's `.env` on the OCI VM
to include the Vercel URL (e.g. `https://crypsavvy-dashboard.vercel.app`), then
`docker compose up -d` to apply. See [../deploy/README.md](../deploy/README.md).

---

## Adding a New Page

1. Create `app/(dashboard)/new-page/page.tsx`
2. Add a nav entry in `components/layout/sidebar.tsx`
3. Add the API call to `lib/api.ts` and a hook to `hooks/use-api.ts`

## Adding a New API Endpoint

1. Add the typed response interface in `lib/api.ts`
2. Add the fetch function to the `api` object in `lib/api.ts`
3. Add a `useXxx()` hook in `hooks/use-api.ts`
4. Use the hook in a component

---

## Warnings

- Never commit `.env.local` — it contains real Clerk keys
- `NEXT_PUBLIC_*` vars are embedded in the browser bundle — never put secrets there
- Always use `wss://` (not `ws://`) for WebSocket in production
