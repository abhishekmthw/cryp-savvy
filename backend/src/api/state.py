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

    # Bounded so a disconnected client can't make the queue grow without limit.
    event_queue: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=500))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def update_scan(self, signals: list, prices: dict):
        with self.lock:
            self.last_signals = signals
            self.current_prices = prices
            self.last_scan_time = time.time()

    def push_event(self, event_type: str, data: dict):
        # Atomic check-and-put: drop the OLDEST event if the queue is full so the
        # most recent state always gets through (and a torn qsize() check can't
        # let it grow past the cap).
        event = {"type": event_type, "data": data}
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            try:
                self.event_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.event_queue.put_nowait(event)
            except queue.Full:
                pass

    def drain_queue(self) -> None:
        """Discard any buffered events — called when a socket disconnects so a
        reconnecting client doesn't receive a backlog of stale events."""
        while True:
            try:
                self.event_queue.get_nowait()
            except queue.Empty:
                return


# Backwards-compat alias — some imports still say ``BotState``
BotState = UserBotState
