# CLAUDE.md — Monorepo Root

## Project Overview

**CrypSavvy** — autonomous, multi-tenant crypto trading bot with a web dashboard.
Trades **USDT-quoted pairs** (BTC/USDT, ETH/USDT, …) on **CoinDCX**. Users allocate
USDT split across a **day-trading** and a **long-term** bucket; a regime-aware
strategy ensemble trades within each bucket's budget, with ATR-based stops,
fractional-Kelly sizing, and per-bucket drawdown circuit-breakers. Live trading is
hard-gated behind a backtest + paper-trading validation step.

```
crypsavvy/
├── backend/    Python bot + scanner + FastAPI server (deploys to Fly.io, Mumbai; fly.toml)
├── frontend/   Next.js 14 dashboard (deploys to Vercel)
├── deploy/     Deploy guides — Fly.io (primary), self-hosted OCI/EC2 VM (alt),
│               and VALIDATION-RUNBOOK.md (the gate before live trading)
└── .gitignore  Covers both projects
```

Each sub-project has its own `CLAUDE.md` with full detail.
**Always read the relevant sub-project CLAUDE.md before making changes.**

## Quick Start

```bash
# Backend
cd backend && pip install -r requirements.txt
cp .env.example .env   # fill in keys
python src/runner.py

# Frontend (separate terminal)
cd frontend && npm install
cp .env.example .env.local   # fill in keys
npm run dev    # http://localhost:3000
```

## Deployment

| Project  | Platform | Notes |
|---|---|---|
| `backend/` | **Fly.io** (Mumbai `bom`) | Config in [backend/fly.toml](backend/fly.toml); `fly-deploy.yml` auto-deploys on push. Guide: [deploy/FLY-SETUP-GUIDE.md](deploy/FLY-SETUP-GUIDE.md). Self-hosted VM alternative: [deploy/README.md](deploy/README.md) |
| `frontend/` | Vercel   | Set **Root Directory = `frontend`** in project settings |

Both deploy from the same GitHub repo on push to `main`: the backend via the Fly deploy workflow, the frontend via Vercel's Git integration.

## .gitignore (root)

Covers both projects — `.env`, `data/`, `node_modules/`, `__pycache__/`, `.next/`.
