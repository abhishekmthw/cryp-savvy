"""
User-credential management API.

Routes:
    GET    /api/credentials              → masked summary of saved providers
    PUT    /api/credentials/coindcx      → save + validate CoinDCX key + secret
    PUT    /api/credentials/telegram     → save + validate Telegram bot token + chat ID
    DELETE /api/credentials/coindcx
    DELETE /api/credentials/telegram
    POST   /api/credentials/coindcx/test → re-run validation against stored creds
    POST   /api/credentials/telegram/test

Hard guarantee: ``GET`` never returns plaintext. ``PUT`` writes ciphertext, runs
read-only validation, and on failure deletes what it just wrote — the user
never has a "saved but unverified" state.
"""

from __future__ import annotations

import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from src.api.deps import get_current_user, get_db, get_vault
from src.api.validation import validate_coindcx, validate_telegram
from src.db import repositories as repo
from src.db.models import User
from src.security.crypto import CredentialVault


router = APIRouter(prefix="/api/credentials", tags=["credentials"])


# ── Provider names (must match seed in repositories) ─────────────────────────

P_COINDCX_KEY     = "coindcx_key"
P_COINDCX_SECRET  = "coindcx_secret"
P_TELEGRAM_TOKEN  = "telegram_bot_token"
P_TELEGRAM_CHAT   = "telegram_chat_id"


# ── Request / response models ────────────────────────────────────────────────

class CoinDCXIn(BaseModel):
    api_key:    str = Field(min_length=10)
    api_secret: str = Field(min_length=10)


class TelegramIn(BaseModel):
    bot_token: str = Field(min_length=10)
    chat_id:   str = Field(min_length=1)


class ProviderStatus(BaseModel):
    present:     bool
    valid:       bool
    last4:       str | None = None
    verified_at: float | None = None


class CredentialsSummary(BaseModel):
    coindcx:  ProviderStatus
    telegram: ProviderStatus


# ── Helpers ──────────────────────────────────────────────────────────────────

def _last4(s: str) -> str:
    s = (s or "").strip()
    return s[-4:] if len(s) >= 4 else s


def _save(
    db: Session, vault: CredentialVault, user: User,
    *, provider: str, plaintext: str, last4: str, valid: bool,
    verified_at: float | None,
) -> None:
    dek = vault.unwrap_dek(user.wrapped_dek, user.dek_nonce)
    ct = vault.encrypt(dek, plaintext)
    repo.upsert_credential(
        db,
        user_id=user.clerk_user_id,
        provider=provider,
        ciphertext=ct.ciphertext,
        nonce=ct.nonce,
        last4=last4,
        valid=valid,
        verified_at=verified_at,
    )


def _decrypt_pair(
    db: Session, vault: CredentialVault, user: User,
    *, provider_a: str, provider_b: str,
) -> tuple[str, str] | None:
    a = repo.get_credential(db, user.clerk_user_id, provider_a)
    b = repo.get_credential(db, user.clerk_user_id, provider_b)
    if not a or not b:
        return None
    dek = vault.unwrap_dek(user.wrapped_dek, user.dek_nonce)
    return vault.decrypt(dek, a.ciphertext, a.nonce), vault.decrypt(dek, b.ciphertext, b.nonce)


# ── GET ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=CredentialsSummary)
async def list_credentials(
    user: Annotated[User, Depends(get_current_user)],
    db:   Annotated[Session, Depends(get_db)],
):
    creds = {c.provider: c for c in repo.get_credentials(db, user.clerk_user_id)}

    def _status(provider: str) -> ProviderStatus:
        c = creds.get(provider)
        if not c:
            return ProviderStatus(present=False, valid=False)
        return ProviderStatus(
            present=True,
            valid=bool(c.valid),
            last4=c.last4,
            verified_at=c.verified_at.timestamp() if c.verified_at else None,
        )

    return CredentialsSummary(
        coindcx=_status(P_COINDCX_KEY),
        telegram=_status(P_TELEGRAM_TOKEN),
    )


# ── CoinDCX ──────────────────────────────────────────────────────────────────

@router.put("/coindcx")
async def put_coindcx(
    body:  CoinDCXIn,
    user:  Annotated[User, Depends(get_current_user)],
    db:    Annotated[Session, Depends(get_db)],
    vault: Annotated[CredentialVault, Depends(get_vault)],
):
    ok, message = await asyncio.to_thread(validate_coindcx, body.api_key, body.api_secret)
    if not ok:
        # Do not save anything that didn't validate — fail closed.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_coindcx_keys", "message": message},
        )

    now = time.time()
    _save(db, vault, user,
          provider=P_COINDCX_KEY,    plaintext=body.api_key,
          last4=_last4(body.api_key), valid=True, verified_at=now)
    _save(db, vault, user,
          provider=P_COINDCX_SECRET, plaintext=body.api_secret,
          last4=_last4(body.api_secret), valid=True, verified_at=now)
    return {"ok": True, "verified_at": now, "last4": _last4(body.api_key)}


@router.delete("/coindcx")
async def delete_coindcx(
    user: Annotated[User, Depends(get_current_user)],
    db:   Annotated[Session, Depends(get_db)],
):
    repo.delete_credential(db, user_id=user.clerk_user_id, provider=P_COINDCX_KEY)
    repo.delete_credential(db, user_id=user.clerk_user_id, provider=P_COINDCX_SECRET)
    return {"ok": True}


@router.post("/coindcx/test")
async def test_coindcx(
    user:  Annotated[User, Depends(get_current_user)],
    db:    Annotated[Session, Depends(get_db)],
    vault: Annotated[CredentialVault, Depends(get_vault)],
):
    pair = _decrypt_pair(db, vault, user,
                         provider_a=P_COINDCX_KEY, provider_b=P_COINDCX_SECRET)
    if pair is None:
        raise HTTPException(404, detail="no_coindcx_credentials")
    api_key, api_secret = pair
    ok, message = await asyncio.to_thread(validate_coindcx, api_key, api_secret)
    repo.upsert_credential(  # update validity flag + verified_at without re-encrypting
        db,
        user_id=user.clerk_user_id, provider=P_COINDCX_KEY,
        ciphertext=repo.get_credential(db, user.clerk_user_id, P_COINDCX_KEY).ciphertext,
        nonce=repo.get_credential(db, user.clerk_user_id, P_COINDCX_KEY).nonce,
        last4=_last4(api_key), valid=ok,
        verified_at=time.time() if ok else None,
    )
    return {"ok": ok, "message": message}


# ── Telegram ─────────────────────────────────────────────────────────────────

@router.put("/telegram")
async def put_telegram(
    body:  TelegramIn,
    user:  Annotated[User, Depends(get_current_user)],
    db:    Annotated[Session, Depends(get_db)],
    vault: Annotated[CredentialVault, Depends(get_vault)],
):
    ok, message = await validate_telegram(body.bot_token, body.chat_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_telegram_credentials", "message": message},
        )

    now = time.time()
    _save(db, vault, user,
          provider=P_TELEGRAM_TOKEN, plaintext=body.bot_token,
          last4=_last4(body.bot_token), valid=True, verified_at=now)
    _save(db, vault, user,
          provider=P_TELEGRAM_CHAT,  plaintext=body.chat_id,
          last4=_last4(body.chat_id), valid=True, verified_at=now)
    return {"ok": True, "verified_at": now, "last4": _last4(body.bot_token)}


@router.delete("/telegram")
async def delete_telegram(
    user: Annotated[User, Depends(get_current_user)],
    db:   Annotated[Session, Depends(get_db)],
):
    repo.delete_credential(db, user_id=user.clerk_user_id, provider=P_TELEGRAM_TOKEN)
    repo.delete_credential(db, user_id=user.clerk_user_id, provider=P_TELEGRAM_CHAT)
    return {"ok": True}


@router.post("/telegram/test")
async def test_telegram(
    user:  Annotated[User, Depends(get_current_user)],
    db:    Annotated[Session, Depends(get_db)],
    vault: Annotated[CredentialVault, Depends(get_vault)],
):
    pair = _decrypt_pair(db, vault, user,
                         provider_a=P_TELEGRAM_TOKEN, provider_b=P_TELEGRAM_CHAT)
    if pair is None:
        raise HTTPException(404, detail="no_telegram_credentials")
    bot_token, chat_id = pair
    ok, message = await validate_telegram(bot_token, chat_id)
    return {"ok": ok, "message": message}
