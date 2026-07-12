"""
Order manager.

Routes buy/sell requests to either the paper trader or the user's live CoinDCX
client, and is the single place that keeps the simulated book in sync with the
exchange.

Correctness contract (live mode):
- Every order is written to the ``orders`` table as ``pending`` BEFORE the
  exchange call, keyed by a client-generated UUID (idempotency key).
- After a successful create the *actual* exchange fill (price/qty) is
  reconciled and the paper book is updated from that fill — never from the
  pre-trade estimate. This fixes the prior bug where live buys never recorded a
  position and could not be exited.
- An ambiguous network timeout on the create POST is NOT retried (that could
  double-submit). The order is marked ``unconfirmed`` and NO position is booked;
  it is left for reconciliation rather than guessed at.
"""

from __future__ import annotations

import sys
import os
import uuid
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.exchange.paper_trader import PaperTrader
from src.monitoring.logger import get_logger

try:                                            # optional — paper-only tests omit it
    import requests
    _TIMEOUT_EXC: tuple = (requests.Timeout,)
except Exception:                               # pragma: no cover
    _TIMEOUT_EXC = ()

log = get_logger()


class OrderManager:
    def __init__(self, paper_trader: PaperTrader, mode: str, live_client=None,
                 user_id: str = "", order_store=None, quote_currency: str = "INR"):
        self._paper = paper_trader
        self._mode  = mode               # 'paper' | 'live'
        self._live  = live_client        # CoinDCXClient with keys, or None
        self._user_id = user_id
        self._store = order_store         # object with create_order/update_order, or None
        self._quote = quote_currency

    @property
    def is_live(self) -> bool:
        return self._mode == "live" and self._live is not None and self._live.has_keys

    # ── internal: best-effort order log ───────────────────────────────────────

    def _log_create(self, coid: str, symbol: str, side: str, **kw) -> None:
        if self._store is None:
            return
        try:
            self._store.create_order(
                client_order_id=coid, symbol=symbol, side=side, mode=self._mode,
                quote_currency=self._quote, **kw,
            )
        except Exception:
            log.exception("Failed to persist pending order %s", coid)

    def _log_update(self, coid: str, **fields) -> None:
        if self._store is None:
            return
        try:
            self._store.update_order(coid, **fields)
        except Exception:
            log.exception("Failed to update order %s", coid)

    # ── Buy ───────────────────────────────────────────────────────────────────

    def buy(self, symbol: str, amount_usdt: float, current_price: float,
            atr: Optional[float] = None, bucket: str = "day",
            strategy: str = "none", regime: Optional[str] = None,
            score: Optional[float] = None,
            scores: Optional[dict] = None) -> Optional[dict]:
        coid = uuid.uuid4().hex
        self._log_create(coid, symbol, "buy", requested_amount=amount_usdt,
                         requested_price=current_price, bucket=bucket)

        if self.is_live:
            return self._buy_live(coid, symbol, amount_usdt, current_price, atr,
                                  bucket, strategy, regime, score, scores)
        return self._buy_paper(coid, symbol, amount_usdt, current_price, atr,
                               bucket, strategy, regime, score, scores)

    def _buy_paper(self, coid, symbol, amount_usdt, current_price,
                   atr=None, bucket="day", strategy="none", regime=None,
                   score=None, scores=None) -> Optional[dict]:
        pos = self._paper.place_market_buy(symbol, amount_usdt, current_price,
                                           atr=atr, bucket=bucket, strategy=strategy,
                                           regime=regime, entry_score=score,
                                           scores=scores)
        if pos is None:
            self._log_update(coid, status="failed", error="paper rejected")
            return None
        self._log_update(coid, status="filled", fill_price=pos.entry_price,
                         fill_qty=pos.qty)
        return {
            "order_id": coid, "symbol": symbol, "side": "buy",
            "price": pos.entry_price, "amount_usdt": pos.amount_usdt, "mode": "paper",
        }

    def _buy_live(self, coid, symbol, amount_usdt, current_price,
                  atr=None, bucket="day", strategy="none", regime=None,
                  score=None, scores=None) -> Optional[dict]:
        try:
            fill = self._live.place_market_buy(symbol, amount_usdt, client_order_id=coid)
        except _TIMEOUT_EXC:
            # Ambiguous: the order may or may not have reached the exchange.
            # Do NOT book a position or retry — flag for reconciliation.
            self._log_update(coid, status="unconfirmed",
                             error="create timed out — needs reconciliation")
            log.critical("LIVE BUY %s timed out (order %s) — manual reconciliation "
                         "may be required", symbol, coid)
            return None
        except Exception as exc:
            self._log_update(coid, status="failed", error=str(exc)[:300])
            log.exception("Live buy failed for %s", symbol)
            return None

        fill = self._reconcile(fill)
        fill_price = fill.get("fill_price") or current_price
        fill_qty   = fill.get("fill_qty")
        pos = self._paper.place_market_buy(
            symbol, amount_usdt, current_price,
            fill_price=fill_price, fill_qty=fill_qty, atr=atr, bucket=bucket,
            strategy=strategy, regime=regime, entry_score=score, scores=scores,
        )
        status = "filled" if fill.get("confirmed") else "unconfirmed"
        self._log_update(coid, status=status, fill_price=fill_price, fill_qty=fill_qty,
                         exchange_order_id=fill.get("exchange_order_id"))
        if pos is None:
            return None
        return {
            "order_id": coid, "symbol": symbol, "side": "buy",
            "price": pos.entry_price, "amount_usdt": pos.amount_usdt, "mode": "live",
            "exchange_order_id": fill.get("exchange_order_id"),
        }

    # ── Sell ──────────────────────────────────────────────────────────────────

    def sell(self, symbol: str, current_price: float,
             reason: str = "signal") -> Optional[dict]:
        coid = uuid.uuid4().hex
        pos = self._paper.positions.get(symbol)
        self._log_create(coid, symbol, "sell",
                         requested_qty=(pos.qty if pos else None),
                         requested_price=current_price, reason=reason)

        if self.is_live:
            return self._sell_live(coid, symbol, current_price, reason)
        return self._sell_paper(coid, symbol, current_price, reason)

    def _sell_paper(self, coid, symbol, current_price, reason) -> Optional[dict]:
        trade = self._paper.place_market_sell(symbol, current_price, reason)
        if trade is None:
            self._log_update(coid, status="failed", error="no position")
            return None
        self._log_update(coid, status="filled", fill_price=current_price,
                         fill_qty=trade["qty"])
        return trade

    def _sell_live(self, coid, symbol, current_price, reason) -> Optional[dict]:
        pos = self._paper.positions.get(symbol)
        if pos is None:
            self._log_update(coid, status="failed", error="no position")
            return None
        try:
            fill = self._live.place_market_sell(symbol, pos.qty, client_order_id=coid)
        except _TIMEOUT_EXC:
            self._log_update(coid, status="unconfirmed",
                             error="sell create timed out — needs reconciliation")
            log.critical("LIVE SELL %s timed out (order %s) — manual reconciliation "
                         "may be required", symbol, coid)
            return None
        except Exception as exc:
            self._log_update(coid, status="failed", error=str(exc)[:300])
            log.exception("Live sell failed for %s", symbol)
            return None

        fill = self._reconcile(fill)
        exit_price = fill.get("fill_price") or current_price
        fill_qty   = fill.get("fill_qty")
        trade = self._paper.place_market_sell(symbol, exit_price, reason, fill_qty=fill_qty)
        status = "filled" if fill.get("confirmed") else "unconfirmed"
        self._log_update(coid, status=status, fill_price=exit_price, fill_qty=fill_qty,
                         exchange_order_id=fill.get("exchange_order_id"))
        return trade

    # ── reconciliation ────────────────────────────────────────────────────────

    def _reconcile(self, fill: dict) -> dict:
        """If the create response didn't include an average fill price, query the
        order status once to fill it in."""
        if fill.get("confirmed") or not fill.get("exchange_order_id"):
            return fill
        try:
            status = self._live.fetch_order_status(fill["exchange_order_id"])
            if status.get("confirmed"):
                return status
        except Exception:
            log.warning("Could not reconcile fill for order %s",
                        fill.get("exchange_order_id"))
        return fill
