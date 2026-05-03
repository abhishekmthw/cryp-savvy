"""
CoinDCX exchange client built on top of ccxt.

Two modes:
- **Public**: no keys — used by the shared MarketDataScanner for tickers,
  OHLCV, and momentum ranking. CoinDCX exposes these endpoints unauthenticated.
- **Authenticated**: per-user keys — used by each UserBot for placing orders
  and reading their own balance.
"""

from __future__ import annotations

import sys
import os
from typing import Optional

import ccxt
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


class CoinDCXClient:
    def __init__(self, api_key: str = "", api_secret: str = ""):
        self._exchange = ccxt.coindcx({
            "apiKey":          api_key,
            "secret":          api_secret,
            "enableRateLimit": True,
        })
        self._markets: Optional[dict] = None
        self._has_keys = bool(api_key and api_secret)

    @property
    def has_keys(self) -> bool:
        return self._has_keys

    # ── Market Data (public) ──────────────────────────────────────────────────

    def load_markets(self) -> dict:
        if self._markets is None:
            self._markets = self._exchange.load_markets()
        return self._markets

    def get_inr_symbols(self) -> list[str]:
        markets = self.load_markets()
        return [
            sym for sym, data in markets.items()
            if data.get("quote") == settings.QUOTE_CURRENCY
            and data.get("active", True)
            and data.get("type", "spot") == "spot"
        ]

    def get_tickers(self, symbols: list[str]) -> dict:
        tickers = {}
        for sym in symbols:
            try:
                tickers[sym] = self._exchange.fetch_ticker(sym)
            except Exception:
                pass
        return tickers

    def get_top_momentum_symbols(self, n: int = settings.TOP_N_COINS) -> list[str]:
        symbols = self.get_inr_symbols()
        tickers = self.get_tickers(symbols)

        rows = []
        for sym, t in tickers.items():
            change = t.get("percentage") or 0.0
            volume = t.get("quoteVolume") or 0.0
            rows.append({"symbol": sym, "change": change, "volume": volume})

        if not rows:
            return []

        df = pd.DataFrame(rows)
        df["change_rank"] = df["change"].rank(ascending=True)
        df["volume_rank"] = df["volume"].rank(ascending=True)
        df["score"] = (df["change_rank"] + df["volume_rank"]) / 2
        df = df.sort_values("score", ascending=False)
        df = df[df["change"] > 0]
        return df["symbol"].head(n).tolist()

    def fetch_ohlcv(self, symbol: str, timeframe: str = settings.TIMEFRAME,
                    limit: int = settings.CANDLE_LIMIT) -> pd.DataFrame:
        raw = self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("timestamp")
        return df.astype(float)

    def fetch_ticker(self, symbol: str) -> dict:
        return self._exchange.fetch_ticker(symbol)

    # ── Order Placement (authenticated) ───────────────────────────────────────

    def place_market_buy(self, symbol: str, amount_inr: float) -> dict:
        if not self._has_keys:
            raise RuntimeError("Cannot place orders without API keys")
        ticker = self.fetch_ticker(symbol)
        price  = ticker["last"]
        qty    = amount_inr / price
        return self._exchange.create_market_buy_order(symbol, qty)

    def place_market_sell(self, symbol: str, qty: float) -> dict:
        if not self._has_keys:
            raise RuntimeError("Cannot place orders without API keys")
        return self._exchange.create_market_sell_order(symbol, qty)

    def fetch_balance(self) -> dict:
        if not self._has_keys:
            raise RuntimeError("Cannot fetch balance without API keys")
        return self._exchange.fetch_balance()
