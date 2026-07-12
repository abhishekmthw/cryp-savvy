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
import random
import sys
import time
from typing import Optional

import pandas as pd
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.monitoring.logger import get_logger


log = get_logger()

_API_BASE    = "https://api.coindcx.com"
_PUBLIC_BASE = "https://public.coindcx.com"
# (connect, read) timeouts — a hung exchange must not block a worker tick for 10s.
_TIMEOUT     = (5, 5)

# Retry / backoff
_MAX_RETRIES   = 3
_BACKOFF_BASE  = 0.5   # seconds
_BACKOFF_CAP   = 8.0
_RETRY_AFTER_CAP = 30.0

# Circuit breaker
_CB_FAIL_THRESHOLD = 5      # consecutive transient failures before opening
_CB_COOLDOWN_S     = 60.0   # how long the circuit stays open


class CoinDCXError(Exception):
    """Base error for the CoinDCX client."""


class CircuitOpenError(CoinDCXError):
    """Raised when the circuit breaker is open and the call is short-circuited."""


class _CircuitBreaker:
    """
    Minimal per-client circuit breaker. After ``fail_threshold`` consecutive
    transient failures it opens for ``cooldown`` seconds; calls during that
    window fail fast instead of hammering a degraded exchange.
    """

    def __init__(self, fail_threshold: int = _CB_FAIL_THRESHOLD,
                 cooldown: float = _CB_COOLDOWN_S):
        self._fail_threshold = fail_threshold
        self._cooldown = cooldown
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    def check(self) -> None:
        if self._opened_at is None:
            return
        if time.time() - self._opened_at >= self._cooldown:
            # half-open: allow a probe through
            self._opened_at = None
            return
        raise CircuitOpenError(
            f"CoinDCX circuit open — cooling down ({self._cooldown:.0f}s)"
        )

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._fail_threshold and self._opened_at is None:
            self._opened_at = time.time()
            log.warning("CoinDCX circuit breaker OPENED after %d consecutive failures",
                        self._consecutive_failures)


def _parse_retry_after(resp: requests.Response) -> float | None:
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return min(float(raw), _RETRY_AFTER_CAP)
    except ValueError:
        return None


def _backoff_sleep(attempt: int, retry_after: float | None = None) -> None:
    if retry_after is not None:
        time.sleep(retry_after)
        return
    delay = min(_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 0.25), _BACKOFF_CAP)
    time.sleep(delay)


def _ccxt_symbol_to_market(symbol: str) -> str:
    """'BTC/INR' → 'BTCINR' — used by ticker + order endpoints."""
    return symbol.replace("/", "")


def _candle_prefix(quote: str) -> str:
    """
    CoinDCX's candles endpoint namespaces pairs by source: INR pairs use the
    ``I-`` prefix, while USDT/global pairs use ``B-`` (Binance-sourced). Map by
    quote currency so the same client works for both quotes.
    """
    return "I-" if quote.upper() == "INR" else "B-"


def _ccxt_symbol_to_pair(symbol: str) -> str:
    """'BTC/INR' → 'I-BTC_INR', 'BTC/USDT' → 'B-BTC_USDT' (candles endpoint)."""
    base, quote = symbol.split("/")
    return f"{_candle_prefix(quote)}{base}_{quote}"


class CoinDCXClient:
    def __init__(self, api_key: str = "", api_secret: str = ""):
        self._api_key    = api_key
        self._api_secret = api_secret
        self._has_keys   = bool(api_key and api_secret)
        self._markets:   Optional[dict] = None
        self._session    = requests.Session()
        self._breaker    = _CircuitBreaker()

    @property
    def has_keys(self) -> bool:
        return self._has_keys

    def clear_keys(self) -> None:
        """Wipe decrypted credentials from memory (called when a bot stops)."""
        self._api_key = ""
        self._api_secret = ""
        self._has_keys = False

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _request(self, method: str, url: str, *, headers: Optional[dict] = None,
                 params: Optional[dict] = None, data: Optional[str] = None,
                 retry_on_timeout: bool = True):
        """
        Single request path with retry + backoff (429/5xx/timeouts/connection
        errors) and a circuit breaker. ``retry_on_timeout`` must be False for
        non-idempotent POSTs (order create) where a retry could double-submit.
        """
        self._breaker.check()
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._session.request(
                    method, url, headers=headers, params=params, data=data,
                    timeout=_TIMEOUT,
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < _MAX_RETRIES:
                        _backoff_sleep(attempt, _parse_retry_after(resp))
                        continue
                    self._breaker.record_failure()
                    resp.raise_for_status()
                resp.raise_for_status()
                self._breaker.record_success()
                return resp.json()
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                transient = retry_on_timeout or isinstance(exc, requests.ConnectionError)
                if transient and attempt < _MAX_RETRIES:
                    _backoff_sleep(attempt)
                    continue
                self._breaker.record_failure()
                raise
            except requests.HTTPError:
                # 4xx (non-429): a client error, not a transient fault — don't
                # retry and don't trip the breaker.
                raise
        self._breaker.record_failure()
        raise last_exc if last_exc else CoinDCXError("request failed")

    def _public_get(self, url: str, params: Optional[dict] = None):
        return self._request("GET", url, params=params or {})

    def _signed_post(self, path: str, payload: Optional[dict] = None,
                     *, retry_on_timeout: bool = True):
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
        return self._request(
            "POST", f"{_API_BASE}{path}", headers=headers, data=body,
            retry_on_timeout=retry_on_timeout,
        )

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

    def get_quote_symbols(self) -> list[str]:
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

    def get_all_prices(self) -> dict[str, float]:
        """One ticker call → {ccxt_symbol: last_price} for every market.
        Used by the fast price-monitor loop (cheap: a single HTTP request)."""
        indexed = self._fetch_all_tickers_indexed()
        return {sym: t["last"] for sym, t in indexed.items() if t.get("last")}

    def get_top_momentum_symbols(self, n: int = settings.TOP_N_COINS) -> list[str]:
        """
        Build the scan universe:
        - always include the configured large caps (BTC/ETH) so the bot can act
          on them regardless of momentum rank;
        - of the remaining USDT pairs, keep those above the 24h quote-volume
          floor, not already pumped past MAX_24H_CHANGE_PCT (buying the top of a
          finished move was the July failure mode), and with an acceptable
          bid/ask spread; rank by momentum, take the top-N.
        Returns core symbols first, then ranked momentum picks (deduped).
        """
        symbols = self.get_quote_symbols()
        tickers = self.get_tickers(symbols)

        core = [s for s in settings.CORE_SYMBOLS if s in tickers]

        rows = []
        for sym, t in tickers.items():
            if sym in core:
                continue
            volume = t.get("quoteVolume") or 0.0
            if volume < settings.MIN_24H_QUOTE_VOLUME:
                continue
            change = t.get("percentage") or 0.0
            if (settings.MAX_24H_CHANGE_PCT is not None
                    and change > settings.MAX_24H_CHANGE_PCT):
                continue
            # Spread filter — only when the ticker carries both sides; a data
            # gap must not empty the universe.
            bid, ask = t.get("bid"), t.get("ask")
            if settings.MAX_SPREAD_PCT is not None and bid and ask:
                mid = (bid + ask) / 2
                if mid > 0 and (ask - bid) / mid > settings.MAX_SPREAD_PCT:
                    log.debug("Universe: %s excluded on spread %.2f%%",
                              sym, (ask - bid) / mid * 100)
                    continue
            rows.append({"symbol": sym, "change": change, "volume": volume})

        ranked: list[str] = []
        if rows:
            w = settings.MOMENTUM_CHANGE_WEIGHT
            df = pd.DataFrame(rows)
            df["change_rank"] = df["change"].rank(ascending=True)
            df["volume_rank"] = df["volume"].rank(ascending=True)
            df["score"] = w * df["change_rank"] + (1 - w) * df["volume_rank"]
            df = df[df["change"] > 0].sort_values("score", ascending=False)
            ranked = df["symbol"].head(n).tolist()

        # core first, then momentum picks, deduped, preserving order
        seen: set[str] = set()
        out: list[str] = []
        for sym in core + ranked:
            if sym not in seen:
                seen.add(sym)
                out.append(sym)
        log.info("Universe: %d symbols (%d momentum picks of top-%d requested)",
                 len(out), len(ranked), n)
        return out

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

    @staticmethod
    def _extract_order(raw: dict | list) -> dict:
        """
        CoinDCX's order-create response is ``{"orders": [ {...} ]}``; status
        lookups return ``{...}`` directly. Normalise to a single order dict.
        """
        if isinstance(raw, dict) and "orders" in raw and raw["orders"]:
            return raw["orders"][0]
        if isinstance(raw, list) and raw:
            return raw[0]
        if isinstance(raw, dict):
            return raw
        return {}

    @staticmethod
    def _normalize_fill(order: dict, fallback_price: float | None = None) -> dict:
        """
        Pull the *actual* fill out of a CoinDCX order dict. Market orders report
        ``avg_price`` + ``total_quantity``/``filled_quantity``. When the average
        price isn't (yet) present we fall back to the requested price and flag the
        fill unconfirmed so the caller can reconcile later.
        """
        def _f(*keys):
            for k in keys:
                v = order.get(k)
                if v not in (None, "", 0, "0"):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        continue
            return None

        fill_price = _f("avg_price", "price_per_unit", "price")
        fill_qty   = _f("filled_quantity", "total_quantity", "quantity")
        confirmed  = fill_price is not None
        if fill_price is None:
            fill_price = fallback_price
        return {
            "exchange_order_id": order.get("id") or order.get("order_id"),
            "status":            order.get("status", "unknown"),
            "fill_price":        fill_price,
            "fill_qty":          fill_qty,
            "confirmed":         confirmed,
            "raw":               order,
        }

    def fetch_order_status(self, exchange_order_id: str) -> dict:
        """Idempotent lookup used to reconcile a fill after an ambiguous create."""
        raw = self._signed_post(
            "/exchange/v1/orders/status", {"id": exchange_order_id},
            retry_on_timeout=True,
        )
        return self._normalize_fill(self._extract_order(raw))

    def place_market_buy(self, symbol: str, amount_quote: float,
                         client_order_id: Optional[str] = None) -> dict:
        """
        Submit a market buy for ``amount_quote`` worth of ``symbol`` and return a
        normalised fill dict (see ``_normalize_fill``). The create POST is NOT
        retried on timeout — an ambiguous timeout is reconciled by the caller via
        ``fetch_order_status`` to avoid double-submitting.
        """
        if not self._has_keys:
            raise RuntimeError("Cannot place orders without API keys")
        ticker = self.fetch_ticker(symbol)
        price  = ticker["last"]
        qty    = amount_quote / price
        payload = {
            "side":           "buy",
            "order_type":     "market_order",
            "market":         _ccxt_symbol_to_market(symbol),
            "total_quantity": qty,
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id
        raw = self._signed_post("/exchange/v1/orders/create", payload,
                                retry_on_timeout=False)
        return self._normalize_fill(self._extract_order(raw), fallback_price=price)

    def place_market_sell(self, symbol: str, qty: float,
                          client_order_id: Optional[str] = None) -> dict:
        if not self._has_keys:
            raise RuntimeError("Cannot place orders without API keys")
        payload = {
            "side":           "sell",
            "order_type":     "market_order",
            "market":         _ccxt_symbol_to_market(symbol),
            "total_quantity": qty,
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id
        raw = self._signed_post("/exchange/v1/orders/create", payload,
                                retry_on_timeout=False)
        return self._normalize_fill(self._extract_order(raw))

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
