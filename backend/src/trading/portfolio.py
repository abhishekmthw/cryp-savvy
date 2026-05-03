"""
Portfolio state tracker.
Persists trade history to SQLite and exposes summary statistics.
"""

import sqlite3
import time
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


class Portfolio:
    def __init__(self):
        db_path = os.path.abspath(settings.DB_PATH)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id    TEXT,
                symbol      TEXT,
                side        TEXT,
                entry_price REAL,
                exit_price  REAL,
                qty         REAL,
                amount_inr  REAL,
                proceeds    REAL,
                pnl         REAL,
                pnl_pct     REAL,
                reason      TEXT,
                duration_s  REAL,
                ts          REAL
            )
        """)
        self._conn.commit()

    def record_trade(self, trade: dict):
        """Persist a closed trade record returned by PaperTrader.place_market_sell."""
        self._conn.execute("""
            INSERT INTO trades
              (order_id, symbol, side, entry_price, exit_price, qty,
               amount_inr, proceeds, pnl, pnl_pct, reason, duration_s, ts)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            trade.get("order_id"),
            trade.get("symbol"),
            "sell",
            trade.get("entry_price"),
            trade.get("exit_price"),
            trade.get("qty"),
            trade.get("amount_inr"),
            trade.get("proceeds"),
            trade.get("pnl"),
            trade.get("pnl_pct"),
            trade.get("reason"),
            trade.get("duration_s"),
            time.time(),
        ))
        self._conn.commit()

    def stats(self) -> dict:
        """Return aggregate performance statistics from the database."""
        cur = self._conn.execute("""
            SELECT
                COUNT(*)                    AS total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losses,
                SUM(pnl)                    AS total_pnl,
                AVG(pnl_pct)                AS avg_pnl_pct,
                MAX(pnl_pct)                AS best_trade_pct,
                MIN(pnl_pct)                AS worst_trade_pct
            FROM trades
        """)
        row = cur.fetchone()
        if not row or row[0] == 0:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "total_pnl": 0.0,
                "avg_pnl_pct": 0.0, "best_trade_pct": 0.0,
                "worst_trade_pct": 0.0,
            }
        total, wins, losses, total_pnl, avg_pnl_pct, best, worst = row
        return {
            "total_trades":    total,
            "wins":            wins or 0,
            "losses":          losses or 0,
            "win_rate":        round((wins or 0) / total * 100, 1),
            "total_pnl":       round(total_pnl or 0, 2),
            "avg_pnl_pct":     round(avg_pnl_pct or 0, 2),
            "best_trade_pct":  round(best or 0, 2),
            "worst_trade_pct": round(worst or 0, 2),
        }

    def recent_trades(self, n: int = 10) -> list[dict]:
        cur = self._conn.execute("""
            SELECT symbol, side, entry_price, exit_price, pnl, pnl_pct, reason, ts
            FROM trades
            ORDER BY ts DESC
            LIMIT ?
        """, (n,))
        cols = ["symbol", "side", "entry_price", "exit_price",
                "pnl", "pnl_pct", "reason", "ts"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def pnl_history(self) -> list[dict]:
        """
        Returns one data-point per trade showing cumulative portfolio value.
        Used by the frontend P&L chart.
        """
        cur = self._conn.execute(
            "SELECT ts, pnl FROM trades ORDER BY ts ASC"
        )
        rows = cur.fetchall()
        running = settings.INITIAL_CAPITAL_INR
        # Start point (before any trades)
        history = [{"ts": rows[0][0] if rows else time.time(),
                    "value": round(running, 2)}]
        for ts, pnl in rows:
            running += (pnl or 0)
            history.append({"ts": ts, "value": round(running, 2)})
        return history

    def close(self):
        self._conn.close()
