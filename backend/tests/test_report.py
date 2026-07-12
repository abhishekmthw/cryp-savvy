"""
Golden tests for the diagnostics export report builder
(src/monitoring/report.py) — structure, config snapshot hygiene, CSV log,
and the machine-readable JSON appendix.
"""

import json
import sys, os
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.models import Base, Trade
from src.db import repositories as repo
from src.monitoring import report


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


_ID = [1000]


def _add(db, **kw):
    _ID[0] += 1
    row = dict(id=_ID[0], user_id="u1", symbol="BTC/USDT", side="sell", ts=time.time())
    row.update(kw)
    db.add(Trade(**row))


def _build(db):
    now = time.time()
    _add(db, pnl=30, pnl_pct=3.0, reason="take_profit", bucket="day",
         strategy="donchian_breakout", regime="bull", amount_usdt=1000,
         duration_s=3600, ts=now - 7200, entry_ts=now - 10_800,
         entry_price=100.0, exit_price=103.0, qty=10.0,
         planned_stop_loss=98.0, planned_take_profit=103.0,
         mae_pct=-0.5, mfe_pct=3.5, fee_usdt=2.1, slippage_usdt=1.05)
    _add(db, pnl=-20, pnl_pct=-2.0, reason="stop_loss", bucket="day",
         strategy="donchian_breakout", regime="bull", amount_usdt=1000,
         duration_s=3600, ts=now, entry_ts=now - 3600,
         entry_price=100.0, exit_price=98.0, qty=10.0,
         planned_stop_loss=98.0, planned_take_profit=103.0,
         mae_pct=-2.2, mfe_pct=1.5, fee_usdt=2.0, slippage_usdt=1.0)
    _add(db, pnl=-5, pnl_pct=-0.5, reason="stop_loss", amount_usdt=500,
         duration_s=1800, ts=now - 86_400)
    db.flush()

    diagnostics = repo.trade_diagnostics(db, "u1", initial_capital=1000)
    trades = repo.trades_full_for_export(db, "u1")
    meta = {
        "generated_at": now, "mode": "paper",
        "period_start_ts": now - 86_400, "period_end_ts": now,
        "period_days": 1.0, "trade_count": diagnostics["total_trades"],
        "open_positions": 0, "initial_capital_usdt": 1000.0,
        "schema_version": report.REPORT_SCHEMA_VERSION,
    }
    config = {"settings": report.settings_snapshot(),
              "user": {"max_position_usdt": 200.0}, "allocation": {}}
    return report.build_markdown_report(
        diagnostics=diagnostics, config=config, trades=trades, meta=meta)


def test_snapshot_has_no_secrets_and_has_strategy_params():
    snap = report.settings_snapshot()
    for forbidden in ("DATABASE_URL", "MASTER_ENCRYPTION_KEY",
                      "MASTER_ENCRYPTION_KEY_PREVIOUS", "CLERK_JWKS_URL",
                      "REDDIT_CLIENT_SECRET", "API_CORS_ORIGINS"):
        assert forbidden not in snap
    assert snap["BUY_THRESHOLD"] == 60
    assert "TRAILING_MODE" in snap
    assert "MIN_24H_QUOTE_VOLUME" in snap


def test_report_contains_all_sections(db):
    md = _build(db)
    for header in [
        "# CrypSavvy Diagnostics Report",
        "## 1. Config snapshot",
        "## 2. Verdict & edge metrics",
        "## 3. Exit-reason breakdown",
        "## 4. Planned vs realized R:R",
        "## 5. MAE / MFE excursion analysis",
        "## 6. Costs: actual vs estimated",
        "## 7. Churn",
        "## 8. Hold time",
        "## 9. Breakdowns",
        "## 10. Worst & best trades",
        "## 11. Full trade log",
        "## 12. Machine-readable appendix",
    ]:
        assert header in md, f"missing section: {header}"
    # A known config value is rendered in the snapshot table.
    assert "| BUY_THRESHOLD | 60 |" in md
    # Coverage is stated so a future session knows what to trust.
    assert "coverage: 2/3" in md


def test_report_csv_block(db):
    md = _build(db)
    assert "```csv" in md
    csv_body = md.split("```csv")[1].split("```")[0].strip().splitlines()
    header = csv_body[0]
    assert header.startswith("entry_ts,exit_ts,symbol,bucket,strategy,regime")
    assert len(csv_body) == 1 + 3                    # header + 3 trades
    # No thousands separators — every row must keep the column count.
    assert all(line.count(",") == header.count(",") for line in csv_body)


def test_report_json_appendix_round_trips(db):
    md = _build(db)
    payload = json.loads(md.split("```json")[1].split("```")[0])
    assert payload["schema_version"] == report.REPORT_SCHEMA_VERSION
    assert payload["diagnostics"]["total_trades"] == 3
    assert payload["config"]["settings"]["BUY_THRESHOLD"] == 60
    assert "DATABASE_URL" not in json.dumps(payload)


def test_report_handles_no_trades():
    meta = {"generated_at": time.time(), "mode": "paper", "trade_count": 0,
            "open_positions": 0, "initial_capital_usdt": 1000.0,
            "period_days": 0.0}
    md = report.build_markdown_report(
        diagnostics={"total_trades": 0},
        config={"settings": report.settings_snapshot()},
        trades=[], meta=meta)
    assert "No closed trades" in md
    assert "```json" in md
