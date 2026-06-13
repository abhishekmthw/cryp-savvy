"""
CoinDCX exchange client built on top of CoinDCX's public + private REST API.

ccxt does not include CoinDCX, so this is a direct implementation against
https://api.coindcx.com (ticker, markets, orders, balance) and
https://public.coindcx.com (OHLCV candles).

Two modes:
- **Public**: no keys — used by the shared MarketDataScanner for tickers,
  OHLCV, and momentum ranking. CoinDCX exposes these endpoints unauthenticated.
- **Authenticated**: per-user keys — used by each UserBot for placing orders
  and reading their own balance. Auth is HMAC-SHA256(secret, body), passed in
  the X-AUTH-SIGNATURE header alongside X-AUTH-APIKEY.

Symbols are CCXT-style ('BTC/INR') for compatibility with the rest of the
codebase; the client maps them to CoinDCX's two native formats internally
('BTCINR' for ticker/order endpoints, 'I-BTC_INR' for candles).
Note: CoinDCX's API reverses the base/quote nomenclature vs ccxt — their
``target_currency`` is the traded asset (BTC), their ``base_currency`` is the
quote (INR). We rename in ``load_markets`` so call sites match ccxt convention.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from typing import Optional

import pandas as pd
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


_API_BASE    = "https://api.coindcx.com"
_PUBLIC_BASE = "https://public.coindcx.com"
_TIMEOUT     = 10  # seconds


def _ccxt_symbol_to_market(symbol: str) -> str:
    """'BTC/INR' → 'BTCINR' — used by ticker + order endpoints."""
    return symbol.replace("/", "")


def _ccxt_symbol_to_pair(symbol: str) -> str:
    """'BTC/INR' → 'I-BTC_INR' — used by the candles endpoint."""
    base, quote = symbol.split("/")
    return f"I-{base}_{quote}"


class CoinDCXClient:
    def __init__(self, api_key: str = "", api_secret: str = ""):
        self._api_key    = api_key
        self._api_secret = api_secret
        self._has_keys   = bool(api_key and api_secret)
        self._markets:   Optional[dict] = None
        self._session    = requests.Session()

    @property
    def has_keys(self) -> bool:
        return self._has_keys

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _public_get(self, url: str, params: Optional[dict] = None):
        resp = self._session.get(url, params=params or {}, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _signed_post(self, path: str, payload: Optional[dict] = None):
        if not self._has_keys:
            raise RuntimeError("CoinDCX API keys required for authenticated endpoints")
        body = json.dumps(
            {**(payload or {}), "timestamp": int(time.time() * 1000)},
            separators=(",", ":"),
        )
        signature = hmac.new(
            self._api_secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        headers = {
            "Content-Type":     "application/json",
            "X-AUTH-APIKEY":    self._api_key,
            "X-AUTH-SIGNATURE": signature,
        }
        resp = self._session.post(
            f"{_API_BASE}{path}", data=body, headers=headers, timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Market data (public) ──────────────────────────────────────────────────

    def load_markets(self) -> dict:
        if self._markets is not None:
            return self._markets

        details = self._public_get(f"{_API_BASE}/exchange/v1/markets_details")
        markets: dict = {}
        for m in details:
            base  = m.get("target_currency_short_name")
            quote = m.get("base_currency_short_name")
            if not base or not quote:
                continue
            symbol = f"{base}/{quote}"
            markets[symbol] = {
                "symbol": symbol,
                "base":   base,
                "quote":  quote,
                "active": m.get("status") == "active",
                "type":   "spot",
                "id":     m.get("coindcx_name") or m.get("symbol"),
                "pair":   m.get("pair"),
                "precision": {
                    "amount": m.get("target_currency_precision"),
                    "price":  m.get("base_currency_precision"),
                },
                "limits": {
                    "amount":   {"min": m.get("min_quantity"), "max": m.get("max_quantity")},
                    "price":    {"min": m.get("min_price"),    "max": m.get("max_price")},
                    "notional": {"min": m.get("min_notional")},
                },
                "info": m,
            }

        self._markets = markets
        return markets

    def get_inr_symbols(self) -> list[str]:
        markets = self.load_markets()
        return [
            sym for sym, data in markets.items()
            if data.get("quote") == settings.QUOTE_CURRENCY
            and data.get("active", True)
            and data.get("type", "spot") == "spot"
        ]

    @staticmethod
    def _ticker_from_raw(raw: dict, ccxt_symbol: str) -> dict:
        last = float(raw["last_price"]) if raw.get("last_price") else None
        # Empirically, CoinDCX's `volume` field on /exchange/ticker is already
        # in the QUOTE currency (INR for INR pairs), not the base — verified
        # by cross-checking against plausible daily INR turnover for major
        # pairs (BTC/SOL/DOGE). So map it straight to `quoteVolume`.
        quote_volume = float(raw["volume"]) if raw.get("volume") else 0.0
        ts = raw.get("timestamp")
        return {
            "symbol":      ccxt_symbol,
            "last":        last,
            "bid":         float(raw["bid"]) if raw.get("bid") else None,
            "ask":         float(raw["ask"]) if raw.get("ask") else None,
            "high":        float(raw["high"]) if raw.get("high") else None,
            "low":         float(raw["low"])  if raw.get("low")  else None,
            "baseVolume":  quote_volume / last if last else 0.0,
            "quoteVolume": quote_volume,
            "percentage":  float(raw["change_24_hour"]) if raw.get("change_24_hour") else 0.0,
            "timestamp":   int(ts) * 1000 if ts else None,
            "info":        raw,
        }

    def _fetch_all_tickers_indexed(self) -> dict:
        """One call to /exchange/ticker; return {ccxt_symbol → ticker_dict}."""
        raw_tickers = self._public_get(f"{_API_BASE}/exchange/ticker")
        markets = self.load_markets()
        coindcx_to_ccxt = {data.get("id"): sym for sym, data in markets.items()}
        out: dict = {}
        for t in raw_tickers:
            sym = coindcx_to_ccxt.get(t.get("market"))
            if not sym:
                continue
            out[sym] = self._ticker_from_raw(t, sym)
        return out

    def get_tickers(self, symbols: list[str]) -> dict:
        indexed = self._fetch_all_tickers_indexed()
        return {sym: indexed[sym] for sym in symbols if sym in indexed}

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
        pair = _ccxt_symbol_to_pair(symbol)
        raw = self._public_get(
            f"{_PUBLIC_BASE}/market_data/candles",
            params={"pair": pair, "interval": timeframe, "limit": limit},
        )
        # CoinDCX returns candles newest-first; reverse so the DataFrame is
        # oldest-first (matches ccxt convention that the rest of the bot uses).
        raw = list(reversed(raw))
        rows = [
            (c["time"], c["open"], c["high"], c["low"], c["close"], c["volume"])
            for c in raw
        ]
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("timestamp")
        return df.astype(float)

    def fetch_ticker(self, symbol: str) -> dict:
        indexed = self._fetch_all_tickers_indexed()
        if symbol not in indexed:
            raise RuntimeError(f"Symbol {symbol!r} not found on CoinDCX")
        return indexed[symbol]

    # ── Order placement (authenticated) ───────────────────────────────────────

    def place_market_buy(self, symbol: str, amount_inr: float) -> dict:
        if not self._has_keys:
            raise RuntimeError("Cannot place orders without API keys")
        ticker = self.fetch_ticker(symbol)
        price  = ticker["last"]
        qty    = amount_inr / price
        return self._signed_post("/exchange/v1/orders/create", {
            "side":           "buy",
            "order_type":     "market_order",
            "market":         _ccxt_symbol_to_market(symbol),
            "total_quantity": qty,
        })

    def place_market_sell(self, symbol: str, qty: float) -> dict:
        if not self._has_keys:
            raise RuntimeError("Cannot place orders without API keys")
        return self._signed_post("/exchange/v1/orders/create", {
            "side":           "sell",
            "order_type":     "market_order",
            "market":         _ccxt_symbol_to_market(symbol),
            "total_quantity": qty,
        })

    def fetch_balance(self) -> dict:
        if not self._has_keys:
            raise RuntimeError("Cannot fetch balance without API keys")
        raw = self._signed_post("/exchange/v1/users/balances")
        # Match ccxt's fetch_balance shape: {currency: {free, used, total}, ...}
        out: dict = {}
        for b in raw:
            cur = b.get("currency")
            if not cur:
                continue
            free = float(b.get("balance") or 0.0)
            used = float(b.get("locked_balance") or 0.0)
            out[cur] = {"free": free, "used": used, "total": free + used}
        return out
