"""
Order manager.
Routes buy/sell requests to either the paper trader or the live CoinDCX
client depending on MODE in settings.
"""

import sys, os
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings
from src.exchange.paper_trader import PaperTrader


class OrderManager:
    def __init__(self, paper_trader: PaperTrader, live_client=None):
        self._paper  = paper_trader
        self._live   = live_client    # CoinDCXClient instance, or None in paper mode

    def buy(self, symbol: str, amount_inr: float,
            current_price: float) -> Optional[dict]:
        """
        Place a buy order.
        Returns a dict with order details, or None on failure.
        """
        if settings.LIVE and self._live is not None:
            try:
                order = self._live.place_market_buy(symbol, amount_inr)
                return {
                    "order_id":  order.get("id"),
                    "symbol":    symbol,
                    "side":      "buy",
                    "price":     current_price,
                    "amount_inr": amount_inr,
                    "mode":      "live",
                }
            except Exception as exc:
                return None
        else:
            pos = self._paper.place_market_buy(symbol, amount_inr, current_price)
            if pos is None:
                return None
            return {
                "order_id":  pos.order_id,
                "symbol":    symbol,
                "side":      "buy",
                "price":     current_price,
                "amount_inr": pos.amount_inr,
                "mode":      "paper",
            }

    def sell(self, symbol: str, current_price: float,
             reason: str = "signal") -> Optional[dict]:
        """
        Close an open position.
        Returns a trade-record dict, or None on failure.
        """
        if settings.LIVE and self._live is not None:
            pos = self._paper.positions.get(symbol)
            if pos is None:
                return None
            try:
                order = self._live.place_market_sell(symbol, pos.qty)
                trade = self._paper.place_market_sell(symbol, current_price, reason)
                return trade
            except Exception:
                return None
        else:
            return self._paper.place_market_sell(symbol, current_price, reason)
