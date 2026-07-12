"""
Diagnostics router.

GET /api/portfolio/diagnostics          — aggregation behind the /diagnostics page
GET /api/portfolio/diagnostics/export   — self-describing export report
                                          (?format=markdown|json, default markdown)

The markdown export is the "paste into Claude Code" artifact: config snapshot,
edge metrics, planned-vs-realized R:R, MAE/MFE, churn, breakdowns, per-trade
CSV log, and a machine-readable JSON appendix.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from src.api.deps import get_current_user
from src.db import repositories as repo
from src.db.engine import session_scope
from src.db.models import User
from src.monitoring import report as report_builder

router = APIRouter(prefix="/api/portfolio", tags=["diagnostics"])


def _orch(request: Request):
    return request.app.state.orchestrator


def _paper_snapshot(request: Request, user_id: str) -> tuple[float, int]:
    """(initial_capital, open_position_count) from the user's paper book."""
    state = _orch(request).get_state(user_id)
    with state.lock:
        if state.paper_trader is None:
            return 10_000.0, 0
        return (state.paper_trader.initial_capital_usdt,
                state.paper_trader.open_position_count)


@router.get("/diagnostics")
async def get_portfolio_diagnostics(
    request: Request, user: Annotated[User, Depends(get_current_user)]
):
    """Loss-attribution breakdown of closed trades — powers the /diagnostics
    dashboard. Read-only aggregation over the trades table."""
    initial, _ = _paper_snapshot(request, user.clerk_user_id)
    with session_scope() as db:
        diagnostics = repo.trade_diagnostics(db, user.clerk_user_id, initial)
    return diagnostics


@router.get("/diagnostics/export")
async def export_diagnostics(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    format: str = Query(default="markdown", pattern="^(markdown|json)$"),
):
    initial, open_positions = _paper_snapshot(request, user.clerk_user_id)

    with session_scope() as db:
        diagnostics = repo.trade_diagnostics(db, user.clerk_user_id, initial)
        trades = repo.trades_full_for_export(db, user.clerk_user_id)
        cfg_row = repo.get_bot_config(db, user.clerk_user_id)
        alloc_row = repo.get_allocation(db, user.clerk_user_id)

        user_cfg = {}
        if cfg_row is not None:
            user_cfg = {
                "initial_capital_usdt":  float(cfg_row.initial_capital_usdt),
                "max_position_usdt":     float(cfg_row.max_position_usdt),
                "max_open_positions":    int(cfg_row.max_open_positions),
                "stop_loss_pct":         float(cfg_row.stop_loss_pct),
                "take_profit_pct":       float(cfg_row.take_profit_pct),
                "trailing_stop_trigger": float(cfg_row.trailing_stop_trigger),
                "trailing_stop_offset":  float(cfg_row.trailing_stop_offset),
                "daily_loss_limit_usdt": float(cfg_row.daily_loss_limit_usdt),
            }
        alloc_cfg = {}
        if alloc_row is not None:
            alloc_cfg = {
                "total_allocated": float(alloc_row.total_allocated),
                "day_budget":      float(alloc_row.day_budget),
                "long_budget":     float(alloc_row.long_budget),
                "allocate_all":    bool(alloc_row.allocate_all),
                "status":          alloc_row.status,
            }
        mode = user.mode

    now = time.time()
    first_ts = trades[0].get("entry_ts") if trades else None
    last_ts = trades[-1].get("exit_ts") if trades else None
    period_days = ((last_ts - first_ts) / 86_400.0
                   if first_ts and last_ts and last_ts > first_ts else 0.0)
    meta = {
        "generated_at":         now,
        "mode":                 mode,
        "period_start_ts":      first_ts,
        "period_end_ts":        last_ts,
        "period_days":          round(period_days, 1),
        "trade_count":          diagnostics.get("total_trades", 0),
        "open_positions":       open_positions,
        "initial_capital_usdt": initial,
        "schema_version":       report_builder.REPORT_SCHEMA_VERSION,
    }
    config = {
        "settings":   report_builder.settings_snapshot(),
        "user":       user_cfg,
        "allocation": alloc_cfg,
    }

    if format == "json":
        return {
            "schema_version": report_builder.REPORT_SCHEMA_VERSION,
            "meta":           meta,
            "config":         config,
            "diagnostics":    diagnostics,
            "trades":         trades,
        }

    md = report_builder.build_markdown_report(
        diagnostics=diagnostics, config=config, trades=trades, meta=meta,
    )
    date_str = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")
    return PlainTextResponse(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="crypsavvy-diagnostics-{date_str}.md"'},
    )
