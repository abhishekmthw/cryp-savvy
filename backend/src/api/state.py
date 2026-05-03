"""
Thread-safe shared state between the trading bot loop and the FastAPI server.
Both run in separate threads in the same process and communicate via this object.
"""

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BotState:
    # Shared objects (set by TradingBot.__init__)
    paper_trader: Any = None
    portfolio: Any = None

    # Updated after every scan cycle (guarded by lock)
    last_signals: list = field(default_factory=list)
    last_scan_time: float = 0.0
    current_prices: dict = field(default_factory=dict)
    is_running: bool = False

    # Events queued by the bot → drained by the WebSocket broadcaster
    event_queue: queue.Queue = field(default_factory=queue.Queue)

    # Lock protects paper_trader and the mutable fields above
    lock: threading.Lock = field(default_factory=threading.Lock)

    # ── Helpers called from the bot thread ───────────────────────────────────

    def update_scan(self, signals: list, prices: dict):
        with self.lock:
            self.last_signals = signals
            self.current_prices = prices
            self.last_scan_time = time.time()

    def push_event(self, event_type: str, data: dict):
        """Non-blocking: drops the event if the queue is full (>500 items)."""
        if self.event_queue.qsize() < 500:
            self.event_queue.put_nowait({"type": event_type, "data": data})
