"""
Per-provider credential validation.

Each ``validate_*`` function makes a single read-only round-trip against the
real provider and returns ``(ok: bool, message: str)``. Called from the
credentials API immediately after saving — on failure the caller deletes
the freshly-written rows so the user only ever sees a "verified" state for
keys that actually work.
"""

from __future__ import annotations


def validate_coindcx(api_key: str, api_secret: str) -> tuple[bool, str]:
    """Verify CoinDCX keys via a read-only ``fetch_balance`` call."""
    if not api_key or not api_secret:
        return False, "missing_credentials"
    try:
        import requests
        from src.exchange.coindcx_client import CoinDCXClient
        client = CoinDCXClient(api_key=api_key, api_secret=api_secret)
        client.fetch_balance()
        return True, "ok"
    except requests.HTTPError as exc:
        # CoinDCX returns 401 on bad keys, 400 on malformed signature
        if exc.response is not None and exc.response.status_code in (400, 401):
            return False, f"authentication_failed: {exc}"
        return False, f"network_or_provider_error: {exc}"
    except Exception as exc:
        return False, f"network_or_provider_error: {exc}"


async def validate_telegram(bot_token: str, chat_id: str) -> tuple[bool, str]:
    """
    Verify a Telegram bot/chat pair by:
    1. Calling ``get_me()`` (fast, no chat needed)
    2. Sending a one-line "connected" message to the chat (proves the chat is reachable)
    """
    if not bot_token or not chat_id:
        return False, "missing_credentials"

    try:
        from telegram import Bot

        bot = Bot(token=bot_token)
        await bot.get_me()
        await bot.send_message(
            chat_id=chat_id,
            text="✅ CrypSavvy connected — credential verification successful.",
        )
        return True, "ok"
    except Exception as exc:
        # Cover the python-telegram-bot exception hierarchy without importing every type.
        msg = str(exc).lower()
        if "unauthorized" in msg or "invalid token" in msg:
            return False, "invalid_bot_token"
        if "chat not found" in msg or "chat_id is empty" in msg:
            return False, "invalid_chat_id"
        return False, f"telegram_error: {exc}"
