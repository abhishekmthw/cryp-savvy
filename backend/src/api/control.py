"""
Bot control router.
Endpoints to start, stop, and switch the per-user bot's paper/live mode.

The orchestrator lives on ``app.state.orchestrator`` (set in ``main.py``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from config import settings
from src.api.deps import get_current_user
from src.bot.errors import BotStartError
from src.db.models import User
from src.monitoring.logger import get_logger


log = get_logger()

router = APIRouter(prefix="/api/bot", tags=["bot"])


class ModeIn(BaseModel):
    mode:    str
    confirm: str | None = None


def _orch(request: Request):
    return request.app.state.orchestrator


@router.post("/start")
async def start_bot(request: Request,
                    user: Annotated[User, Depends(get_current_user)]):
    try:
        ok = _orch(request).start(user.clerk_user_id)
    except BotStartError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except Exception:
        log.exception("Unexpected error starting bot for %s", user.clerk_user_id[:8])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start the bot due to a server error.",
        )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot start bot — missing config or credentials",
        )
    return {"ok": True, "is_running": True}


@router.post("/stop")
async def stop_bot(request: Request,
                   user: Annotated[User, Depends(get_current_user)]):
    _orch(request).stop(user.clerk_user_id)
    return {"ok": True, "is_running": False}


@router.put("/mode")
async def set_mode(body: ModeIn, request: Request,
                   user: Annotated[User, Depends(get_current_user)]):
    if body.mode not in ("paper", "live"):
        raise HTTPException(400, detail="mode must be 'paper' or 'live'")
    if body.mode == "live":
        # Hard validation gate — operator must enable live trading explicitly
        # (after the backtest + paper-trade validation in the runbook).
        if not settings.LIVE_TRADING_ENABLED:
            raise HTTPException(
                403,
                detail="Live trading is disabled on this deployment until "
                       "validation is complete (set LIVE_TRADING_ENABLED=true).",
            )
        if body.confirm != "I_ACCEPT_LIVE_RISK":
            raise HTTPException(
                400,
                detail="Switching to live trading requires confirm='I_ACCEPT_LIVE_RISK'",
            )
    try:
        _orch(request).set_mode(user.clerk_user_id, body.mode)
    except BotStartError as exc:
        # Mode switch restarts the bot, which can hit the same decryption failure.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except Exception:
        log.exception("Unexpected error switching mode for %s", user.clerk_user_id[:8])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to switch mode due to a server error.",
        )
    return {"ok": True, "mode": body.mode}
