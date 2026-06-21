"""
Capital-allocation API.

    GET  /api/allocation          → current split + per-bucket equity/PnL/drawdown
    POST /api/allocation          → set total USDT + day/long split (rebuilds bot)
    POST /api/allocation/pause     → pause the allocation (bot stops new entries)
    POST /api/allocation/resume    → resume
    POST /api/allocation/confirm-shift → apply a suggested day/long split

The bot trades freely within each bucket's budget and never withdraws profit —
gains compound inside the bucket. Funds are not moved between buckets unless the
user confirms a shift here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from src.api.deps import get_current_user
from src.db import repositories as repo
from src.db.engine import session_scope
from src.db.models import User
from src.trading.allocation import DAY, LONG

router = APIRouter(prefix="/api/allocation", tags=["allocation"])


class AllocationIn(BaseModel):
    total: float = Field(gt=0, description="Total USDT to allocate to the bot")
    day_pct: float = Field(ge=0, le=100, default=30)
    allocate_all: bool = False


class ShiftIn(BaseModel):
    day_pct: float = Field(ge=0, le=100)


def _orch(request: Request):
    return request.app.state.orchestrator


def _reload(request: Request, user_id: str) -> None:
    """Rebuild the running bot so it picks up the new allocation."""
    orch = _orch(request)
    try:
        if orch.is_running(user_id):
            orch.stop(user_id)
            orch.start(user_id)
    except Exception:
        pass


@router.get("")
async def get_allocation(request: Request,
                         user: Annotated[User, Depends(get_current_user)]):
    uid = user.clerk_user_id
    with session_scope() as db:
        alloc = repo.get_allocation(db, uid)
        states = {s.bucket: s for s in repo.get_bucket_states(db, uid)}
        if alloc is None:
            return {"allocated": False}
        out = {
            "allocated": True,
            "total_allocated": float(alloc.total_allocated),
            "allocate_all": bool(alloc.allocate_all),
            "status": alloc.status,
            "buckets": {},
        }
        budgets = {DAY: float(alloc.day_budget), LONG: float(alloc.long_budget)}

    # Live equity from the running bot's book (best-effort).
    state = _orch(request).get_state(uid)
    with state.lock:
        prices = dict(state.current_prices)
        paper = state.paper_trader
        for b, budget in budgets.items():
            realized = float(states[b].realized_pnl) if b in states else 0.0
            deployed = paper.deployed_in(b) if paper else 0.0
            unrealized = paper.unrealized_in(b, prices) if paper else 0.0
            capital = budget + realized
            out["buckets"][b] = {
                "budget": round(budget, 2),
                "realized_pnl": round(realized, 2),
                "deployed": round(deployed, 2),
                "available": round(max(0.0, capital - deployed), 2),
                "equity": round(capital + unrealized, 2),
                "drawdown_state": states[b].drawdown_state if b in states else "normal",
            }
    return out


@router.post("")
async def set_allocation(body: AllocationIn, request: Request,
                         user: Annotated[User, Depends(get_current_user)]):
    day_budget = round(body.total * body.day_pct / 100.0, 2)
    long_budget = round(body.total - day_budget, 2)
    with session_scope() as db:
        repo.upsert_allocation(
            db, user_id=user.clerk_user_id, total=body.total,
            day_budget=day_budget, long_budget=long_budget,
            allocate_all=body.allocate_all, status="active",
        )
    _reload(request, user.clerk_user_id)
    return {"ok": True, "day_budget": day_budget, "long_budget": long_budget}


@router.post("/pause")
async def pause_allocation(request: Request,
                           user: Annotated[User, Depends(get_current_user)]):
    with session_scope() as db:
        repo.set_allocation_status(db, user.clerk_user_id, "paused")
    _reload(request, user.clerk_user_id)
    return {"ok": True, "status": "paused"}


@router.post("/resume")
async def resume_allocation(request: Request,
                            user: Annotated[User, Depends(get_current_user)]):
    with session_scope() as db:
        repo.set_allocation_status(db, user.clerk_user_id, "active")
    _reload(request, user.clerk_user_id)
    return {"ok": True, "status": "active"}


@router.post("/confirm-shift")
async def confirm_shift(body: ShiftIn, request: Request,
                        user: Annotated[User, Depends(get_current_user)]):
    """Apply a suggested day/long split to the existing total. The bot won't
    force-liquidate; the new split just governs future entries per bucket."""
    uid = user.clerk_user_id
    with session_scope() as db:
        alloc = repo.get_allocation(db, uid)
        if alloc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no_allocation")
        total = float(alloc.total_allocated)
        day_budget = round(total * body.day_pct / 100.0, 2)
        long_budget = round(total - day_budget, 2)
        repo.upsert_allocation(
            db, user_id=uid, total=total, day_budget=day_budget,
            long_budget=long_budget, allocate_all=bool(alloc.allocate_all),
            status="active",
        )
    _reload(request, uid)
    return {"ok": True, "day_budget": day_budget, "long_budget": long_budget}
