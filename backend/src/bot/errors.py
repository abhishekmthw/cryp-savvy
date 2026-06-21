"""Domain errors for the bot lifecycle."""

from __future__ import annotations


class BotStartError(Exception):
    """Raised when a bot can't be started for a reason worth surfacing to the
    user (e.g. stored credentials can't be decrypted).

    Carries a sanitized, user-facing message only — never the underlying
    exception detail or a stack trace. The API layer maps it to a 409 with
    ``str(exc)`` as the response detail.
    """
