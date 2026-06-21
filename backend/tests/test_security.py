"""
Unit tests for the Phase-1 security primitives: WS handshake tickets, the
sliding-window rate limiter, Clerk subject validation, and DB-TLS enforcement.
"""

import sys, os
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.api.ws_tickets import WsTicketStore
from src.api.ratelimit import SlidingWindowLimiter
from src.api.auth import is_valid_clerk_sub


# ── WS tickets ────────────────────────────────────────────────────────────────

def test_ticket_round_trip():
    store = WsTicketStore()
    t = store.issue("user_abc")
    assert store.consume(t) == "user_abc"


def test_ticket_is_single_use():
    store = WsTicketStore()
    t = store.issue("user_abc")
    assert store.consume(t) == "user_abc"
    assert store.consume(t) is None        # consumed — cannot be replayed


def test_ticket_expires():
    store = WsTicketStore(ttl=-1)           # already expired
    t = store.issue("user_abc")
    assert store.consume(t) is None


def test_unknown_or_empty_ticket_rejected():
    store = WsTicketStore()
    assert store.consume("nope") is None
    assert store.consume("") is None


# ── Rate limiter ──────────────────────────────────────────────────────────────

def test_limiter_allows_up_to_max():
    lim = SlidingWindowLimiter(max_requests=3, window_s=60)
    assert [lim.allow("k") for _ in range(3)] == [True, True, True]
    assert lim.allow("k") is False          # 4th in window blocked


def test_limiter_is_per_key():
    lim = SlidingWindowLimiter(max_requests=1, window_s=60)
    assert lim.allow("a") is True
    assert lim.allow("b") is True           # different key, own bucket
    assert lim.allow("a") is False


def test_limiter_window_rolls_off():
    lim = SlidingWindowLimiter(max_requests=1, window_s=0.05)
    assert lim.allow("k") is True
    assert lim.allow("k") is False
    time.sleep(0.06)
    assert lim.allow("k") is True           # window expired


# ── Clerk subject validation ──────────────────────────────────────────────────

@pytest.mark.parametrize("sub,ok", [
    ("user_2abcDEF123", True),
    ("user_x", True),
    ("admin_123", False),
    ("'; DROP TABLE users;--", False),
    ("", False),
    (None, False),
])
def test_clerk_sub_validation(sub, ok):
    assert is_valid_clerk_sub(sub) is ok


# ── DB TLS enforcement ────────────────────────────────────────────────────────

def test_db_tls_appended_for_remote():
    from config.settings import _enforce_db_tls
    url = "postgresql+psycopg://u:p@db.example.com:5432/app"
    assert _enforce_db_tls(url).endswith("?sslmode=require")


def test_db_tls_skipped_for_localhost():
    from config.settings import _enforce_db_tls
    url = "postgresql+psycopg://u:p@localhost:5432/app"
    assert "sslmode" not in _enforce_db_tls(url)


def test_db_tls_not_duplicated():
    from config.settings import _enforce_db_tls
    url = "postgresql+psycopg://u:p@host/app?sslmode=verify-full"
    assert _enforce_db_tls(url).count("sslmode") == 1


# ── Live-trading gate ─────────────────────────────────────────────────────────

def test_live_trading_disabled_by_default():
    from config import settings
    # Safe default: live trading is OFF until an operator explicitly enables it
    # post-validation (control.set_mode enforces this).
    assert settings.LIVE_TRADING_ENABLED is False
