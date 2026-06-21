"""
Shared market-data scanner.

One thread fetches top-momentum INR pairs and their OHLCV every
``SCAN_INTERVAL_S``, then caches the results in memory keyed by symbol.
Every UserBot reads from this cache instead of issuing its own
duplicate requests.

The cache uses a no-keys CoinDCXClient since CoinDCX exposes its
public market endpoints unauthenticated.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.exchange.coindcx_client import CoinDCXClient
from src.data.market_data import MarketData
from src.monitoring.logger import get_logger


log = get_logger()


@dataclass
class ScanCache:
    symbols:        list[str]              = field(default_factory=list)
    current_prices: dict[str, float]       = field(default_factory=dict)
    all_prices:     dict[str, float]       = field(default_factory=dict)
    market_data:    Optional[MarketData]   = None
    last_scan_time: float                  = 0.0
    last_price_time: float                 = 0.0
    lock:           threading.Lock         = field(default_factory=threading.Lock)


class MarketDataScanner:
    """
    Owns a public-only CoinDCXClient and a MarketData OHLCV cache.

    Two cadences:
    - **Universe scan** every ``SCAN_INTERVAL_S`` (5 min): re-rank the top-momentum
      symbols + refresh their OHLCV; fires ``scan_complete_event``.
    - **Price monitor** every ``FAST_POLL_S`` (~15 s): one ticker call refreshes
      live prices for *all* symbols; fires ``price_event`` so each UserBot can run
      stop-loss/take-profit checks without waiting for the 5-minute scan.
    """

    def __init__(self):
        self._client = CoinDCXClient()  # no keys → public endpoints only
        self.cache = ScanCache(market_data=MarketData(self._client))
        self.scan_complete_event = threading.Event()
        self.price_event = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._price_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="market-scanner")
        self._thread.start()
        self._price_thread = threading.Thread(target=self._price_loop, daemon=True,
                                              name="price-monitor")
        self._price_thread.start()
        log.info("MarketDataScanner started (scan + price monitor)")

    def stop(self) -> None:
        self._stop.set()
        for t in (self._thread, self._price_thread):
            if t:
                t.join(timeout=5)

    def get_all_prices_snapshot(self) -> dict[str, float]:
        with self.cache.lock:
            return dict(self.cache.all_prices)

    # ── Universe scan (slow) ────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._scan_once()
            except Exception as exc:
                log.exception(f"Scanner cycle failed: {exc}")

            # sleep in 1-second slices so stop() responds quickly
            for _ in range(settings.SCAN_INTERVAL_S):
                if self._stop.is_set():
                    return
                time.sleep(1)

    def _scan_once(self) -> None:
        log.info("Scanner: fetching top momentum symbols + tickers …")
        symbols = self._client.get_top_momentum_symbols()
        if not symbols:
            log.warning("Scanner: no symbols returned")
            return

        # One ticker call for everything, then pick out the universe prices.
        try:
            all_prices = self._client.get_all_prices()
        except Exception:
            all_prices = {}
        prices = {sym: all_prices[sym] for sym in symbols if sym in all_prices}

        with self.cache.lock:
            self.cache.symbols = symbols
            self.cache.current_prices = prices
            if all_prices:
                self.cache.all_prices = all_prices
            self.cache.last_scan_time = time.time()

        self.scan_complete_event.set()
        # Reset the event so subsequent waits can fire on the next scan
        self.scan_complete_event.clear()
        log.info(f"Scanner: cached {len(symbols)} symbols, prices for {len(prices)}")

    # ── Price monitor (fast) ────────────────────────────────────────────────────

    def _price_loop(self) -> None:
        while not self._stop.is_set():
            try:
                all_prices = self._client.get_all_prices()
                if all_prices:
                    with self.cache.lock:
                        self.cache.all_prices = all_prices
                        self.cache.last_price_time = time.time()
                    self.price_event.set()
                    self.price_event.clear()
            except Exception as exc:
                log.warning("Price monitor cycle failed: %s", exc)

            for _ in range(settings.FAST_POLL_S):
                if self._stop.is_set():
                    return
                time.sleep(1)
