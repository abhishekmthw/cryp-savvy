"""
FastAPI application — multi-tenant.

Every route resolves the per-user state from the ``BotOrchestrator`` (which
lives on ``app.state.orchestrator``). The WebSocket binds each connected
socket to its Clerk user and only receives that user's events.
"""

from __future__ import annotations

import asyncio
import json
import queue as _queue
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import (
    Depends, FastAPI, HTTPException, Query, Request,
    WebSocket, WebSocketDisconnect, status,
)
from fastapi.middleware.cors import CORSMiddleware

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from config import settings
from src.api.auth import verify_clerk_token
from src.api.control import router as control_router
from src.api.credentials import router as credentials_router
from src.api.deps import get_current_user, get_vault
from src.bot.orchestrator import BotOrchestrator
from src.bot.scanner import MarketDataScanner
from src.db import repositories as repo
from src.db.engine import session_scope
from src.db.models import User
from src.security.crypto import CredentialVault


# ── WebSocket: per-user connection registry ──────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.setdefault(user_id, []).append(ws)

    async def disconnect(self, user_id: str, ws: WebSocket):
        async with self._lock:
            if user_id in self._connections:
                try:
                    self._connections[user_id].remove(ws)
                except ValueError:
                    pass
                if not self._connections[user_id]:
                    self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: str):
        sockets = list(self._connections.get(user_id, []))
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(user_id, ws)


# ── App factory ──────────────────────────────────────────────────────────────

def create_app(scanner: MarketDataScanner, orchestrator: BotOrchestrator) -> FastAPI:
    manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def _drain():
            while True:
                states = orchestrator.all_states()
                pushed = False
                for user_id, state in states.items():
                    try:
                        while True:
                            event = state.event_queue.get_nowait()
                            await manager.send_to_user(user_id, json.dumps(event))
                            pushed = True
                    except _queue.Empty:
                        pass
                    except Exception:
                        pass
                if not pushed:
                    await asyncio.sleep(0.2)

        task = asyncio.create_task(_drain())
        yield
        task.cancel()

    app = FastAPI(title="CrypSavvy API", lifespan=lifespan)
    app.state.scanner = scanner
    app.state.orchestrator = orchestrator

    origins = [o.strip() for o in settings.API_CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(credentials_router)
    app.include_router(control_router)

    # ── REST: per-user data ──────────────────────────────────────────────────

    @app.get("/api/status")
    async def get_status(user: Annotated[User, Depends(get_current_user)]):
        state = orchestrator.get_state(user.clerk_user_id)
        with state.lock:
            return {
                "is_running":      state.is_running,
                "mode":            state.mode,
                "last_scan_time":  state.last_scan_time,
                "open_positions":  state.paper_trader.open_position_count if state.paper_trader else 0,
                "daily_limit_hit": state.paper_trader.is_daily_limit_hit if state.paper_trader else False,
                "daily_pnl":       round(state.paper_trader.daily_pnl, 2) if state.paper_trader else 0,
            }

    @app.get("/api/portfolio")
    async def get_portfolio(user: Annotated[User, Depends(get_current_user)]):
        state = orchestrator.get_state(user.clerk_user_id)
        with state.lock:
            summary = state.paper_trader.summary(state.current_prices) if state.paper_trader else {}
        with session_scope() as db:
            stats = repo.trade_stats(db, user.clerk_user_id)
        return {"summary": summary, "stats": stats}

    @app.get("/api/portfolio/history")
    async def get_portfolio_history(user: Annotated[User, Depends(get_current_user)]):
        state = orchestrator.get_state(user.clerk_user_id)
        initial = state.paper_trader.initial_capital_inr if state.paper_trader else 10_000.0
        with session_scope() as db:
            history = repo.pnl_history_for_user(db, user.clerk_user_id, initial)
        return {"history": history}

    @app.get("/api/positions")
    async def get_positions(user: Annotated[User, Depends(get_current_user)]):
        state = orchestrator.get_state(user.clerk_user_id)
        with state.lock:
            positions = []
            if state.paper_trader is None:
                return {"positions": positions}
            for sym, pos in state.paper_trader.positions.items():
                price = state.current_prices.get(sym, pos.entry_price)
                upnl  = (price - pos.entry_price) / pos.entry_price * 100
                positions.append({
                    "symbol":             sym,
                    "entry_price":        pos.entry_price,
                    "current_price":      price,
                    "qty":                pos.qty,
                    "amount_inr":         pos.amount_inr,
                    "stop_loss":          pos.stop_loss,
                    "take_profit":        pos.take_profit,
                    "unrealised_pnl_pct": round(upnl, 2),
                    "entry_time":         pos.entry_time,
                })
        return {"positions": positions}

    @app.get("/api/trades")
    async def get_trades(
        user: Annotated[User, Depends(get_current_user)],
        limit:  int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        with session_scope() as db:
            trades = repo.trades_for_user(db, user.clerk_user_id, limit=limit, offset=offset)
            stats  = repo.trade_stats(db, user.clerk_user_id)
        return {"trades": trades, "total": stats["total_trades"]}

    @app.get("/api/signals")
    async def get_signals(user: Annotated[User, Depends(get_current_user)]):
        state = orchestrator.get_state(user.clerk_user_id)
        with state.lock:
            signals   = list(state.last_signals)
            last_scan = state.last_scan_time
        return {"signals": signals, "last_scan_time": last_scan}

    # ── WebSocket: bound to a user ───────────────────────────────────────────

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket, token: str = Query(default="")):
        try:
            payload = await verify_clerk_token(token)
        except HTTPException:
            await websocket.close(code=4001, reason="Unauthorized")
            return
        sub = payload.get("sub")
        if not sub:
            await websocket.close(code=4001, reason="Missing subject")
            return

        # Lazy-create a User row from the JWT — same code path as get_current_user
        vault = get_vault()
        with session_scope() as db:
            email = payload.get("email")
            user = repo.get_user_or_create(
                db, clerk_user_id=sub, email=email, vault=vault,
            )
            user_id = user.clerk_user_id

        await manager.connect(user_id, websocket)
        try:
            state = orchestrator.get_state(user_id)
            snapshot = {
                "type": "snapshot",
                "data": {
                    "mode":           state.mode,
                    "is_running":     state.is_running,
                    "last_scan_time": state.last_scan_time,
                },
            }
            await websocket.send_text(json.dumps(snapshot))

            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect(user_id, websocket)

    return app
