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
from src.db import repositories as repo
from src.db.engine import session_scope
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


_LIVE_GUARD_DETAIL = (
    "You have live-trading order history. Trades and positions can't be "
    "separated by mode, so clearing paper data would also destroy live "
    "records. Wipe refused — nothing was deleted."
)


def _try_restart(orch, user_id: str) -> None:
    """Best-effort bot restore when the wipe aborted (mirror of allocation._reload)."""
    try:
        orch.start(user_id)
    except Exception:
        log.exception("Failed to restart bot after aborted wipe for %s", user_id[:8])


@router.delete("/paper-data")
async def clear_paper_data(request: Request,
                           user: Annotated[User, Depends(get_current_user)]):
    """
    Wipe the user's paper-trading history: all trades, open positions,
    paper-mode orders, and bucket P&L state. Credentials, bot config and
    allocation are kept. If the bot is running it is stopped, the data wiped,
    and the bot restarted so the in-memory paper book rebuilds from the
    now-empty DB.
    """
    uid = user.clerk_user_id
    orch = _orch(request)

    # Fast-fail guard before touching the bot (no side effects on 409).
    with session_scope() as db:
        if repo.count_live_orders(db, uid) > 0:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=_LIVE_GUARD_DETAIL)

    was_running = orch.is_running(uid)
    if was_running:
        try:
            orch.stop(uid)
        except Exception:
            log.exception("Failed to stop bot before wipe for %s", uid[:8])
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not stop the bot — no data was deleted. Try again.",
            )

    try:
        with session_scope() as db:
            # Re-check inside the delete transaction now the worker is stopped.
            if repo.count_live_orders(db, uid) > 0:
                raise HTTPException(status.HTTP_409_CONFLICT, detail=_LIVE_GUARD_DETAIL)
            deleted = repo.clear_paper_data(db, uid)
    except HTTPException:
        if was_running:
            _try_restart(orch, uid)  # data untouched — put the bot back
        raise
    except Exception:
        log.exception("Paper-data wipe failed for %s", uid[:8])
        if was_running:
            _try_restart(orch, uid)  # transaction rolled back — restore the bot
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear data due to a server error. Nothing was deleted.",
        )

    restarted, warning = False, None
    if was_running:
        try:
            restarted = orch.start(uid)
        except BotStartError as exc:
            warning = f"Data was cleared, but the bot could not restart: {exc}"
        except Exception:
            log.exception("Restart after wipe failed for %s", uid[:8])
        if not restarted and warning is None:
            warning = ("Data was cleared, but the bot could not restart. "
                       "Start it manually from the dashboard.")

    return {
        "ok": True,
        "deleted": deleted,
        "was_running": was_running,
        "bot_restarted": restarted,
        "warning": warning,
    }


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
