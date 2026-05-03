"""
CoinDCX exchange client built on top of ccxt.
Provides a clean interface for fetching market data and placing orders.
"""

import ccxt
import pandas as pd
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


class CoinDCXClient:
    def __init__(self):
        self._exchange = ccxt.coindcx({
            "apiKey": settings.COINDCX_API_KEY,
            "secret": settings.COINDCX_API_SECRET,
            "enableRateLimit": True,
        })
        self._markets: Optional[dict] = None

    # ── Market Data ───────────────────────────────────────────────────────────

    def load_markets(self) -> dict:
        if self._markets is None:
            self._markets = self._exchange.load_markets()
        return self._markets

    def get_inr_symbols(self) -> list[str]:
        """Return all active spot symbols quoted in INR."""
        markets = self.load_markets()
        return [
            sym for sym, data in markets.items()
            if data.get("quote") == settings.QUOTE_CURRENCY
            and data.get("active", True)
            and data.get("type", "spot") == "spot"
        ]

    def get_tickers(self, symbols: list[str]) -> dict:
        """Fetch 24h ticker data for a list of symbols. Returns dict keyed by symbol."""
        tickers = {}
        for sym in symbols:
            try:
                tickers[sym] = self._exchange.fetch_ticker(sym)
            except Exception:
                pass
        return tickers

    def get_top_momentum_symbols(self, n: int = settings.TOP_N_COINS) -> list[str]:
        """
        Rank all INR pairs by a composite momentum score:
            score = (24h_change_pct * 0.5) + (24h_volume_rank * 0.5)
        Returns top-n symbols.
        """
        symbols = self.get_inr_symbols()
        tickers = self.get_tickers(symbols)

        rows = []
        for sym, t in tickers.items():
            change = t.get("percentage") or 0.0     # 24h % change
            volume = t.get("quoteVolume") or 0.0    # volume in INR
            rows.append({"symbol": sym, "change": change, "volume": volume})

        if not rows:
            return []

        df = pd.DataFrame(rows)
        # Rank both metrics (higher is better) then average the ranks
        df["change_rank"] = df["change"].rank(ascending=True)
        df["volume_rank"] = df["volume"].rank(ascending=True)
        df["score"] = (df["change_rank"] + df["volume_rank"]) / 2
        df = df.sort_values("score", ascending=False)

        # Only consider coins with positive 24h change (upward momentum)
        df = df[df["change"] > 0]
        return df["symbol"].head(n).tolist()

    def fetch_ohlcv(self, symbol: str, timeframe: str = settings.TIMEFRAME,
                    limit: int = settings.CANDLE_LIMIT) -> pd.DataFrame:
        """
        Fetch OHLCV candles for a symbol.
        Returns a DataFrame with columns: timestamp, open, high, low, close, volume.
        """
        raw = self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("timestamp")
        return df.astype(float)

    def fetch_ticker(self, symbol: str) -> dict:
        return self._exchange.fetch_ticker(symbol)

    # ── Order Placement (live only) ───────────────────────────────────────────

    def place_market_buy(self, symbol: str, amount_inr: float) -> dict:
        """Place a market buy order for `amount_inr` worth of the asset."""
        ticker = self.fetch_ticker(symbol)
        price  = ticker["last"]
        qty    = amount_inr / price
        return self._exchange.create_market_buy_order(symbol, qty)

    def place_market_sell(self, symbol: str, qty: float) -> dict:
        """Place a market sell order for the given quantity."""
        return self._exchange.create_market_sell_order(symbol, qty)

    def fetch_balance(self) -> dict:
        return self._exchange.fetch_balance()
