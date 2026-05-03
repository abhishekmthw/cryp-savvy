"""
Per-user shared state between a ``UserBot`` worker thread and the FastAPI
handlers/WebSocket. Replaces the previous global ``BotState`` singleton.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserBotState:
    user_id: str
    paper_trader: Any = None
    portfolio: Any = None

    mode: str = "paper"
    is_running: bool = False

    last_signals: list = field(default_factory=list)
    last_scan_time: float = 0.0
    current_prices: dict = field(default_factory=dict)

    event_queue: queue.Queue = field(default_factory=queue.Queue)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def update_scan(self, signals: list, prices: dict):
        with self.lock:
            self.last_signals = signals
            self.current_prices = prices
            self.last_scan_time = time.time()

    def push_event(self, event_type: str, data: dict):
        if self.event_queue.qsize() < 500:
            self.event_queue.put_nowait({"type": event_type, "data": data})


# Backwards-compat alias — some imports still say ``BotState``
BotState = UserBotState
