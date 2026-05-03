"""
Clerk JWT verification for FastAPI.

Clerk issues RS256-signed JWTs.  We verify them locally using Clerk's JWKS
endpoint so no network call is needed on the hot path (JWKS is cached 1 hour).
"""

import time
import httpx
from jose import jwt, JWTError
from fastapi import HTTPException, status
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from config import settings

# ── JWKS cache ────────────────────────────────────────────────────────────────

_jwks_cache: dict = {"data": None, "expires_at": 0.0}
_CACHE_TTL = 3600  # seconds


async def _get_jwks() -> dict:
    now = time.time()
    if _jwks_cache["data"] and now < _jwks_cache["expires_at"]:
        return _jwks_cache["data"]

    if not settings.CLERK_JWKS_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CLERK_JWKS_URL is not configured",
        )

    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.CLERK_JWKS_URL, timeout=10)
        resp.raise_for_status()

    _jwks_cache["data"] = resp.json()
    _jwks_cache["expires_at"] = now + _CACHE_TTL
    return _jwks_cache["data"]


# ── Public API ────────────────────────────────────────────────────────────────

async def verify_clerk_token(token: str) -> dict:
    """
    Verify a Clerk JWT and return its payload.
    Raises HTTP 401 on any failure.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        jwks = await _get_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk JWTs omit `aud` by default
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {exc}",
        )
