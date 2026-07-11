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


def run_backtest(df: pd.DataFrame, *, initial_capital: float = 1000.0,
                 periods_per_year: float = 365 * 24,
                 use_trailing: bool = True) -> BacktestResult:
    """
    Replay ``df`` (oldest-first OHLCV) bar by bar. Enters long on a gated BUY,
    exits on SL/TP (checked intrabar against high/low) or a SELL signal.

    ``use_trailing`` mirrors the live PaperTrader's trailing stop (arms at
    ``TRAILING_STOP_TRIGGER`` gain, trails ``TRAILING_STOP_OFFSET`` below the
    running high). It defaults to True so the gate is an HONEST proxy for live —
    without it the backtest rides winners to the fixed take-profit that live
    never reaches, badly overstating the edge.
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
            elif use_trailing:
                # Mirror PaperTrader.update_trailing_stop: once the running high
                # is far enough above entry, ratchet the stop up beneath it. Uses
                # this bar's high, so the raised stop applies from the next bar
                # (avoids same-bar SL/trail circularity).
                hi = max(pos["trail_high"], float(bar["high"]))
                if (hi - pos["entry"]) / pos["entry"] >= trail_trigger:
                    pos["stop"] = max(pos["stop"], hi * (1 - trail_offset))
                pos["trail_high"] = hi

        # ── consider a new entry when flat ──────────────────────────────────────
        if pos is None:
            tech = compute_indicators(window)
            if tech is not None:
                strat = strategies.evaluate(window, tech)
                composite = tech["technical_total"] * settings.TECHNICAL_WEIGHT + \
                    50.0 * settings.SENTIMENT_WEIGHT  # neutral sentiment in backtest
                if strat["action"] == strategies.BUY and composite >= settings.BUY_THRESHOLD:
                    atr = strat["atr"]
                    bucket = strat["bucket"] or "day"
                    entry = price * (1 + slip)
                    cost = min(cash, settings.MAX_POSITION_USDT)
                    if cost >= settings.MIN_TRADE_USDT and atr:
                        qty = (cost / entry) * (1 - fee)
                        stop, take = strategies.atr_stops(entry, atr, bucket)
                        cash -= cost
                        pos = {"qty": qty, "entry": entry, "cost": cost,
                               "stop": stop, "take": take, "bucket": bucket,
                               "trail_high": entry}

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
