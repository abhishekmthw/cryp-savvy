"""
Sentiment data fetcher.
Sources:
  1. CryptoPanic API — aggregated news with sentiment labels
  2. Reddit (PRAW)   — mention count from r/CryptoCurrency in the last hour
"""

import time
import requests
import praw
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


_vader = SentimentIntensityAnalyzer()

# Simple in-process cache to avoid hammering free-tier APIs
_sentiment_cache: dict[str, tuple[float, float]] = {}   # symbol → (ts, score)
_CACHE_TTL = 300   # 5 minutes


def _coin_name(symbol: str) -> str:
    """Extract the base currency name from a symbol like 'BTC/INR' → 'BTC'."""
    return symbol.split("/")[0].upper()


# ── CryptoPanic ───────────────────────────────────────────────────────────────

def _fetch_cryptopanic_score(coin: str) -> float:
    """
    Query CryptoPanic for recent news about `coin`.
    Returns a sentiment score in [-1.0, +1.0]:
      +1.0 = all positive, -1.0 = all negative, 0.0 = neutral / no data.
    Falls back to 0.0 on any error.
    """
    if not settings.CRYPTOPANIC_API_KEY:
        return 0.0

    url = "https://cryptopanic.com/api/v1/posts/"
    params = {
        "auth_token": settings.CRYPTOPANIC_API_KEY,
        "currencies": coin,
        "public": "true",
        "filter": "hot",
        "limit": 10,
    }
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return 0.0

    results = data.get("results", [])
    if not results:
        return 0.0

    # CryptoPanic provides a "votes" object per post: positive / negative / important
    pos_total = neg_total = 0
    for post in results:
        votes = post.get("votes", {})
        pos_total += votes.get("positive", 0) + votes.get("important", 0)
        neg_total += votes.get("negative", 0)

        # Also run VADER on the headline for additional signal
        title = post.get("title", "")
        if title:
            score = _vader.polarity_scores(title)["compound"]
            if score > 0.05:
                pos_total += 1
            elif score < -0.05:
                neg_total += 1

    total = pos_total + neg_total
    if total == 0:
        return 0.0
    return (pos_total - neg_total) / total   # range [-1, +1]


# ── Reddit ────────────────────────────────────────────────────────────────────

_reddit: Optional[praw.Reddit] = None


def _get_reddit() -> Optional[praw.Reddit]:
    global _reddit
    if _reddit is not None:
        return _reddit
    if not (settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET):
        return None
    try:
        _reddit = praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            user_agent=settings.REDDIT_USER_AGENT,
        )
        return _reddit
    except Exception:
        return None


def _fetch_reddit_score(coin: str) -> float:
    """
    Search r/CryptoCurrency for posts mentioning the coin in the last hour.
    Returns a normalised score in [0.0, 1.0]:
      0.0 = no mentions, 1.0 = many highly-upvoted positive mentions.
    """
    reddit = _get_reddit()
    if reddit is None:
        return 0.0

    try:
        sub        = reddit.subreddit("CryptoCurrency")
        hour_ago   = time.time() - 3600
        pos_score  = 0
        neg_score  = 0
        count      = 0

        for post in sub.search(coin, sort="new", time_filter="day", limit=20):
            if post.created_utc < hour_ago:
                continue
            count += 1
            vader_score = _vader.polarity_scores(post.title)["compound"]
            if vader_score > 0.05:
                pos_score += 1
            elif vader_score < -0.05:
                neg_score += 1

        if count == 0:
            return 0.0

        # Return fraction of positive mentions, normalised to [-1, +1]
        return (pos_score - neg_score) / count

    except Exception:
        return 0.0


# ── Public API ────────────────────────────────────────────────────────────────

def get_sentiment_score(symbol: str) -> float:
    """
    Returns a composite sentiment score in [-1.0, +1.0] for the given trading pair.
    Positive = bullish sentiment, negative = bearish.
    Uses cache to respect free-tier rate limits.
    """
    now = time.time()
    cached = _sentiment_cache.get(symbol)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    coin = _coin_name(symbol)
    cp_score     = _fetch_cryptopanic_score(coin)    # [-1, +1]
    reddit_score = _fetch_reddit_score(coin)         # [-1, +1]

    # Average both sources (each equally weighted within the sentiment block)
    if settings.REDDIT_CLIENT_ID:
        combined = (cp_score + reddit_score) / 2
    else:
        combined = cp_score   # Fallback to CryptoPanic only

    _sentiment_cache[symbol] = (now, combined)
    return combined


def sentiment_to_score_0_100(sentiment: float) -> float:
    """
    Map [-1.0, +1.0] sentiment to [0, 100] for use in the signal engine.
    0.0 sentiment → 50 (neutral midpoint).
    """
    return (sentiment + 1.0) / 2.0 * 100
