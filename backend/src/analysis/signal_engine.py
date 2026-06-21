"""
Signal engine.
Combines technical score (0–100) and sentiment score (0–100)
into a single composite score and emits BUY / SELL / HOLD decisions.
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.analysis import strategies
from src.analysis.technical import compute_indicators
from src.data.sentiment import get_sentiment_score, sentiment_to_score_0_100
from src.data.market_data import MarketData


class Signal:
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


def analyse_symbol(symbol: str, market_data: MarketData) -> dict:
    """
    Full analysis pipeline for one symbol.

    The regime-aware strategy ensemble decides the entry/exit and the capital
    bucket (day vs long); the composite technical+sentiment score is layered on
    as a quality gate so a BUY only fires when conviction clears BUY_THRESHOLD.
    """
    result = {
        "symbol":          symbol,
        "action":          Signal.HOLD,
        "composite_score": 0.0,
        "technical_score": 0.0,
        "sentiment_score": 50.0,
        "regime":          None,
        "bucket":          None,
        "strategy":        "none",
        "atr":             None,
        "details":         {},
    }

    # 1. Technical analysis
    df = market_data.get_ohlcv(symbol)
    if df is None or df.empty:
        return result

    tech = compute_indicators(df)
    if tech is None:
        return result

    technical_score = float(tech["technical_total"])   # 0–100

    # 2. Sentiment analysis (capped to ≤10% weight until validated)
    sentiment_raw   = get_sentiment_score(symbol)      # -1 to +1
    sentiment_score = sentiment_to_score_0_100(sentiment_raw)  # 0–100

    # 3. Composite weighted score (quality gate)
    composite = (
        technical_score * settings.TECHNICAL_WEIGHT
        + sentiment_score * settings.SENTIMENT_WEIGHT
    )

    # 4. Regime-aware strategy decision
    strat = strategies.evaluate(df, tech)
    action = strat["action"]

    # 5. Quality gate: a BUY must also clear the composite threshold; a strategy
    #    SELL always passes (exits are not gated).
    if action == Signal.BUY and composite < settings.BUY_THRESHOLD:
        action = Signal.HOLD

    result.update({
        "action":          action,
        "composite_score": round(composite, 2),
        "technical_score": round(technical_score, 2),
        "sentiment_score": round(sentiment_score, 2),
        "regime":          strat["regime"],
        "bucket":          strat["bucket"],
        "strategy":        strat["strategy"],
        "atr":             strat["atr"],
        "details":         tech,
    })
    return result


def analyse_open_position(symbol: str, market_data: MarketData) -> dict:
    """
    Focused analysis for a coin we already hold.
    Checks whether we should exit (sell signal or stop/TP already managed by risk manager).
    """
    return analyse_symbol(symbol, market_data)
