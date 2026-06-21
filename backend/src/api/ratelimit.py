"""
Lightweight in-process sliding-window rate limiter.

Used to throttle sensitive endpoints (credential save/test, bot control, WS
ticket minting) per client IP without pulling in an extra dependency. Single
Fly.io instance only, so in-memory state is sufficient.
"""

from __future__ import annotations

import threading
import time


class SlidingWindowLimiter:
    def __init__(self, max_requests: int = 5, window_s: float = 60.0):
        self.max_requests = max_requests
        self.window_s = window_s
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if now - t < self.window_s]
            if len(recent) >= self.max_requests:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            # opportunistic GC of cold keys
            if len(self._hits) > 10_000:
                self._hits = {
                    k: v for k, v in self._hits.items()
                    if v and now - v[-1] < self.window_s
                }
            return True
