# CLAUDE.md — Monorepo Root

## Project Overview

**CrypSavvy** — autonomous crypto trading bot for the **Indian market** with a web dashboard.

```
crypsavvy/
├── backend/    Python trading bot + FastAPI server (deploys to Railway)
├── frontend/   Next.js 14 dashboard (deploys to Vercel)
└── .gitignore  Covers both projects
```

Each sub-project has its own `CLAUDE.md` with full detail.
**Always read the relevant sub-project CLAUDE.md before making changes.**

## Quick Start

```bash
# Backend
cd backend && pip install -r requirements.txt
cp .env.example .env   # fill in keys
python src/bot.py

# Frontend (separate terminal)
cd frontend && npm install
cp .env.example .env.local   # fill in keys
npm run dev    # http://localhost:3000
```

## Deployment

| Project  | Platform | Root Directory setting |
|---|---|---|
| `backend/` | Railway   | Set **Root Directory = `backend`** in service settings |
| `frontend/` | Vercel   | Set **Root Directory = `frontend`** in project settings |

Both deployments pull from the same GitHub repo.

## .gitignore (root)

Covers both projects — `.env`, `data/`, `node_modules/`, `__pycache__/`, `.next/`.
