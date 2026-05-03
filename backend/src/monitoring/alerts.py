"""
Per-user Telegram alerter.

The previous module-level functions read tokens from settings — that worked
for single-tenant. Now each user provides their own bot+chat, so alerting
is a per-user object. ``alert_*`` methods become methods on a class.

If the user has no Telegram credentials saved (or if a send fails), all
methods are silent no-ops — alerting must never crash the bot.
"""

from __future__ import annotations

import asyncio


class TelegramAlerter:
    def __init__(self, bot_token: str = "", chat_id: str = "", *, capital_inr: float = 0.0,
                 daily_loss_limit_inr: float = 0.0):
        self._token = bot_token
        self._chat  = chat_id
        self._capital = capital_inr
        self._daily_loss_limit = daily_loss_limit_inr

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _send(self, text: str):
        if not self.enabled:
            return
        try:
            from telegram import Bot

            async def _do():
                bot = Bot(token=self._token)
                await bot.send_message(chat_id=self._chat, text=text, parse_mode="Markdown")

            asyncio.run(_do())
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────────────────

    def alert_buy(self, symbol: str, price: float, amount_inr: float,
                  score: float, mode: str = "paper"):
        tag = "[PAPER]" if mode == "paper" else "[LIVE]"
        self._send(
            f"*{tag} BUY* `{symbol}`\n"
            f"Price: ₹{price:,.4f}\n"
            f"Amount: ₹{amount_inr:,.2f}\n"
            f"Signal Score: {score:.1f}/100"
        )

    def alert_sell(self, symbol: str, price: float, pnl: float,
                   pnl_pct: float, reason: str, mode: str = "paper"):
        tag   = "[PAPER]" if mode == "paper" else "[LIVE]"
        emoji = "✅" if pnl >= 0 else "❌"
        self._send(
            f"*{tag} SELL* `{symbol}` {emoji}\n"
            f"Exit Price: ₹{price:,.4f}\n"
            f"P&L: ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
            f"Reason: `{reason}`"
        )

    def alert_daily_limit(self):
        self._send(
            "⚠️ *Daily loss limit reached.*\n"
            f"Bot has paused trading for today (limit: ₹{self._daily_loss_limit:,.0f})."
        )

    def alert_error(self, message: str):
        self._send(f"🔴 *Bot Error*\n`{message}`")

    def alert_startup(self, mode: str):
        self._send(
            "🚀 *CrypSavvy Started*\n"
            f"Mode: `{mode.upper()}`\n"
            f"Capital: ₹{self._capital:,.0f}\n"
            "Strategy: Multi-Signal Momentum Hybrid"
        )

    def alert_daily_summary(self, stats: dict, portfolio_value: float):
        self._send(
            "📊 *Daily Summary*\n"
            f"Portfolio Value: ₹{portfolio_value:,.2f}\n"
            f"Total P&L: ₹{stats['total_pnl']:+,.2f}\n"
            f"Trades: {stats['total_trades']} | Win Rate: {stats['win_rate']:.1f}%\n"
            f"Best: {stats['best_trade_pct']:+.2f}% | Worst: {stats['worst_trade_pct']:+.2f}%"
        )


# Lightweight no-op for users without Telegram configured
NULL_ALERTER = TelegramAlerter()
