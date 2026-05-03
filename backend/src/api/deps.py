"""
Shared FastAPI dependencies.

`get_current_user` is the seam between the Clerk JWT and our DB. Every route
that touches user-scoped data depends on it. The dependency lazy-creates a
``User`` row (with a fresh wrapped DEK) on the first authenticated request
from a new Clerk identity.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from src.api.auth import verify_clerk_token
from src.db.engine import session_scope
from src.db.models import User
from src.db import repositories as repo
from src.security.crypto import CredentialVault


_bearer = HTTPBearer(auto_error=True)


def get_vault() -> CredentialVault:
    """Lazily build the vault from current settings. Raises at startup if KEK missing."""
    if _vault_singleton["instance"] is None:
        from config import settings
        _vault_singleton["instance"] = CredentialVault(
            master_key_b64=settings.MASTER_ENCRYPTION_KEY,
            previous_key_b64=settings.MASTER_ENCRYPTION_KEY_PREVIOUS,
        )
    return _vault_singleton["instance"]


_vault_singleton: dict = {"instance": None}


def get_db() -> Session:
    """Per-request session. Use as Depends(get_db)."""
    with session_scope() as db:
        yield db


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
    vault: Annotated[CredentialVault, Depends(get_vault)],
) -> User:
    payload = await verify_clerk_token(creds.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )
    email = payload.get("email") or payload.get("primary_email_address")
    user = repo.get_user_or_create(db, clerk_user_id=sub, email=email, vault=vault)
    return user


async def get_current_user_id(user: Annotated[User, Depends(get_current_user)]) -> str:
    """Convenience for routes that only need the ID, not the row."""
    return user.clerk_user_id
