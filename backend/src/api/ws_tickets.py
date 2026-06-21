"""
Short-lived, single-use WebSocket handshake tickets.

The Clerk JWT must NOT be passed in the WebSocket URL query string (it leaks to
logs, referers and proxies). Instead the client authenticates a normal REST call
to mint a ticket, then opens ``wss://…/ws?ticket=<ticket>``. Tickets are
single-use and expire after ``ttl`` seconds.
"""

from __future__ import annotations

import secrets
import threading
import time

_TICKET_TTL = 60.0  # seconds


class WsTicketStore:
    def __init__(self, ttl: float = _TICKET_TTL):
        self._ttl = ttl
        self._tickets: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def issue(self, user_id: str) -> str:
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            self._tickets[ticket] = (user_id, time.time() + self._ttl)
            self._gc_locked()
        return ticket

    def consume(self, ticket: str) -> str | None:
        if not ticket:
            return None
        with self._lock:
            entry = self._tickets.pop(ticket, None)   # single-use: removed on read
        if not entry:
            return None
        user_id, expires = entry
        if time.time() > expires:
            return None
        return user_id

    def _gc_locked(self) -> None:
        now = time.time()
        for t in [t for t, (_, exp) in self._tickets.items() if now > exp]:
            self._tickets.pop(t, None)
