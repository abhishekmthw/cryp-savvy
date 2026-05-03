"""
FastAPI application.
Runs in a daemon thread alongside the trading bot loop.
Exposes REST endpoints + a WebSocket for real-time events.
"""

import asyncio
import json
import time
import queue as _queue
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from config import settings
from src.api.state import BotState
from src.api.auth import verify_clerk_token


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard if False else None
        try:
            self._connections.remove(ws)
        except ValueError:
            pass

    async def broadcast(self, message: str):
        dead = []
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# ── App factory ───────────────────────────────────────────────────────────────

def create_app(bot_state: BotState) -> FastAPI:
    manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Background task: drain bot event queue → broadcast to WebSocket clients
        async def _drain():
            while True:
                try:
                    event = bot_state.event_queue.get_nowait()
                    await manager.broadcast(json.dumps(event))
                except _queue.Empty:
                    await asyncio.sleep(0.1)
                except Exception:
                    await asyncio.sleep(0.5)

        task = asyncio.create_task(_drain())
        yield
        task.cancel()

    app = FastAPI(title="CrypSavvy API", lifespan=lifespan)

    # CORS — allow the frontend origin(s) configured via env
    origins = [o.strip() for o in settings.API_CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # ── Auth dependency ───────────────────────────────────────────────────────

    _bearer = HTTPBearer(auto_error=True)

    async def get_user(
        creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)]
    ) -> dict:
        return await verify_clerk_token(creds.credentials)

    # ── REST routes ───────────────────────────────────────────────────────────

    @app.get("/api/status")
    async def get_status(user: dict = Depends(get_user)):
        with bot_state.lock:
            return {
                "is_running":       bot_state.is_running,
                "mode":             settings.MODE,
                "last_scan_time":   bot_state.last_scan_time,
                "open_positions":   bot_state.paper_trader.open_position_count if bot_state.paper_trader else 0,
                "daily_limit_hit":  bot_state.paper_trader.is_daily_limit_hit if bot_state.paper_trader else False,
                "daily_pnl":        round(bot_state.paper_trader.daily_pnl, 2) if bot_state.paper_trader else 0,
            }

    @app.get("/api/portfolio")
    async def get_portfolio(user: dict = Depends(get_user)):
        with bot_state.lock:
            summary = bot_state.paper_trader.summary(bot_state.current_prices)
            stats   = bot_state.portfolio.stats()
        return {"summary": summary, "stats": stats}

    @app.get("/api/portfolio/history")
    async def get_portfolio_history(user: dict = Depends(get_user)):
        history = bot_state.portfolio.pnl_history()
        return {"history": history}

    @app.get("/api/positions")
    async def get_positions(user: dict = Depends(get_user)):
        with bot_state.lock:
            positions = []
            for sym, pos in bot_state.paper_trader.positions.items():
                price = bot_state.current_prices.get(sym, pos.entry_price)
                upnl  = (price - pos.entry_price) / pos.entry_price * 100
                positions.append({
                    "symbol":           sym,
                    "entry_price":      pos.entry_price,
                    "current_price":    price,
                    "qty":              pos.qty,
                    "amount_inr":       pos.amount_inr,
                    "stop_loss":        pos.stop_loss,
                    "take_profit":      pos.take_profit,
                    "unrealised_pnl_pct": round(upnl, 2),
                    "entry_time":       pos.entry_time,
                })
        return {"positions": positions}

    @app.get("/api/trades")
    async def get_trades(
        limit:  int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        user: dict = Depends(get_user),
    ):
        trades = bot_state.portfolio.recent_trades(limit)
        return {"trades": trades, "total": bot_state.portfolio.stats()["total_trades"]}

    @app.get("/api/signals")
    async def get_signals(user: dict = Depends(get_user)):
        with bot_state.lock:
            signals   = list(bot_state.last_signals)
            last_scan = bot_state.last_scan_time
        return {"signals": signals, "last_scan_time": last_scan}

    # ── WebSocket ─────────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def ws_endpoint(
        websocket: WebSocket,
        token: str = Query(default=""),
    ):
        """
        Authenticate via ?token=<clerk_jwt> query param (standard for WebSockets
        since browsers cannot set custom headers on WS upgrades).
        """
        try:
            await verify_clerk_token(token)
        except HTTPException:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        await manager.connect(websocket)
        try:
            # Send current state snapshot immediately on connect
            with bot_state.lock:
                snapshot = {
                    "type": "snapshot",
                    "data": {
                        "mode":           settings.MODE,
                        "is_running":     bot_state.is_running,
                        "last_scan_time": bot_state.last_scan_time,
                    },
                }
            await websocket.send_text(json.dumps(snapshot))

            # Keep the connection open; the drain task pushes messages
            while True:
                await websocket.receive_text()   # ping/pong or ignore client messages

        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return app
