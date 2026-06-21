"""
Tests for CoinDCXClient HTTP resilience: retry/backoff, no-retry on
non-idempotent order POSTs, and the circuit breaker. No real network.
"""

import sys, os
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.exchange.coindcx_client as cc
from src.exchange.coindcx_client import CoinDCXClient, CircuitOpenError


class FakeResp:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload if payload is not None else {"ok": True}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err


class FakeSession:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def request(self, *args, **kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(cc.time, "sleep", lambda *_: None)


def test_retries_5xx_then_succeeds():
    c = CoinDCXClient()
    c._session = FakeSession([FakeResp(503), FakeResp(200, {"ok": 1})])
    assert c._public_get("http://x") == {"ok": 1}
    assert c._session.calls == 2


def test_retries_429_with_retry_after():
    c = CoinDCXClient()
    c._session = FakeSession([
        FakeResp(429, headers={"Retry-After": "1"}),
        FakeResp(200, {"ok": 2}),
    ])
    assert c._public_get("http://x") == {"ok": 2}
    assert c._session.calls == 2


def test_4xx_not_retried_and_does_not_trip_breaker():
    c = CoinDCXClient()
    c._session = FakeSession([FakeResp(400)])
    with pytest.raises(requests.HTTPError):
        c._public_get("http://x")
    assert c._session.calls == 1


def test_order_create_timeout_not_retried():
    c = CoinDCXClient(api_key="k", api_secret="s")
    c._session = FakeSession([requests.Timeout()])
    with pytest.raises(requests.Timeout):
        c._signed_post("/orders/create", {"a": 1}, retry_on_timeout=False)
    assert c._session.calls == 1     # exactly one attempt — no double-submit


def test_idempotent_get_retries_timeout():
    c = CoinDCXClient()
    c._session = FakeSession([requests.Timeout(), requests.Timeout(), FakeResp(200, {"ok": 3})])
    assert c._public_get("http://x") == {"ok": 3}
    assert c._session.calls == 3


def test_circuit_breaker_opens_after_consecutive_failures():
    c = CoinDCXClient()
    # Each call exhausts retries (4 attempts) on ConnectionError → 1 failure.
    # 5 failures reaches the threshold and opens the breaker.
    c._session = FakeSession([requests.ConnectionError() for _ in range(100)])
    for _ in range(5):
        with pytest.raises(requests.ConnectionError):
            c._public_get("http://x")
    calls_before = c._session.calls
    with pytest.raises(CircuitOpenError):
        c._public_get("http://x")          # short-circuits without touching the session
    assert c._session.calls == calls_before


def test_candle_pair_prefix_by_quote():
    assert cc._ccxt_symbol_to_pair("BTC/INR") == "I-BTC_INR"
    assert cc._ccxt_symbol_to_pair("BTC/USDT") == "B-BTC_USDT"
