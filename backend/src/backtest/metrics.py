"""
Performance metrics for the backtester. Pure functions — no I/O, no globals.

- equity-curve metrics: total return, max drawdown, Sharpe
- per-trade metrics: win rate, profit factor, expectancy
"""

from __future__ import annotations

import math
from statistics import mean, pstdev


def total_return(equity: list[float]) -> float:
    if not equity or equity[0] == 0:
        return 0.0
    return equity[-1] / equity[0] - 1.0


def max_drawdown(equity: list[float]) -> float:
    """Largest peak-to-trough decline as a positive fraction (0.2 == −20%)."""
    peak = float("-inf")
    mdd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return mdd


def sharpe(returns: list[float], periods_per_year: float = 365 * 24) -> float:
    """Annualised Sharpe from per-period returns (risk-free ≈ 0)."""
    if len(returns) < 2:
        return 0.0
    sd = pstdev(returns)
    if sd == 0:
        return 0.0
    return (mean(returns) / sd) * math.sqrt(periods_per_year)


def win_rate(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t["pnl"] > 0)
    return wins / len(trades)


def profit_factor(trades: list[dict]) -> float:
    gross_win = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    if gross_loss == 0:
        return float("inf") if gross_win > 0 else 0.0
    return gross_win / gross_loss


def expectancy(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    return mean(t["pnl"] for t in trades)


def summarize(trades: list[dict], equity: list[float],
              periods_per_year: float = 365 * 24) -> dict:
    rets = [equity[i] / equity[i - 1] - 1.0
            for i in range(1, len(equity)) if equity[i - 1]]
    return {
        "num_trades":    len(trades),
        "win_rate":      round(win_rate(trades), 4),
        "profit_factor": round(profit_factor(trades), 4),
        "expectancy":    round(expectancy(trades), 4),
        "total_return":  round(total_return(equity), 4),
        "max_drawdown":  round(max_drawdown(equity), 4),
        "sharpe":        round(sharpe(rets, periods_per_year), 4),
    }
