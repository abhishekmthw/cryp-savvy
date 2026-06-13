"""
Sentiment data fetcher.
Sources:
  1. Public crypto news RSS feeds — VADER-scored headlines matching the coin
  2. Reddit (PRAW)                — mention count from r/CryptoCurrency in the last hour
"""

import re
import time
import xml.etree.ElementTree as ET
import requests
import praw
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


_vader = SentimentIntensityAnalyzer()

# Per-symbol composite-score cache
_sentiment_cache: dict[str, tuple[float, float]] = {}   # symbol → (ts, score)
_CACHE_TTL = 300   # 5 minutes

# Public RSS feeds — no signup, no key, no rate limit. Add/remove as needed.
RSS_FEEDS = (
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://u.today/rss",
)
_RSS_USER_AGENT = "Mozilla/5.0 (compatible; CrypSavvy/1.0)"

# Feed-level cache so a single scan across N coins fetches each feed once.
_news_items_cache: tuple[float, list[tuple[str, str]]] = (0.0, [])
_NEWS_CACHE_TTL = 300


def _coin_name(symbol: str) -> str:
    """Extract the base currency name from a symbol like 'BTC/INR' → 'BTC'."""
    return symbol.split("/")[0].upper()


# ── RSS news ──────────────────────────────────────────────────────────────────

def _fetch_news_items() -> list[tuple[str, str]]:
    """Fetch + parse every RSS feed once; return cached [(title, description), ...]."""
    global _news_items_cache
    now = time.time()
    cached_ts, cached_items = _news_items_cache
    if cached_items and (now - cached_ts) < _NEWS_CACHE_TTL:
        return cached_items

    items: list[tuple[str, str]] = []
    headers = {"User-Agent": _RSS_USER_AGENT}
    for feed_url in RSS_FEEDS:
        try:
            resp = requests.get(feed_url, headers=headers, timeout=8)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception:
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            if title:
                items.append((title, desc))

    _news_items_cache = (now, items)
    return items


def _fetch_rss_news_score(coin: str) -> float:
    """
    Score recent news headlines against `coin`.
    Returns a sentiment score in [-1.0, +1.0] from VADER analysis of matching
    titles; 0.0 on no matches or any error.

    RSS feeds are not coin-filtered, so we substring-match the ticker as a
    whole word. Coverage is strong for majors (BTC, ETH, SOL…) and thinner
    for long-tail alts — fine because the bot scans top-momentum coins.
    """
    items = _fetch_news_items()
    if not items:
        return 0.0

    pattern = re.compile(rf"\b{re.escape(coin.upper())}\b", re.IGNORECASE)

    pos_total = neg_total = 0
    matched = 0
    for title, desc in items:
        if not pattern.search(f"{title} {desc}"):
            continue
        matched += 1
        score = _vader.polarity_scores(title)["compound"]
        if score > 0.05:
            pos_total += 1
        elif score < -0.05:
            neg_total += 1
        if matched >= 20:
            break

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
    news_score   = _fetch_rss_news_score(coin)       # [-1, +1]
    reddit_score = _fetch_reddit_score(coin)         # [-1, +1]

    # Average both sources (each equally weighted within the sentiment block)
    if settings.REDDIT_CLIENT_ID:
        combined = (news_score + reddit_score) / 2
    else:
        combined = news_score   # Fallback to news only

    _sentiment_cache[symbol] = (now, combined)
    return combined


def sentiment_to_score_0_100(sentiment: float) -> float:
    """
    Map [-1.0, +1.0] sentiment to [0, 100] for use in the signal engine.
    0.0 sentiment → 50 (neutral midpoint).
    """
    return (sentiment + 1.0) / 2.0 * 100
