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
    market_data:    Optional[MarketData]   = None
    last_scan_time: float                  = 0.0
    lock:           threading.Lock         = field(default_factory=threading.Lock)


class MarketDataScanner:
    """
    Owns a public-only CoinDCXClient and a MarketData OHLCV cache.
    Every ``SCAN_INTERVAL_S``, refreshes the top-momentum symbol list
    and current prices, then notifies subscribers via ``scan_complete_event``.
    """

    def __init__(self):
        self._client = CoinDCXClient()  # no keys → public endpoints only
        self.cache = ScanCache(market_data=MarketData(self._client))
        self.scan_complete_event = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="market-scanner")
        self._thread.start()
        log.info("MarketDataScanner started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

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

        prices: dict[str, float] = {}
        for sym in symbols:
            try:
                t = self._client.fetch_ticker(sym)
                prices[sym] = float(t["last"])
            except Exception:
                pass

        with self.cache.lock:
            self.cache.symbols = symbols
            self.cache.current_prices = prices
            self.cache.last_scan_time = time.time()

        self.scan_complete_event.set()
        # Reset the event so subsequent waits can fire on the next scan
        self.scan_complete_event.clear()
        log.info(f"Scanner: cached {len(symbols)} symbols, prices for {len(prices)}")
