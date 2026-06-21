# CLAUDE.md — frontend/

## What this is

Next.js 14 (App Router) dashboard for **CrypSavvy**.
Authentication via **Clerk**. Real-time data via **WebSocket** + **TanStack Query**.
All money is shown in **USDT** (`formatUSD`). Deploys to **Vercel** (Root Directory = `frontend`).

---

## Architecture

```
app/
  layout.tsx                    Root layout — ClerkProvider + Providers
  (auth)/
    sign-in/[[...sign-in]]/     Clerk sign-in (public)
    sign-up/[[...sign-up]]/     Clerk sign-up (public)
  (dashboard)/                  Route group — shared Sidebar+Navbar, no URL prefix
    layout.tsx                  Protected layout (Sidebar + Navbar + OnboardingGuard)
    page.tsx                    Main dashboard at /
    trades/page.tsx             Full trade history at /trades
    signals/page.tsx            Full signal scanner at /signals
    settings/page.tsx           Per-user credentials + bot config at /settings
    settings/allocation/page.tsx  Capital allocation (day/long buckets) at /settings/allocation
    onboarding/page.tsx         First-run setup wizard at /onboarding
components/
  providers.tsx                 QueryClientProvider (client component)
  onboarding-guard.tsx          Redirects to /onboarding until CoinDCX creds exist
  layout/                       sidebar (Dashboard/Trades/Signals/Allocation/Settings), navbar, nav-items
  dashboard/
    bot-status.tsx              Running indicator + WS connection badge
    bot-controls.tsx            Start/stop + paper/live toggle (live = confirm dialog)
    stat-cards.tsx              Balance, portfolio value, total/daily P&L
    positions-table.tsx         Live open positions (current_price patched via WS)
    pnl-chart.tsx               Portfolio value area chart (Recharts)
    trades-feed.tsx             Last 10 trades
    live-events.tsx             Real-time WebSocket event feed
    signals-table.tsx           Top signals widget
    full-trades-table.tsx / full-signals-table.tsx
  settings/credential-section.tsx   CoinDCX/Telegram credential entry (masked)
  onboarding/coindcx-setup-guide.tsx
hooks/
  use-api.ts                    React Query hooks (incl. useAllocation + mutations)
  use-websocket.ts              WS connection + cache patching/invalidation
lib/
  api.ts                        Typed fetch client — all API calls + types
  ws.ts                         WebSocket factory: ticket handshake + reconnect w/ jitter
  utils.ts                      cn(), formatUSD(), formatPct(), formatQty(), formatTs()
middleware.ts                   Clerk auth middleware
```

---

## Running locally

```bash
npm install
cp .env.example .env.local   # Clerk keys + backend URL
npm run dev                  # http://localhost:3000
```

The backend must be running at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

---

## Environment Variables (`.env.local`)

| Variable | Required | Notes |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` | Yes | Clerk Dashboard → API Keys |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` / `SIGN_UP_URL` / `AFTER_*` | Yes | Auth routing |
| `NEXT_PUBLIC_API_URL` | Yes | Backend URL (`https://…fly.dev` in prod) |
| `NEXT_PUBLIC_WS_URL` | Yes | WebSocket URL (`wss://` in prod) |

`NEXT_PUBLIC_*` vars are embedded in the browser bundle — never put secrets there.

---

## Authentication Flow

```
REST: useAuth().getToken() → fetch(API_URL, { Authorization: Bearer <jwt> })
      backend verifies the JWT via Clerk JWKS.

WebSocket (lib/ws.ts):
  1. POST /api/ws/token  (with the Clerk JWT)  → single-use ticket
  2. open wss://backend/ws?ticket=<ticket>     ← JWT is NEVER put in the URL
  A fresh ticket is fetched before every (re)connect (tickets are single-use).
```

---

## Data Flow (real-time)

```
React Query (15s fallback polling) ←──── REST API (portfolio, positions, trades, signals, allocation)

WebSocket events:
  price_update    → setQueryData PATCHES ['positions']/['portfolio']/['status'] in place
                    (no refetch — live prices/P&L update instantly, exchange-style)
  trade_buy/sell  → invalidate portfolio, positions, trades, portfolioHistory
  scan_complete   → invalidate signals, status
  shift_suggestion / bucket_drawdown → surfaced in the live-events feed
```

Prefer **patching** the cache (`setQueryData`) for high-frequency events and
**invalidating** only for discrete ones. Polling is a fallback for when the WS drops.

---

## Vercel Deployment

1. Import the repo → Framework: **Next.js** → **Root Directory = `frontend`**.
2. Add all env vars from `.env.example`.
3. After deploy, add the Vercel URL to the backend's `API_CORS_ORIGINS`
   (`fly secrets set API_CORS_ORIGINS="…"`). See [../deploy/FLY-SETUP-GUIDE.md](../deploy/FLY-SETUP-GUIDE.md).

---

## Adding a New Page / Endpoint

- **Page**: `app/(dashboard)/<name>/page.tsx` → add a nav entry in `components/layout/nav-items.ts`.
- **Endpoint**: add the typed response + fetch fn in `lib/api.ts` → a `useXxx()` hook in
  `hooks/use-api.ts` → use it in a component.

---

## Warnings

- Never commit `.env.local`.
- Always use `wss://` (not `ws://`) for WebSocket in production.
- Allocating capital in **live** mode commits real USDT — the UI warns, and the
  backend hard-gates live mode until validation is complete.
