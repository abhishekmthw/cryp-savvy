"""
Telegram alert system.
Sends non-blocking notifications for trades, errors, and daily summaries.
If TELEGRAM_BOT_TOKEN is empty, all calls are silent no-ops.
"""

import asyncio
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings


def _send(text: str):
    """Fire-and-forget Telegram message. Silently ignores errors."""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return
    try:
        from telegram import Bot
        async def _do():
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            await bot.send_message(
                chat_id=settings.TELEGRAM_CHAT_ID,
                text=text,
                parse_mode="Markdown",
            )
        # Run in a fresh event loop so we don't need to be inside an async context
        asyncio.run(_do())
    except Exception:
        pass   # Never crash the bot over a failed notification


def alert_buy(symbol: str, price: float, amount_inr: float,
              score: float, mode: str = "paper"):
    tag = "[PAPER]" if mode == "paper" else "[LIVE]"
    _send(
        f"*{tag} BUY* `{symbol}`\n"
        f"Price: ₹{price:,.4f}\n"
        f"Amount: ₹{amount_inr:,.2f}\n"
        f"Signal Score: {score:.1f}/100"
    )


def alert_sell(symbol: str, price: float, pnl: float,
               pnl_pct: float, reason: str, mode: str = "paper"):
    tag   = "[PAPER]" if mode == "paper" else "[LIVE]"
    emoji = "✅" if pnl >= 0 else "❌"
    _send(
        f"*{tag} SELL* `{symbol}` {emoji}\n"
        f"Exit Price: ₹{price:,.4f}\n"
        f"P&L: ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
        f"Reason: `{reason}`"
    )


def alert_daily_limit():
    _send(
        "⚠️ *Daily loss limit reached.*\n"
        f"Bot has paused trading for today (limit: ₹{settings.DAILY_LOSS_LIMIT_INR:,.0f})."
    )


def alert_error(message: str):
    _send(f"🔴 *Bot Error*\n`{message}`")


def alert_startup(mode: str):
    _send(
        f"🚀 *CrypSavvy Started*\n"
        f"Mode: `{mode.upper()}`\n"
        f"Capital: ₹{settings.INITIAL_CAPITAL_INR:,.0f}\n"
        f"Strategy: Multi-Signal Momentum Hybrid"
    )


def alert_daily_summary(stats: dict, portfolio_value: float):
    _send(
        f"📊 *Daily Summary*\n"
        f"Portfolio Value: ₹{portfolio_value:,.2f}\n"
        f"Total P&L: ₹{stats['total_pnl']:+,.2f}\n"
        f"Trades: {stats['total_trades']} | Win Rate: {stats['win_rate']:.1f}%\n"
        f"Best: {stats['best_trade_pct']:+.2f}% | Worst: {stats['worst_trade_pct']:+.2f}%"
    )
