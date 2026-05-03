"""
Market data helper.
Thin wrapper around CoinDCXClient that adds caching to avoid
hammering the API with repeated calls for the same candle data.
"""

import time
import pandas as pd
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.exchange.coindcx_client import CoinDCXClient


class MarketData:
    CACHE_TTL = 60  # seconds — don't re-fetch candles more than once per minute

    def __init__(self, client: CoinDCXClient):
        self._client = client
        self._cache: dict[str, tuple[float, pd.DataFrame]] = {}  # symbol → (ts, df)

    def get_ohlcv(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Return cached OHLCV DataFrame if fresh, otherwise fetch from exchange.
        Returns None if the fetch fails.
        """
        now = time.time()
        cached = self._cache.get(symbol)
        if cached and (now - cached[0]) < self.CACHE_TTL:
            return cached[1]

        try:
            df = self._client.fetch_ohlcv(symbol)
            if df is not None and not df.empty:
                self._cache[symbol] = (now, df)
                return df
        except Exception:
            pass
        return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Fetch the latest trade price for a symbol."""
        try:
            ticker = self._client.fetch_ticker(symbol)
            return float(ticker["last"])
        except Exception:
            return None

    def get_top_momentum_symbols(self) -> list[str]:
        try:
            return self._client.get_top_momentum_symbols()
        except Exception:
            return []
