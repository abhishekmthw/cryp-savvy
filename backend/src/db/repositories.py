"""
User-scoped query helpers. The single seam where every "find X for user Y"
query lives, so the multi-tenant invariant (data is filtered by user_id)
is enforced in one place.

Functions take an explicit ``Session`` rather than opening one — callers
control the transaction boundary via ``session_scope()``.
"""

from __future__ import annotations

import time
from statistics import mean
from typing import Optional

from sqlalchemy import case, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.backtest import metrics
from src.db.models import (
    Allocation, BucketState, Order, Position, Trade, User, UserBotConfig,
    UserCredential,
)
from src.security.crypto import CredentialVault


# ── Users ────────────────────────────────────────────────────────────────────

def get_user_or_create(
    db: Session,
    *,
    clerk_user_id: str,
    email: str | None,
    vault: CredentialVault,
) -> User:
    """
    Lazy upsert called by the auth dependency. If the user is new, generate a
    fresh wrapped DEK and a default UserBotConfig from settings.py.
    """
    user = db.get(User, clerk_user_id)
    if user is not None:
        # Update email if Clerk says it changed
        if email and user.email != email:
            user.email = email
        return user

    _, wrapped = vault.new_user_dek()
    user = User(
        clerk_user_id=clerk_user_id,
        email=email,
        bot_enabled=False,
        mode="paper",
        wrapped_dek=wrapped.wrapped_dek,
        dek_nonce=wrapped.dek_nonce,
        kek_version=wrapped.kek_version,
    )
    db.add(user)

    db.add(UserBotConfig(
        user_id=clerk_user_id,
        initial_capital_usdt=settings.INITIAL_CAPITAL_USDT,
        max_position_usdt=settings.MAX_POSITION_USDT,
        max_open_positions=settings.MAX_OPEN_POSITIONS,
        stop_loss_pct=settings.STOP_LOSS_PCT,
        take_profit_pct=settings.TAKE_PROFIT_PCT,
        trailing_stop_trigger=settings.TRAILING_STOP_TRIGGER,
        trailing_stop_offset=settings.TRAILING_STOP_OFFSET,
        daily_loss_limit_usdt=settings.DAILY_LOSS_LIMIT_USDT,
    ))

    db.flush()
    return user


def list_users_with_bot_enabled(db: Session) -> list[User]:
    return list(db.execute(select(User).where(User.bot_enabled.is_(True))).scalars())


# ── Credentials ──────────────────────────────────────────────────────────────

def upsert_credential(
    db: Session,
    *,
    user_id: str,
    provider: str,
    ciphertext: bytes,
    nonce: bytes,
    last4: str,
    valid: bool,
    verified_at: Optional[float] = None,
) -> None:
    stmt = pg_insert(UserCredential).values(
        user_id=user_id,
        provider=provider,
        ciphertext=ciphertext,
        nonce=nonce,
        last4=last4,
        valid=valid,
        verified_at=__epoch_to_dt(verified_at) if verified_at else None,
    ).on_conflict_do_update(
        index_elements=[UserCredential.user_id, UserCredential.provider],
        set_={
            "ciphertext":  ciphertext,
            "nonce":       nonce,
            "last4":       last4,
            "valid":       valid,
            "verified_at": __epoch_to_dt(verified_at) if verified_at else None,
        },
    )
    db.execute(stmt)


def delete_credential(db: Session, *, user_id: str, provider: str) -> None:
    db.query(UserCredential).filter_by(user_id=user_id, provider=provider).delete()


def get_credentials(db: Session, user_id: str) -> list[UserCredential]:
    return list(db.execute(
        select(UserCredential).where(UserCredential.user_id == user_id)
    ).scalars())


def get_credential(db: Session, user_id: str, provider: str) -> UserCredential | None:
    return db.get(UserCredential, (user_id, provider))


# ── Trades ───────────────────────────────────────────────────────────────────

def record_trade(db: Session, *, user_id: str, trade: dict) -> None:
    db.add(Trade(
        user_id=user_id,
        order_id=trade.get("order_id"),
        symbol=trade.get("symbol"),
        side="sell",
        entry_price=trade.get("entry_price"),
        exit_price=trade.get("exit_price"),
        qty=trade.get("qty"),
        amount_usdt=trade.get("amount_usdt"),
        proceeds=trade.get("proceeds"),
        pnl=trade.get("pnl"),
        pnl_pct=trade.get("pnl_pct"),
        reason=trade.get("reason"),
        bucket=trade.get("bucket"),
        strategy=trade.get("strategy"),
        regime=trade.get("regime"),
        entry_score=trade.get("entry_score"),
        duration_s=trade.get("duration_s"),
        ts=time.time(),
        # Diagnostics v2 (0006) — execution detail captured at close.
        entry_ts=trade.get("entry_ts"),
        planned_stop_loss=trade.get("planned_stop_loss"),
        planned_take_profit=trade.get("planned_take_profit"),
        mae_pct=trade.get("mae_pct"),
        mfe_pct=trade.get("mfe_pct"),
        fee_usdt=trade.get("fee_usdt"),
        slippage_usdt=trade.get("slippage_usdt"),
        scores=trade.get("scores"),
    ))


def trades_for_user(db: Session, user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    rows = db.execute(
        select(Trade)
        .where(Trade.user_id == user_id)
        .order_by(desc(Trade.ts))
        .limit(limit).offset(offset)
    ).scalars()
    def _f(v):  # Numeric columns read back as Decimal — cast to float for JSON
        return float(v) if v is not None else None
    return [{
        "symbol":      t.symbol,
        "side":        t.side,
        "entry_price": _f(t.entry_price),
        "exit_price":  _f(t.exit_price),
        "pnl":         _f(t.pnl),
        "pnl_pct":     _f(t.pnl_pct),
        "reason":      t.reason,
        "bucket":      t.bucket,
        "strategy":    t.strategy,
        "regime":      t.regime,
        "entry_score": _f(t.entry_score),
        "duration_s":  _f(t.duration_s),
        "ts":          t.ts,
        "entry_ts":    _f(t.entry_ts),
    } for t in rows]


def trade_stats(db: Session, user_id: str) -> dict:
    win_case  = case((Trade.pnl > 0, 1), else_=0)
    loss_case = case((Trade.pnl < 0, 1), else_=0)
    row = db.execute(
        select(
            func.count(Trade.id).label("total"),
            func.coalesce(func.sum(win_case),  0).label("wins"),
            func.coalesce(func.sum(loss_case), 0).label("losses"),
            func.coalesce(func.sum(Trade.pnl),     0.0).label("total_pnl"),
            func.coalesce(func.avg(Trade.pnl_pct), 0.0).label("avg_pnl_pct"),
            func.coalesce(func.max(Trade.pnl_pct), 0.0).label("best_pct"),
            func.coalesce(func.min(Trade.pnl_pct), 0.0).label("worst_pct"),
        ).where(Trade.user_id == user_id)
    ).one()

    total = int(row.total or 0)
    if total == 0:
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "total_pnl": 0.0,
            "avg_pnl_pct": 0.0, "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
        }
    wins = int(row.wins or 0)
    return {
        "total_trades":    total,
        "wins":            wins,
        "losses":          int(row.losses or 0),
        "win_rate":        round(wins / total * 100, 1),
        "total_pnl":       round(float(row.total_pnl  or 0), 2),
        "avg_pnl_pct":     round(float(row.avg_pnl_pct or 0), 2),
        "best_trade_pct":  round(float(row.best_pct   or 0), 2),
        "worst_trade_pct": round(float(row.worst_pct  or 0), 2),
    }


def count_trades(db: Session, user_id: str) -> int:
    return int(db.execute(
        select(func.count(Trade.id)).where(Trade.user_id == user_id)
    ).scalar() or 0)


def trade_diagnostics(db: Session, user_id: str, initial_capital: float = 0.0) -> dict:
    """
    Loss-attribution breakdown of a user's closed trades — the data behind the
    diagnostics dashboard. Pure aggregation over the ``trades`` table: overall
    "edge" metrics (profit factor, expectancy, payoff & breakeven win rate, max
    drawdown) plus per-reason / per-symbol / per-bucket / per-strategy /
    per-regime cuts and a fee-drag estimate. Reuses the backtester's metric
    helpers so paper stats and backtest stats are computed identically.

    Trades booked before the 0005 instrumentation have NULL bucket/strategy/
    regime and are grouped as ``"unknown"`` there (see ``coverage``); the
    reason/symbol/duration/edge/fee cuts work on all historical trades.
    """
    rows = list(db.execute(
        select(Trade).where(Trade.user_id == user_id).order_by(Trade.ts.asc())
    ).scalars())
    if not rows:
        return {"total_trades": 0}

    def _f(v) -> float:
        return float(v) if v is not None else 0.0

    def _opt(v) -> float | None:
        # None-preserving cast — v2 sections track coverage, so NULL ≠ 0.
        return float(v) if v is not None else None

    trades = [{
        "pnl":         _f(t.pnl),
        "pnl_pct":     _f(t.pnl_pct),
        "reason":      t.reason or "unknown",
        "symbol":      t.symbol or "unknown",
        "bucket":      t.bucket or "unknown",
        "strategy":    t.strategy or "unknown",
        "regime":      t.regime or "unknown",
        "amount_usdt": _f(t.amount_usdt),
        "duration_s":  _f(t.duration_s),
        # v2 fields (0006) — None on pre-instrumentation rows.
        "ts":            float(t.ts),
        "entry_ts":      (float(t.entry_ts) if t.entry_ts is not None
                          else float(t.ts) - _f(t.duration_s)),
        "entry_price":   _opt(t.entry_price),
        "planned_sl":    _opt(t.planned_stop_loss),
        "planned_tp":    _opt(t.planned_take_profit),
        "mae_pct":       _opt(t.mae_pct),
        "mfe_pct":       _opt(t.mfe_pct),
        "fee_usdt":      _opt(t.fee_usdt),
        "slippage_usdt": _opt(t.slippage_usdt),
    } for t in rows]

    total  = len(trades)
    pnls   = [t["pnl"] for t in trades]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    avg_win  = mean(wins) if wins else 0.0
    avg_loss = mean(losses) if losses else 0.0            # negative
    payoff   = (avg_win / abs(avg_loss)) if avg_loss else 0.0
    breakeven_wr = (1.0 / (1.0 + payoff) * 100) if payoff > 0 else 0.0

    # Equity curve (initial + running P&L) → max drawdown, via the backtester.
    equity, running = [float(initial_capital)], float(initial_capital)
    for p in pnls:
        running += p
        equity.append(running)

    edge = {
        "win_rate":           round(len(wins) / total * 100, 2),
        "breakeven_win_rate": round(breakeven_wr, 2),
        "profit_factor":      round(metrics.profit_factor(trades), 3),
        "expectancy_usdt":    round(metrics.expectancy(trades), 4),
        "expectancy_pct":     round(mean([t["pnl_pct"] for t in trades]), 4),
        "avg_win_usdt":       round(avg_win, 2),
        "avg_loss_usdt":      round(avg_loss, 2),
        "payoff_ratio":       round(payoff, 3),
        "largest_win_usdt":   round(max(wins), 2) if wins else 0.0,
        "largest_loss_usdt":  round(min(losses), 2) if losses else 0.0,
        "gross_profit_usdt":  round(sum(wins), 2),
        "gross_loss_usdt":    round(sum(losses), 2),
        "total_pnl_usdt":     round(sum(pnls), 2),
        "max_drawdown_pct":   round(metrics.max_drawdown(equity) * 100, 2),
    }

    # Fee/slippage drag: ~round-trip cost on the traded notional (both sides).
    rt_rate = (settings.FEE_PCT + settings.SLIPPAGE_PCT) * 2
    est_cost = sum(t["amount_usdt"] for t in trades) * rt_rate
    gross_loss_abs = abs(edge["gross_loss_usdt"]) or 1.0
    fees = {
        "round_trip_pct":      round(rt_rate * 100, 3),
        "est_total_cost_usdt": round(est_cost, 2),
        "est_cost_per_trade":  round(est_cost / total, 4),
        "pct_of_gross_loss":   round(est_cost / gross_loss_abs * 100, 1),
    }
    # v2: ACTUAL costs, from trades that recorded them (paper-modeled; live
    # fills are net of fees so those rows stay NULL — hence the coverage count).
    fee_rows = [t for t in trades if t["fee_usdt"] is not None]
    if fee_rows:
        actual_fee  = sum(t["fee_usdt"] for t in fee_rows)
        actual_slip = sum(t["slippage_usdt"] or 0.0 for t in fee_rows)
        fees.update({
            "actual_fee_usdt":        round(actual_fee, 2),
            "actual_slippage_usdt":   round(actual_slip, 2),
            "actual_total_cost_usdt": round(actual_fee + actual_slip, 2),
            "actual_cost_per_trade":  round((actual_fee + actual_slip) / len(fee_rows), 4),
            "trades_with_fee_data":   len(fee_rows),
        })
    else:
        fees["trades_with_fee_data"] = 0

    # Hold-time: are losers held longer than winners (letting losses run)?
    win_durs  = [t["duration_s"] for t, p in zip(trades, pnls) if p > 0]
    loss_durs = [t["duration_s"] for t, p in zip(trades, pnls) if p < 0]
    duration = {
        "avg_hours":      round(mean([t["duration_s"] for t in trades]) / 3600, 2),
        "avg_win_hours":  round(mean(win_durs) / 3600, 2) if win_durs else 0.0,
        "avg_loss_hours": round(mean(loss_durs) / 3600, 2) if loss_durs else 0.0,
    }

    def _breakdown(key: str) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for t in trades:
            groups.setdefault(t[key], []).append(t)
        out = []
        for name, ts in groups.items():
            g_pnls = [x["pnl"] for x in ts]
            g_wins = [p for p in g_pnls if p > 0]
            out.append({
                "key":         name,
                "count":       len(ts),
                "wins":        len(g_wins),
                "win_rate":    round(len(g_wins) / len(ts) * 100, 1),
                "total_pnl":   round(sum(g_pnls), 2),
                "avg_pnl":     round(mean(g_pnls), 2),
                "avg_pnl_pct": round(mean([x["pnl_pct"] for x in ts]), 2),
            })
        # Biggest bleeders (most negative total P&L) first.
        return sorted(out, key=lambda r: r["total_pnl"])

    # ── v2: planned vs realized R:R ──────────────────────────────────────────
    rr_rows = []
    for t in trades:
        e, sl, tp = t["entry_price"], t["planned_sl"], t["planned_tp"]
        if not e or sl is None or tp is None:
            continue
        risk_pct = (e - sl) / e * 100
        reward_pct = (tp - e) / e * 100
        if risk_pct <= 0:
            continue
        rr_rows.append({
            "risk_pct": risk_pct, "reward_pct": reward_pct,
            "rr": reward_pct / risk_pct,
            "realized_r": t["pnl_pct"] / risk_pct,
            "pnl": t["pnl"], "pnl_pct": t["pnl_pct"], "reason": t["reason"],
        })
    rr_wins   = [r["realized_r"] for r in rr_rows if r["pnl"] > 0]
    rr_losses = [r["realized_r"] for r in rr_rows if r["pnl"] < 0]
    stop_exits = [r for r in rr_rows if r["reason"] == "stop_loss"]
    # Lost more than planned (gap/slippage past the stop, 0.1pct-pt tolerance).
    overshoots = [r for r in stop_exits if abs(r["pnl_pct"]) > r["risk_pct"] + 0.1]
    rr = {
        "coverage":               len(rr_rows),
        "avg_planned_risk_pct":   round(mean(r["risk_pct"] for r in rr_rows), 2) if rr_rows else 0.0,
        "avg_planned_reward_pct": round(mean(r["reward_pct"] for r in rr_rows), 2) if rr_rows else 0.0,
        "avg_planned_rr":         round(mean(r["rr"] for r in rr_rows), 2) if rr_rows else 0.0,
        "avg_realized_r":         round(mean(r["realized_r"] for r in rr_rows), 3) if rr_rows else 0.0,
        "avg_win_realized_r":     round(mean(rr_wins), 3) if rr_wins else 0.0,
        "avg_loss_realized_r":    round(mean(rr_losses), 3) if rr_losses else 0.0,
        "stop_overshoot_pct":     (round(len(overshoots) / len(stop_exits) * 100, 1)
                                   if stop_exits else 0.0),
    }

    # ── v2: MAE/MFE excursion analysis ───────────────────────────────────────
    exc = [t for t in trades if t["mfe_pct"] is not None and t["mae_pct"] is not None]
    exc_wins   = [t for t in exc if t["pnl"] > 0]
    exc_losses = [t for t in exc if t["pnl"] < 0]
    # Losers with planned-reward data, for the "reached ≥50% of target" cut.
    loss_with_plan = [t for t in exc_losses
                      if t["entry_price"] and t["planned_tp"] is not None]
    reached_half_tp = [
        t for t in loss_with_plan
        if t["mfe_pct"] >= ((t["planned_tp"] - t["entry_price"])
                            / t["entry_price"] * 100) * 0.5
    ]
    mae_mfe = {
        "coverage":            len(exc),
        "avg_mfe_winners_pct": round(mean(t["mfe_pct"] for t in exc_wins), 2) if exc_wins else 0.0,
        "avg_mfe_losers_pct":  round(mean(t["mfe_pct"] for t in exc_losses), 2) if exc_losses else 0.0,
        "avg_mae_winners_pct": round(mean(t["mae_pct"] for t in exc_wins), 2) if exc_wins else 0.0,
        "avg_mae_losers_pct":  round(mean(t["mae_pct"] for t in exc_losses), 2) if exc_losses else 0.0,
        # % of losers that were ≥1% in profit at some point — the direct
        # "winners being clipped into losers" signal.
        "losers_profitable_1pct": (round(sum(1 for t in exc_losses if t["mfe_pct"] >= 1.0)
                                         / len(exc_losses) * 100, 1) if exc_losses else 0.0),
        "losers_reached_half_tp": (round(len(reached_half_tp) / len(loss_with_plan) * 100, 1)
                                   if loss_with_plan else 0.0),
    }

    # ── v2: churn ────────────────────────────────────────────────────────────
    from statistics import median
    period_days = max((trades[-1]["ts"] - trades[0]["ts"]) / 86_400.0, 1.0)
    window_s = settings.CHURN_REENTRY_WINDOW_H * 3600
    sym_groups: dict[str, list[dict]] = {}
    for t in trades:
        sym_groups.setdefault(t["symbol"], []).append(t)
    all_gaps: list[float] = []
    reentered = []
    for sym, ts_list in sym_groups.items():
        ordered = sorted(ts_list, key=lambda x: x["entry_ts"])
        gaps = []
        for prev, nxt in zip(ordered, ordered[1:]):
            gap = nxt["entry_ts"] - prev["ts"]   # exit of one → entry of next
            if 0 <= gap <= window_s:
                gaps.append(gap)
        if gaps:
            all_gaps.extend(gaps)
            reentered.append({"symbol": sym, "entries": len(ordered),
                              "reentries": len(gaps),
                              "median_gap_min": round(median(gaps) / 60, 1)})
    reentered.sort(key=lambda r: r["reentries"], reverse=True)
    churn = {
        "period_days":             round(period_days, 1),
        "trades_per_day":          round(total / period_days, 2),
        "window_h":                settings.CHURN_REENTRY_WINDOW_H,
        "reentries_within_window": len(all_gaps),
        "median_reentry_minutes":  round(median(all_gaps) / 60, 1) if all_gaps else 0.0,
        "top_reentered":           reentered[:5],
    }

    # ── v2: daily-annualised Sharpe from realized P&L ────────────────────────
    daily_pnl: dict[int, float] = {}
    for t in trades:
        day = int(t["ts"] // 86_400)
        daily_pnl[day] = daily_pnl.get(day, 0.0) + t["pnl"]
    daily_returns: list[float] = []
    if initial_capital and float(initial_capital) > 0:
        equity_d = float(initial_capital)
        for day in sorted(daily_pnl):
            daily_returns.append(daily_pnl[day] / equity_d if equity_d > 0 else 0.0)
            equity_d += daily_pnl[day]
    risk = {
        "sharpe_daily_ann":  (round(metrics.sharpe(daily_returns, periods_per_year=365), 3)
                              if len(daily_returns) >= 2 else 0.0),
        "daily_return_days": len(daily_returns),
    }

    # ── v2: by entry hour (UTC) ──────────────────────────────────────────────
    for t in trades:
        t["hour"] = f"{int((t['entry_ts'] % 86_400) // 3600):02d}"

    attributed = sum(1 for t in trades if t["strategy"] != "unknown")

    return {
        "total_trades": total,
        "edge":         edge,
        "fees":         fees,
        "duration":     duration,
        "rr":           rr,
        "mae_mfe":      mae_mfe,
        "churn":        churn,
        "risk":         risk,
        "by_reason":    _breakdown("reason"),
        "by_symbol":    _breakdown("symbol"),
        "by_bucket":    _breakdown("bucket"),
        "by_strategy":  _breakdown("strategy"),
        "by_regime":    _breakdown("regime"),
        "by_hour":      _breakdown("hour"),
        "coverage": {
            "attributed_trades":   attributed,
            "unattributed_trades": total - attributed,
            "instrumented_trades": len(exc),
        },
    }


def trades_full_for_export(db: Session, user_id: str,
                           limit: int | None = None) -> list[dict]:
    """Every column of the most recent ``limit`` trades, oldest-first — the
    per-trade log for the diagnostics export report."""
    limit = limit or settings.EXPORT_TRADE_LOG_LIMIT
    rows = list(db.execute(
        select(Trade)
        .where(Trade.user_id == user_id)
        .order_by(desc(Trade.ts))
        .limit(limit)
    ).scalars())
    rows.reverse()  # oldest-first reads naturally in the report

    def _opt(v):
        return float(v) if v is not None else None

    return [{
        "symbol":              t.symbol,
        "bucket":              t.bucket,
        "strategy":            t.strategy,
        "regime":              t.regime,
        "entry_score":         _opt(t.entry_score),
        "entry_ts":            (_opt(t.entry_ts) if t.entry_ts is not None
                                else (float(t.ts) - float(t.duration_s or 0.0))),
        "exit_ts":             float(t.ts),
        "entry_price":         _opt(t.entry_price),
        "exit_price":          _opt(t.exit_price),
        "qty":                 _opt(t.qty),
        "amount_usdt":         _opt(t.amount_usdt),
        "pnl":                 _opt(t.pnl),
        "pnl_pct":             _opt(t.pnl_pct),
        "reason":              t.reason,
        "planned_stop_loss":   _opt(t.planned_stop_loss),
        "planned_take_profit": _opt(t.planned_take_profit),
        "mae_pct":             _opt(t.mae_pct),
        "mfe_pct":             _opt(t.mfe_pct),
        "fee_usdt":            _opt(t.fee_usdt),
        "slippage_usdt":       _opt(t.slippage_usdt),
        "duration_s":          _opt(t.duration_s),
        "scores":              t.scores,
    } for t in rows]


def pnl_history_for_user(db: Session, user_id: str, initial_capital: float) -> list[dict]:
    # Running P&L computed in SQL via a window function — avoids shipping every
    # trade row to Python just to add them up.
    running_pnl = func.sum(func.coalesce(Trade.pnl, 0.0)).over(
        order_by=Trade.ts.asc(),
        rows=(None, 0),
    ).label("running_pnl")
    rows = list(db.execute(
        select(Trade.ts, running_pnl)
        .where(Trade.user_id == user_id)
        .order_by(Trade.ts.asc())
    ))

    initial = float(initial_capital)
    if not rows:
        return [{"ts": time.time(), "value": round(initial, 2)}]
    history = [{"ts": rows[0][0], "value": round(initial, 2)}]
    for ts, running in rows:
        history.append({"ts": ts, "value": round(initial + float(running or 0), 2)})
    return history


# ── Positions (open) ─────────────────────────────────────────────────────────

def upsert_position(db: Session, user_id: str, p: dict) -> None:
    stmt = pg_insert(Position).values(user_id=user_id, **p).on_conflict_do_update(
        index_elements=[Position.user_id, Position.symbol],
        set_={k: v for k, v in p.items() if k != "symbol"},
    )
    db.execute(stmt)


def delete_position(db: Session, user_id: str, symbol: str) -> None:
    db.query(Position).filter_by(user_id=user_id, symbol=symbol).delete()


def positions_for_user(db: Session, user_id: str) -> list[Position]:
    return list(db.execute(
        select(Position).where(Position.user_id == user_id)
    ).scalars())


# ── Orders (idempotent intent log) ───────────────────────────────────────────

def create_order(db: Session, *, user_id: str, client_order_id: str, symbol: str,
                 side: str, mode: str, quote_currency: str = "USDT",
                 bucket: str = "day",
                 requested_amount: float | None = None,
                 requested_qty: float | None = None,
                 requested_price: float | None = None,
                 reason: str | None = None) -> None:
    db.add(Order(
        id=client_order_id, user_id=user_id, symbol=symbol, side=side, mode=mode,
        status="pending", quote_currency=quote_currency, bucket=bucket,
        requested_amount=requested_amount, requested_qty=requested_qty,
        requested_price=requested_price, reason=reason,
    ))


def update_order(db: Session, client_order_id: str, **fields) -> None:
    order = db.get(Order, client_order_id)
    if order is None:
        return
    for k, v in fields.items():
        setattr(order, k, v)


# ── Paper-data wipe ──────────────────────────────────────────────────────────

def count_live_orders(db: Session, user_id: str) -> int:
    """
    Safety guard for the paper-data wipe: trades/positions rows carry no mode
    column, so any live-mode order means live history would be silently
    destroyed — the wipe must be refused while this is non-zero.
    """
    return int(db.execute(
        select(func.count(Order.id))
        .where(Order.user_id == user_id, Order.mode == "live")
    ).scalar() or 0)


def clear_paper_data(db: Session, user_id: str) -> dict[str, int]:
    """
    Delete all paper-trading history for one user: every trades/positions row,
    paper-mode orders, and the bucket_state rows (missing rows read back as the
    zero defaults everywhere). Caller must verify ``count_live_orders() == 0``
    and that the user's bot is stopped. Returns per-table deleted-row counts.
    """
    trades = db.query(Trade).filter_by(user_id=user_id).delete()
    positions = db.query(Position).filter_by(user_id=user_id).delete()
    orders = db.query(Order).filter_by(user_id=user_id, mode="paper").delete()
    buckets = db.query(BucketState).filter_by(user_id=user_id).delete()
    return {
        "trades": trades,
        "positions": positions,
        "orders": orders,
        "bucket_states": buckets,
    }


# ── Daily realized P&L (restart-safe loss-limit recovery) ─────────────────────

def daily_realized_pnl(db: Session, user_id: str, day_start_ts: float) -> float:
    """Sum of realized P&L from trades since ``day_start_ts`` (epoch seconds)."""
    val = db.execute(
        select(func.coalesce(func.sum(Trade.pnl), 0.0))
        .where(Trade.user_id == user_id, Trade.ts >= day_start_ts)
    ).scalar()
    return float(val or 0.0)


# ── Bot config ───────────────────────────────────────────────────────────────

def get_bot_config(db: Session, user_id: str) -> UserBotConfig | None:
    return db.get(UserBotConfig, user_id)


# ── Allocation + bucket state ─────────────────────────────────────────────────

def get_allocation(db: Session, user_id: str) -> Allocation | None:
    return db.get(Allocation, user_id)


def upsert_allocation(db: Session, *, user_id: str, total: float, day_budget: float,
                      long_budget: float, allocate_all: bool,
                      base_currency: str = "USDT", status: str = "active") -> None:
    stmt = pg_insert(Allocation).values(
        user_id=user_id, base_currency=base_currency, total_allocated=total,
        day_budget=day_budget, long_budget=long_budget, allocate_all=allocate_all,
        status=status,
    ).on_conflict_do_update(
        index_elements=[Allocation.user_id],
        set_={
            "total_allocated": total, "day_budget": day_budget,
            "long_budget": long_budget, "allocate_all": allocate_all,
            "base_currency": base_currency, "status": status,
        },
    )
    db.execute(stmt)


def set_allocation_status(db: Session, user_id: str, status: str) -> None:
    alloc = db.get(Allocation, user_id)
    if alloc is not None:
        alloc.status = status


def get_bucket_states(db: Session, user_id: str) -> list[BucketState]:
    return list(db.execute(
        select(BucketState).where(BucketState.user_id == user_id)
    ).scalars())


def upsert_bucket_state(db: Session, *, user_id: str, bucket: str,
                        realized_pnl: float, peak_equity: float,
                        drawdown_state: str) -> None:
    stmt = pg_insert(BucketState).values(
        user_id=user_id, bucket=bucket, realized_pnl=realized_pnl,
        peak_equity=peak_equity, drawdown_state=drawdown_state,
    ).on_conflict_do_update(
        index_elements=[BucketState.user_id, BucketState.bucket],
        set_={"realized_pnl": realized_pnl, "peak_equity": peak_equity,
              "drawdown_state": drawdown_state},
    )
    db.execute(stmt)


# ── Internal ─────────────────────────────────────────────────────────────────

def __epoch_to_dt(epoch: float):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc)
