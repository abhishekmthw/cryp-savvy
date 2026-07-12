"""
Backtest runner + live-readiness gate.

Fetches recent OHLCV for the core symbols from CoinDCX (public endpoint, no keys
needed) and runs a walk-forward backtest, printing the metrics and a GO / NO-GO
verdict. This is the validation gate referenced by the runbook — only flip
LIVE_TRADING_ENABLED=true once this prints GO and paper trading looks healthy.

    python -m src.backtest.run            # default symbols/timeframe
    python -m src.backtest.run BTC/USDT ETH/USDT
    python -m src.backtest.run --profile legacy BTC/USDT   # July-behavior A/B

The ``--profile`` flag drives the A/B validation of the post-July strategy
changes: ``improved`` (default) runs with settings.py as-is; ``legacy``
overrides the new exit/churn settings back to the July values so the two runs
isolate exactly what the improvements change.
"""

from __future__ import annotations

import sys
import os
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.backtest.engine import run_backtest, walk_forward_report
from src.exchange.coindcx_client import CoinDCXClient

# Go/no-go thresholds (conservative — the strategy must show a real edge OOS).
MIN_OOS_SHARPE = 0.5
MAX_OOS_DRAWDOWN = 0.35   # aligns with the aggressive pause breaker

# The July 2026 parameterisation — what "legacy" restores for the A/B run.
LEGACY_PROFILE = {
    "TRAILING_MODE":              "fixed_pct",
    "MAX_STOP_DISTANCE_PCT_DAY":  None,
    "MAX_STOP_DISTANCE_PCT_LONG": None,
    "REENTRY_COOLDOWN_S":         0,
    "STOPOUT_COOLDOWN_S":         0,
    "MAX_TRADES_PER_SYMBOL_PER_DAY": 0,
}


def apply_profile(profile: str) -> None:
    if profile == "legacy":
        for key, value in LEGACY_PROFILE.items():
            setattr(settings, key, value)
    elif profile != "improved":
        raise SystemExit(f"unknown profile {profile!r} (use legacy|improved)")


def main(symbols: list[str], timeframe: str = settings.TIMEFRAME, limit: int = 1000,
         profile: str = "improved") -> int:
    # NOTE: use the SAME timeframe the live bot trades on (settings.TIMEFRAME,
    # default '1h') so the gate is representative. CoinDCX's public candles API
    # only accepts [1m, 15m, 1h, 1d] — the previous hardcoded '4h' 422'd on every
    # fetch, which surfaced as a silent NO-GO (the gate never actually ran).
    apply_profile(profile)
    print(f"profile: {profile}"
          + (" (July-behavior overrides active)" if profile == "legacy" else ""))
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
        # Exit-reason histogram — the July failure signature was 0 take-profit
        # hits vs 117 stop-outs; this makes the mix directly visible per run.
        reasons = Counter(t.get("reason", "unknown") for t in full.trades)
        print("  exit reasons:", dict(sorted(reasons.items())))

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
    args = sys.argv[1:]
    profile = "improved"
    if "--profile" in args:
        idx = args.index("--profile")
        try:
            profile = args[idx + 1]
        except IndexError:
            raise SystemExit("--profile requires a value (legacy|improved)")
        del args[idx:idx + 2]
    syms = args or settings.CORE_SYMBOLS
    raise SystemExit(main(syms, profile=profile))
