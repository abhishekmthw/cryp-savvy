"""
Clerk JWT verification for FastAPI.

Clerk issues RS256-signed JWTs.  We verify them locally using Clerk's JWKS
endpoint so no network call is needed on the hot path (JWKS is cached 1 hour).
"""

import re
import time
import httpx
from jose import jwt, JWTError
from fastapi import HTTPException, status
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from config import settings
from src.monitoring.logger import get_logger

log = get_logger()

# ── JWKS cache ────────────────────────────────────────────────────────────────

_jwks_cache: dict = {"data": None, "expires_at": 0.0}
_CACHE_TTL = 1800  # seconds — shorter so a Clerk key rotation propagates faster

# Clerk subject claims look like ``user_2abc…``. Reject anything else early.
_SUB_RE = re.compile(r"^user_[A-Za-z0-9]+$")


def is_valid_clerk_sub(sub: str | None) -> bool:
    return bool(sub) and bool(_SUB_RE.match(sub))


async def _get_jwks(force: bool = False) -> dict:
    now = time.time()
    if not force and _jwks_cache["data"] and now < _jwks_cache["expires_at"]:
        return _jwks_cache["data"]

    if not settings.CLERK_JWKS_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is not configured",
        )

    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.CLERK_JWKS_URL, timeout=10)
        resp.raise_for_status()

    _jwks_cache["data"] = resp.json()
    _jwks_cache["expires_at"] = now + _CACHE_TTL
    return _jwks_cache["data"]


# ── Public API ────────────────────────────────────────────────────────────────

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired authentication token",
    headers={"WWW-Authenticate": "Bearer"},
)


async def verify_clerk_token(token: str) -> dict:
    """
    Verify a Clerk JWT and return its payload. Raises a generic HTTP 401 on any
    failure — exception details are logged server-side only, never returned to
    the client (avoids leaking internal/Clerk error text).
    """
    if not token:
        raise _UNAUTHORIZED
    try:
        jwks = await _get_jwks()
        try:
            return _decode(token, jwks)
        except JWTError:
            # Possibly a rotated signing key the cache hasn't seen — force one
            # refresh and retry before giving up (kid-miss invalidation).
            jwks = await _get_jwks(force=True)
            return _decode(token, jwks)
    except JWTError as exc:
        log.info("JWT verification failed: %s", exc)
        raise _UNAUTHORIZED
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Authentication error: %s", exc)
        raise _UNAUTHORIZED


def _decode(token: str, jwks: dict) -> dict:
    return jwt.decode(
        token, jwks, algorithms=["RS256"],
        options={"verify_aud": False},  # Clerk JWTs omit `aud` by default
    )
