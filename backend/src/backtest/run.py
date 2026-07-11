"""
Backtest runner + live-readiness gate.

Fetches recent OHLCV for the core symbols from CoinDCX (public endpoint, no keys
needed) and runs a walk-forward backtest, printing the metrics and a GO / NO-GO
verdict. This is the validation gate referenced by the runbook — only flip
LIVE_TRADING_ENABLED=true once this prints GO and paper trading looks healthy.

    python -m src.backtest.run            # default symbols/timeframe
    python -m src.backtest.run BTC/USDT ETH/USDT
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.backtest.engine import run_backtest, walk_forward_report
from src.exchange.coindcx_client import CoinDCXClient

# Go/no-go thresholds (conservative — the strategy must show a real edge OOS).
MIN_OOS_SHARPE = 0.5
MAX_OOS_DRAWDOWN = 0.35   # aligns with the aggressive pause breaker


def main(symbols: list[str], timeframe: str = settings.TIMEFRAME, limit: int = 1000) -> int:
    # NOTE: use the SAME timeframe the live bot trades on (settings.TIMEFRAME,
    # default '1h') so the gate is representative. CoinDCX's public candles API
    # only accepts [1m, 15m, 1h, 1d] — the previous hardcoded '4h' 422'd on every
    # fetch, which surfaced as a silent NO-GO (the gate never actually ran).
    client = CoinDCXClient()
    overall_go = True
    for symbol in symbols:
        print(f"\n=== {symbol} ({timeframe}, {limit} candles) ===")
        try:
            df = client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as exc:
            print(f"  could not fetch candles: {exc}")
            overall_go = False
            continue
        if len(df) < 300:
            print(f"  not enough data ({len(df)} candles)")
            overall_go = False
            continue

        full = run_backtest(df)
        print("  full-sample:", full.metrics)

        wf = walk_forward_report(df, train_bars=min(400, len(df) // 2),
                                 test_bars=max(50, len(df) // 8))
        print("  walk-forward:", {k: v for k, v in wf.items() if k != "per_window"})

        ok = (wf.get("windows", 0) > 0
              and wf.get("avg_sharpe", 0) >= MIN_OOS_SHARPE
              and wf.get("worst_drawdown", 1) <= MAX_OOS_DRAWDOWN)
        print(f"  verdict: {'GO' if ok else 'NO-GO'}")
        overall_go = overall_go and ok

    print(f"\n{'='*40}\nOVERALL: {'GO — validation passed' if overall_go else 'NO-GO — keep paper trading'}")
    print("Live trading is gated by LIVE_TRADING_ENABLED; only enable it on GO.")
    return 0 if overall_go else 1


if __name__ == "__main__":
    syms = sys.argv[1:] or settings.CORE_SYMBOLS
    raise SystemExit(main(syms))
