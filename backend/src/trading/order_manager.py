"""
Order manager.
Routes buy/sell requests to either the paper trader or the user's live
CoinDCX client depending on the per-user mode.
"""

from __future__ import annotations

import sys
import os
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.exchange.paper_trader import PaperTrader


class OrderManager:
    def __init__(self, paper_trader: PaperTrader, mode: str, live_client=None):
        self._paper = paper_trader
        self._mode  = mode               # 'paper' | 'live'
        self._live  = live_client        # CoinDCXClient with keys, or None

    @property
    def is_live(self) -> bool:
        return self._mode == "live" and self._live is not None and self._live.has_keys

    def buy(self, symbol: str, amount_inr: float,
            current_price: float) -> Optional[dict]:
        if self.is_live:
            try:
                order = self._live.place_market_buy(symbol, amount_inr)
                return {
                    "order_id":   order.get("id"),
                    "symbol":     symbol,
                    "side":       "buy",
                    "price":      current_price,
                    "amount_inr": amount_inr,
                    "mode":       "live",
                }
            except Exception:
                return None
        else:
            pos = self._paper.place_market_buy(symbol, amount_inr, current_price)
            if pos is None:
                return None
            return {
                "order_id":   pos.order_id,
                "symbol":     symbol,
                "side":       "buy",
                "price":      current_price,
                "amount_inr": pos.amount_inr,
                "mode":       "paper",
            }

    def sell(self, symbol: str, current_price: float,
             reason: str = "signal") -> Optional[dict]:
        if self.is_live:
            pos = self._paper.positions.get(symbol)
            if pos is None:
                return None
            try:
                self._live.place_market_sell(symbol, pos.qty)
                trade = self._paper.place_market_sell(symbol, current_price, reason)
                return trade
            except Exception:
                return None
        else:
            return self._paper.place_market_sell(symbol, current_price, reason)
