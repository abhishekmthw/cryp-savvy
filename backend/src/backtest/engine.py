"""
Historical replay backtester.

Long-only spot simulation that drives the SAME regime-aware strategy used live
(``strategies.evaluate``), with realistic ATR stops, fees and slippage, so the
backtest is an honest forward proxy. Live mode is meant to stay gated until a
walk-forward run here shows a positive out-of-sample Sharpe.

This is intentionally simple and dependency-light (no vectorbt). It recomputes
indicators on an expanding window each bar, so it's O(n·indicator_cost) — fine
for offline validation over months of candles, not for live hot paths.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass, field

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.analysis import strategies
from src.analysis.technical import compute_indicators
from src.backtest import metrics


@dataclass
class BacktestResult:
    trades: list[dict] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _warmup(df: pd.DataFrame) -> int:
    return max(settings.REGIME_SLOW_SMA, settings.EMA_SLOW, settings.MACD_SLOW,
              settings.DONCHIAN_PERIOD, settings.ATR_PERIOD) + 5


_TIMEFRAME_S = {"1m": 60, "15m": 900, "1h": 3600, "4h": 14_400, "1d": 86_400}


def _bar_epoch(df: pd.DataFrame, i: int) -> float:
    """Epoch seconds for bar ``i`` — real timestamps when the index is datetime
    (live data), else synthetic bar-number × timeframe (test fixtures)."""
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index[i].timestamp()
    return i * _TIMEFRAME_S.get(settings.TIMEFRAME, 3600)


def run_backtest(df: pd.DataFrame, *, initial_capital: float = 1000.0,
                 periods_per_year: float = 365 * 24,
                 use_trailing: bool = True) -> BacktestResult:
    """
    Replay ``df`` (oldest-first OHLCV) bar by bar. Enters long on a gated BUY,
    exits on SL/TP (checked intrabar against high/low) or a SELL signal.

    ``use_trailing`` mirrors the live PaperTrader's trailing stop via the shared
    ``strategies.trail_stop`` helper (``TRAILING_MODE`` selects ATR-scaled vs
    legacy fixed-percent). It defaults to True so the gate is an HONEST proxy
    for live — without it the backtest rides winners to the fixed take-profit
    that live never reaches, badly overstating the edge.

    Re-entry cooldowns (``REENTRY_COOLDOWN_S``/``STOPOUT_COOLDOWN_S``) and the
    per-day trade cap (``MAX_TRADES_PER_SYMBOL_PER_DAY``) are modeled too, so
    the churn-control settings are validated by the same gate. 0 disables.
    """
    fee = settings.FEE_PCT
    slip = settings.SLIPPAGE_PCT
    trail_trigger = settings.TRAILING_STOP_TRIGGER
    trail_offset = settings.TRAILING_STOP_OFFSET
    warmup = _warmup(df)
    if len(df) <= warmup + 2:
        return BacktestResult(equity=[initial_capital],
                              metrics=metrics.summarize([], [initial_capital], periods_per_year))

    cash = initial_capital
    pos = None              # dict: qty, entry, stop, take, bucket
    trades: list[dict] = []
    equity: list[float] = []
    last_exit_ts: float | None = None   # churn control (single-symbol frame)
    last_exit_reason = ""
    entries_by_day: dict[int, int] = {}

    for i in range(warmup, len(df)):
        window = df.iloc[: i + 1]
        bar = df.iloc[i]
        price = float(bar["close"])

        # ── manage an open position (intrabar SL/TP, then signal exit) ──────────
        if pos is not None:
            exit_price, reason = None, None
            if float(bar["low"]) <= pos["stop"]:
                exit_price, reason = pos["stop"], "stop_loss"
            elif float(bar["high"]) >= pos["take"]:
                exit_price, reason = pos["take"], "take_profit"
            if exit_price is None:
                tech = compute_indicators(window)
                if tech is not None:
                    strat = strategies.evaluate(window, tech)
                    if strat["action"] == strategies.SELL:
                        exit_price, reason = price, "sell_signal"
            if exit_price is not None:
                fill = exit_price * (1 - slip)
                proceeds = pos["qty"] * fill * (1 - fee)
                pnl = proceeds - pos["cost"]
                cash += proceeds
                trades.append({
                    "entry": pos["entry"], "exit": fill, "qty": pos["qty"],
                    "pnl": pnl, "pnl_pct": pnl / pos["cost"] * 100 if pos["cost"] else 0.0,
                    "bucket": pos["bucket"], "reason": reason,
                })
                pos = None
                last_exit_ts, last_exit_reason = _bar_epoch(df, i), reason
            elif use_trailing:
                # Shared strategies.trail_stop — identical math to the live
                # PaperTrader. Uses this bar's high, so the raised stop applies
                # from the next bar (avoids same-bar SL/trail circularity).
                hi = max(pos["trail_high"], float(bar["high"]))
                candidate = strategies.trail_stop(pos["entry"], pos["take"], hi,
                                                  pos["bucket"], trail_trigger,
                                                  trail_offset)
                if candidate is not None:
                    pos["stop"] = max(pos["stop"], candidate)
                pos["trail_high"] = hi

        # ── consider a new entry when flat ──────────────────────────────────────
        if pos is None:
            tech = compute_indicators(window)
            if tech is not None:
                strat = strategies.evaluate(window, tech)
                composite = tech["technical_total"] * settings.TECHNICAL_WEIGHT + \
                    50.0 * settings.SENTIMENT_WEIGHT  # neutral sentiment in backtest
                if strat["action"] == strategies.BUY and composite >= settings.BUY_THRESHOLD:
                    now_ts = _bar_epoch(df, i)
                    blocked = False
                    if last_exit_ts is not None:
                        cd = (settings.STOPOUT_COOLDOWN_S
                              if last_exit_reason == "stop_loss"
                              else settings.REENTRY_COOLDOWN_S)
                        blocked = cd > 0 and (now_ts - last_exit_ts) < cd
                    day = int(now_ts // 86_400)
                    day_cap = settings.MAX_TRADES_PER_SYMBOL_PER_DAY
                    if day_cap > 0 and entries_by_day.get(day, 0) >= day_cap:
                        blocked = True
                    atr = strat["atr"]
                    bucket = strat["bucket"] or "day"
                    entry = price * (1 + slip)
                    cost = min(cash, settings.MAX_POSITION_USDT)
                    if not blocked and cost >= settings.MIN_TRADE_USDT and atr:
                        qty = (cost / entry) * (1 - fee)
                        stop, take = strategies.atr_stops(entry, atr, bucket)
                        cash -= cost
                        pos = {"qty": qty, "entry": entry, "cost": cost,
                               "stop": stop, "take": take, "bucket": bucket,
                               "trail_high": entry}
                        entries_by_day[day] = entries_by_day.get(day, 0) + 1

        # mark-to-market equity
        held = pos["qty"] * price if pos else 0.0
        equity.append(cash + held)

    return BacktestResult(
        trades=trades, equity=equity,
        metrics=metrics.summarize(trades, equity, periods_per_year),
    )


# ── Walk-forward + Monte Carlo helpers ────────────────────────────────────────

def walk_forward_windows(df: pd.DataFrame, train_bars: int, test_bars: int):
    """Yield (train_df, test_df) tuples rolling forward. The strategy has no
    fitted params yet, so today this validates *stability* across out-of-sample
    windows; it's ready for parameter optimisation later."""
    start = 0
    n = len(df)
    while start + train_bars + test_bars <= n:
        train = df.iloc[start: start + train_bars]
        test = df.iloc[start + train_bars: start + train_bars + test_bars]
        yield train, test
        start += test_bars


def walk_forward_report(df: pd.DataFrame, train_bars: int, test_bars: int,
                        initial_capital: float = 1000.0) -> dict:
    oos = []
    for _, test in walk_forward_windows(df, train_bars, test_bars):
        res = run_backtest(test, initial_capital=initial_capital)
        oos.append(res.metrics)
    if not oos:
        return {"windows": 0}
    return {
        "windows": len(oos),
        "avg_sharpe": round(sum(m["sharpe"] for m in oos) / len(oos), 4),
        "avg_return": round(sum(m["total_return"] for m in oos) / len(oos), 4),
        "worst_drawdown": round(max(m["max_drawdown"] for m in oos), 4),
        "per_window": oos,
    }
