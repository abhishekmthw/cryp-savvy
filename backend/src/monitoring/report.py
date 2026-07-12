"""
Diagnostics export report builder.

Pure functions, no I/O (mirrors backtest/metrics.py) — the API layer fetches
the data and this module renders it. The markdown report is written for LLM
consumption: the user pastes it into Claude Code after a paper/live period so
the next round of strategy improvements starts from complete, self-describing
evidence (config that was active, edge metrics, planned-vs-realized R:R,
MAE/MFE, churn, per-trade log).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings

REPORT_SCHEMA_VERSION = 2

# Explicit allowlist — NEVER dump settings wholesale: DATABASE_URL,
# MASTER_ENCRYPTION_KEY*, CLERK_*, REDDIT_*, API_* must not reach a report
# that gets pasted into chats and shared.
_SNAPSHOT_KEYS = [
    # Universe / coin selection
    "QUOTE_CURRENCY", "TOP_N_COINS", "SCAN_INTERVAL_S", "FAST_POLL_S",
    "CORE_SYMBOLS", "MIN_24H_QUOTE_VOLUME", "MAX_24H_CHANGE_PCT",
    "MOMENTUM_CHANGE_WEIGHT", "MAX_SPREAD_PCT", "MIN_TRADE_USDT",
    # Churn control
    "REENTRY_COOLDOWN_S", "STOPOUT_COOLDOWN_S", "MAX_TRADES_PER_SYMBOL_PER_DAY",
    # Technical analysis
    "TIMEFRAME", "CANDLE_LIMIT", "SIGNAL_ON_CLOSED_CANDLE",
    "EMA_FAST", "EMA_SLOW", "RSI_PERIOD", "RSI_LOWER", "RSI_UPPER",
    "MACD_FAST", "MACD_SLOW", "MACD_SIGNAL", "VOLUME_MULT",
    # Scoring / quality gate
    "TECHNICAL_WEIGHT", "SENTIMENT_WEIGHT", "BUY_THRESHOLD",
    # Regime detection
    "REGIME_FAST_SMA", "REGIME_SLOW_SMA", "REGIME_FLAT_BAND",
    # Strategy triggers
    "DONCHIAN_PERIOD", "RSI_OVERSOLD", "RSI_OVERBOUGHT",
    # Stops / trailing
    "USE_ATR_STOPS", "ATR_PERIOD", "ATR_SL_MULT_DAY", "ATR_TP_MULT_DAY",
    "ATR_SL_MULT_LONG", "ATR_TP_MULT_LONG",
    "MAX_STOP_DISTANCE_PCT_DAY", "MAX_STOP_DISTANCE_PCT_LONG",
    "TRAILING_MODE", "TRAIL_ARM_R", "TRAIL_ATR_MULT_DAY", "TRAIL_ATR_MULT_LONG",
    # Sizing
    "RISK_PER_TRADE", "KELLY_FRACTION", "KELLY_MIN_TRADES",
    "KELLY_LOOKBACK_TRADES", "NEGATIVE_EDGE_RISK_MULT",
    # Circuit breakers / limits
    "DRAWDOWN_REDUCE_PCT", "DRAWDOWN_HALT_PCT", "DRAWDOWN_PAUSE_PCT",
    # Execution costs
    "FEE_PCT", "SLIPPAGE_PCT",
    # Per-user defaults
    "INITIAL_CAPITAL_USDT", "MAX_POSITION_USDT", "MAX_OPEN_POSITIONS",
    "STOP_LOSS_PCT", "TAKE_PROFIT_PCT", "TRAILING_STOP_TRIGGER",
    "TRAILING_STOP_OFFSET", "DAILY_LOSS_LIMIT_USDT",
]


def settings_snapshot() -> dict:
    """Strategy-relevant settings active right now (allowlisted, no secrets)."""
    return {k: getattr(settings, k) for k in _SNAPSHOT_KEYS if hasattr(settings, k)}


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _iso(ts: float | None) -> str:
    if not ts:
        return "n/a"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _n(v, nd: int = 2) -> str:
    """Number → string, None-safe (renders 'n/a' so gaps stay visible)."""
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return str(v)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def _breakdown_table(groups: list[dict]) -> str:
    return _table(
        ["Key", "Trades", "Wins", "Win rate", "Total P&L", "Avg P&L", "Avg P&L %"],
        [[str(g["key"]), str(g["count"]), str(g["wins"]), f'{g["win_rate"]}%',
          _n(g["total_pnl"]), _n(g["avg_pnl"]), f'{_n(g["avg_pnl_pct"])}%']
         for g in groups],
    )


# ── Verdict prose (same rules as the dashboard Diagnosis banner) ──────────────

def _verdict_notes(d: dict) -> tuple[str, list[str]]:
    edge, fees, duration = d["edge"], d["fees"], d["duration"]
    negative = (edge["win_rate"] < edge["breakeven_win_rate"]
                or edge["profit_factor"] < 1.0)
    verdict = "NEGATIVE EDGE" if negative else "POSITIVE EDGE"
    notes: list[str] = []
    if edge["win_rate"] < edge["breakeven_win_rate"]:
        notes.append(
            f"Win rate {edge['win_rate']}% is below the {edge['breakeven_win_rate']}% "
            f"breakeven required by the {edge['payoff_ratio']}:1 payoff ratio — "
            "the strategy loses money at this win/payoff combination.")
    if edge["profit_factor"] < 1.0:
        notes.append(f"Profit factor {edge['profit_factor']} (<1): gross losses "
                     "exceed gross profits.")
    reasons = {g["key"]: g["count"] for g in d.get("by_reason", [])}
    tp, sl = reasons.get("take_profit", 0), reasons.get("stop_loss", 0)
    if sl and tp == 0:
        notes.append(f"{sl} stop-outs and ZERO take-profit hits — winners never "
                     "reach the profit target (exit design problem).")
    elif reasons.get("sell_signal", 0) > tp:
        notes.append("More sell_signal exits than take_profit hits — winners are "
                     "being cut before reaching targets.")
    if fees.get("pct_of_gross_loss", 0) >= 10:
        notes.append(f"Estimated fees/slippage are {fees['pct_of_gross_loss']}% of "
                     "gross losses — churn is a material drag.")
    if duration["avg_loss_hours"] > duration["avg_win_hours"] > 0:
        notes.append(f"Losers held {duration['avg_loss_hours']}h on average vs "
                     f"{duration['avg_win_hours']}h for winners — losses run "
                     "longer than profits.")
    mm = d.get("mae_mfe") or {}
    if mm.get("coverage", 0) > 0 and mm.get("losers_profitable_1pct", 0) >= 25:
        notes.append(f"{mm['losers_profitable_1pct']}% of losers were ≥1% in profit "
                     "at some point (MFE) — winners are being clipped into losers.")
    rr = d.get("rr") or {}
    if rr.get("coverage", 0) > 0 and rr.get("stop_overshoot_pct", 0) >= 10:
        notes.append(f"{rr['stop_overshoot_pct']}% of stop-outs lost more than "
                     "planned — gaps/slippage past the stop (liquidity problem).")
    if not notes:
        notes.append("No structural failure signature detected in this sample.")
    return verdict, notes


# ── The report ─────────────────────────────────────────────────────────────────

def build_markdown_report(*, diagnostics: dict, config: dict,
                          trades: list[dict], meta: dict) -> str:
    d = diagnostics
    lines: list[str] = []
    add = lines.append

    add("# CrypSavvy Diagnostics Report")
    add("")
    add(f"> Generated {_iso(meta.get('generated_at'))} · mode: **{meta.get('mode', 'paper')}** · "
        f"period: {_iso(meta.get('period_start_ts'))} → {_iso(meta.get('period_end_ts'))} "
        f"({_n(meta.get('period_days'), 1)} days)")
    add(f"> {meta.get('trade_count', 0)} closed trades · {meta.get('open_positions', 0)} open positions · "
        f"initial capital {_n(meta.get('initial_capital_usdt'))} USDT · report schema v{REPORT_SCHEMA_VERSION}")
    add("> Purpose: paste this whole report into Claude Code to diagnose the "
        "strategy and plan the next round of improvements. Sections that depend "
        "on per-trade instrumentation state their coverage — treat low-coverage "
        "sections as partial evidence.")
    add("")

    # 1. Config snapshot — exact values (never rounded: FEE_PCT=0.001 must not
    # render as 0.00; a future session tunes parameters off this table).
    add("## 1. Config snapshot (parameters active when this report was generated)")
    add("")
    snap = config.get("settings", {})
    add(_table(["Param", "Value"], [[k, str(snap[k])] for k in snap]))
    user_cfg = config.get("user") or {}
    if user_cfg:
        add("")
        add("Per-user config overrides:")
        add("")
        add(_table(["Param", "Value"], [[k, str(v)] for k, v in user_cfg.items()]))
    alloc = config.get("allocation") or {}
    if alloc:
        add("")
        add("Capital allocation: " + ", ".join(f"{k}={v}" for k, v in alloc.items()))
    add("")

    if d.get("total_trades", 0) == 0:
        add("## 2. Verdict")
        add("")
        add("**No closed trades in this period — nothing to diagnose yet.**")
        add("")
        add("## Machine-readable appendix")
        add("")
        add("```json")
        add(json.dumps({"schema_version": REPORT_SCHEMA_VERSION, "meta": meta,
                        "config": config, "diagnostics": d},
                       indent=2, default=str))
        add("```")
        return "\n".join(lines)

    edge = d["edge"]

    # 2. Verdict & edge
    verdict, notes = _verdict_notes(d)
    add(f"## 2. Verdict & edge metrics — **{verdict}**")
    add("")
    for n in notes:
        add(f"- {n}")
    add("")
    add(_table(["Metric", "Value"], [
        ["Total trades", str(d["total_trades"])],
        ["Win rate", f'{edge["win_rate"]}%'],
        ["Breakeven win rate (at current payoff)", f'{edge["breakeven_win_rate"]}%'],
        ["Profit factor", _n(edge["profit_factor"], 3)],
        ["Payoff ratio (avg win : avg loss)", f'{edge["payoff_ratio"]}:1'],
        ["Expectancy / trade", f'{_n(edge["expectancy_usdt"], 4)} USDT ({_n(edge["expectancy_pct"], 4)}%)'],
        ["Avg win / avg loss", f'{_n(edge["avg_win_usdt"])} / {_n(edge["avg_loss_usdt"])} USDT'],
        ["Largest win / largest loss", f'{_n(edge["largest_win_usdt"])} / {_n(edge["largest_loss_usdt"])} USDT'],
        ["Gross profit / gross loss", f'{_n(edge["gross_profit_usdt"])} / {_n(edge["gross_loss_usdt"])} USDT'],
        ["Total P&L", f'{_n(edge["total_pnl_usdt"])} USDT'],
        ["Max drawdown", f'{edge["max_drawdown_pct"]}%'],
        ["Daily-annualised Sharpe", _n((d.get("risk") or {}).get("sharpe_daily_ann"), 3)],
    ]))
    add("")

    # 3. Exit reasons
    add("## 3. Exit-reason breakdown")
    add("")
    add(_breakdown_table(d["by_reason"]))
    add("")

    # 4. Planned vs realized R:R
    rr = d.get("rr") or {}
    add(f"## 4. Planned vs realized R:R (coverage: {rr.get('coverage', 0)}/{d['total_trades']} trades)")
    add("")
    if rr.get("coverage", 0) > 0:
        add(f"Avg planned R:R **{_n(rr['avg_planned_rr'])}** "
            f"(risk {_n(rr['avg_planned_risk_pct'])}% → reward {_n(rr['avg_planned_reward_pct'])}%) · "
            f"avg realized **{_n(rr['avg_realized_r'], 3)}R** "
            f"(winners {_n(rr['avg_win_realized_r'], 3)}R, losers {_n(rr['avg_loss_realized_r'], 3)}R).")
        add(f"Stop overshoot: {_n(rr['stop_overshoot_pct'], 1)}% of stop-loss exits "
            "lost more than planned (slippage/gap past the stop).")
    else:
        add("_No instrumented trades yet (planned SL/TP recorded from migration 0006 onward)._")
    add("")

    # 5. MAE/MFE
    mm = d.get("mae_mfe") or {}
    add(f"## 5. MAE / MFE excursion analysis (coverage: {mm.get('coverage', 0)}/{d['total_trades']} trades)")
    add("")
    if mm.get("coverage", 0) > 0:
        add(_table(["Cut", "Avg MFE (best point)", "Avg MAE (worst point)"], [
            ["Winners", f'{_n(mm["avg_mfe_winners_pct"])}%', f'{_n(mm["avg_mae_winners_pct"])}%'],
            ["Losers",  f'{_n(mm["avg_mfe_losers_pct"])}%',  f'{_n(mm["avg_mae_losers_pct"])}%'],
        ]))
        add("")
        add(f"- **{_n(mm['losers_profitable_1pct'], 1)}%** of losers were ≥1% in profit at "
            "some point (clipped winners signal).")
        add(f"- **{_n(mm['losers_reached_half_tp'], 1)}%** of losers reached ≥50% of their "
            "planned take-profit distance before losing.")
    else:
        add("_No instrumented trades yet (MAE/MFE recorded from migration 0006 onward)._")
    add("")

    # 6. Costs
    fees = d["fees"]
    add("## 6. Costs: actual vs estimated")
    add("")
    if fees.get("trades_with_fee_data", 0) > 0:
        add(f"Actual (modeled per-trade): fees {_n(fees['actual_fee_usdt'])} + "
            f"slippage {_n(fees['actual_slippage_usdt'])} = "
            f"**{_n(fees['actual_total_cost_usdt'])} USDT** across "
            f"{fees['trades_with_fee_data']} trades "
            f"({_n(fees['actual_cost_per_trade'], 4)}/trade).")
    add(f"Estimate (round-trip {_n(fees['round_trip_pct'], 3)}% on notional, all trades): "
        f"{_n(fees['est_total_cost_usdt'])} USDT "
        f"({_n(fees['est_cost_per_trade'], 4)}/trade) — "
        f"{_n(fees['pct_of_gross_loss'], 1)}% of gross losses.")
    add("")

    # 7. Churn
    ch = d.get("churn") or {}
    add("## 7. Churn")
    add("")
    add(f"{_n(ch.get('trades_per_day'))} trades/day over {_n(ch.get('period_days'), 1)} days · "
        f"{ch.get('reentries_within_window', 0)} same-symbol re-entries within "
        f"{ch.get('window_h', settings.CHURN_REENTRY_WINDOW_H)}h "
        f"(median gap {_n(ch.get('median_reentry_minutes'), 1)} min).")
    if ch.get("top_reentered"):
        add("")
        add(_table(["Symbol", "Entries", "Re-entries", "Median gap (min)"],
                   [[r["symbol"], str(r["entries"]), str(r["reentries"]),
                     _n(r["median_gap_min"], 1)] for r in ch["top_reentered"]]))
    add("")

    # 8. Hold time
    dur = d["duration"]
    add("## 8. Hold time")
    add("")
    add(f"Avg {_n(dur['avg_hours'])}h · winners {_n(dur['avg_win_hours'])}h · "
        f"losers {_n(dur['avg_loss_hours'])}h.")
    add("")

    # 9. Breakdowns
    add("## 9. Breakdowns (biggest bleeders first)")
    for title, key in [("By symbol", "by_symbol"), ("By strategy", "by_strategy"),
                       ("By regime", "by_regime"), ("By bucket", "by_bucket"),
                       ("By entry hour (UTC)", "by_hour")]:
        groups = d.get(key) or []
        if not groups:
            continue
        add("")
        add(f"### {title}")
        add("")
        add(_breakdown_table(groups))
    add("")

    # 10. Worst & best trades
    n_detail = settings.EXPORT_WORST_BEST_N
    closed = [t for t in trades if t.get("pnl") is not None]
    by_pnl = sorted(closed, key=lambda t: t["pnl"])
    worst, best = by_pnl[:n_detail], list(reversed(by_pnl[-n_detail:]))

    def _trade_rows(ts_list: list[dict]) -> list[list[str]]:
        rows = []
        for t in ts_list:
            held_h = (t["duration_s"] or 0) / 3600
            rows.append([
                t["symbol"] or "?", t.get("strategy") or "?", t.get("regime") or "?",
                f'{_n(t["entry_price"], 6)}→{_n(t["exit_price"], 6)}',
                f'{_n(t["pnl_pct"])}%', f'{_n(t["mfe_pct"], 1)}/{_n(t["mae_pct"], 1)}',
                t.get("reason") or "?", f"{held_h:.1f}h",
            ])
        return rows

    add(f"## 10. Worst & best trades (N={n_detail})")
    add("")
    add("### Worst")
    add("")
    add(_table(["Symbol", "Strategy", "Regime", "Entry→Exit", "P&L %", "MFE/MAE %", "Reason", "Held"],
               _trade_rows(worst)))
    add("")
    add("### Best")
    add("")
    add(_table(["Symbol", "Strategy", "Regime", "Entry→Exit", "P&L %", "MFE/MAE %", "Reason", "Held"],
               _trade_rows(best)))
    add("")

    # 11. Full trade log (CSV)
    def _c(v, nd: int = 4) -> str:
        # CSV-safe: empty for None, NO thousands separators.
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:.{nd}f}"
        return str(v)

    add(f"## 11. Full trade log (CSV, most recent {settings.EXPORT_TRADE_LOG_LIMIT} max, oldest first)")
    add("")
    add("```csv")
    add("entry_ts,exit_ts,symbol,bucket,strategy,regime,entry_score,entry_price,"
        "exit_price,pnl,pnl_pct,reason,planned_sl,planned_tp,mae_pct,mfe_pct,"
        "fee_usdt,slippage_usdt,held_h")
    for t in trades:
        held_h = (t.get("duration_s") or 0) / 3600
        add(",".join([
            _c(t.get("entry_ts"), 0), _c(t.get("exit_ts"), 0),
            t.get("symbol") or "", t.get("bucket") or "", t.get("strategy") or "",
            t.get("regime") or "", _c(t.get("entry_score"), 1),
            _c(t.get("entry_price"), 8), _c(t.get("exit_price"), 8),
            _c(t.get("pnl"), 4), _c(t.get("pnl_pct"), 3), t.get("reason") or "",
            _c(t.get("planned_stop_loss"), 8), _c(t.get("planned_take_profit"), 8),
            _c(t.get("mae_pct"), 2), _c(t.get("mfe_pct"), 2),
            _c(t.get("fee_usdt"), 4), _c(t.get("slippage_usdt"), 4),
            f"{held_h:.2f}",
        ]))
    add("```")
    add("")

    # 12. Machine-readable appendix
    add("## 12. Machine-readable appendix")
    add("")
    add("```json")
    add(json.dumps({"schema_version": REPORT_SCHEMA_VERSION, "meta": meta,
                    "config": config, "diagnostics": d},
                   indent=2, default=str))
    add("```")
    add("")
    return "\n".join(lines)
