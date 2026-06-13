"""
Envelope encryption for per-user credentials.

Each user gets a 32-byte random Data Encryption Key (DEK). The DEK encrypts
that user's credential blobs with AES-256-GCM. The DEK itself is encrypted
("wrapped") by a master Key Encryption Key (KEK) loaded from
``MASTER_ENCRYPTION_KEY``. The DB only ever stores ciphertext; plaintext keys
exist only in process memory for the duration of a request.

Threat model: an attacker with full read access to Postgres sees random bytes
and cannot recover any plaintext credential without also obtaining the KEK
from Railway env vars.

KEK rotation: set ``MASTER_ENCRYPTION_KEY_PREVIOUS`` to the old key while the
new one is active. ``unwrap_dek`` will try the current key first, then fall
back to the previous one. After re-wrapping all DEKs, drop the PREVIOUS env var.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_DEK_BYTES = 32
_NONCE_BYTES = 12  # AES-GCM standard


def _decode_kek(value: str, label: str) -> bytes:
    if not value:
        raise RuntimeError(f"{label} is not set — refusing to start")
    # Some env-var UIs (Railway, Heroku) and shells strip trailing '=' padding
    # and surrounding whitespace from the pasted value. Restore both before
    # decoding; the 32-byte length check below still rejects truncated keys.
    cleaned = value.strip()
    missing_padding = (-len(cleaned)) % 4
    if missing_padding:
        cleaned += "=" * missing_padding
    try:
        kek = base64.urlsafe_b64decode(cleaned.encode())
    except Exception as exc:
        raise RuntimeError(f"{label} is not valid urlsafe base64: {exc}")
    if len(kek) != 32:
        raise RuntimeError(
            f"{label} must decode to 32 bytes (AES-256); got {len(kek)} bytes"
        )
    return kek


@dataclass(frozen=True)
class WrappedDEK:
    """Result of ``CredentialVault.new_user_dek``."""
    wrapped_dek: bytes  # ciphertext + 16-byte GCM tag
    dek_nonce:   bytes  # 12 bytes
    kek_version: int = 1


@dataclass(frozen=True)
class Ciphertext:
    """Result of ``CredentialVault.encrypt``."""
    ciphertext: bytes  # ciphertext + 16-byte GCM tag (AESGCM API combines them)
    nonce:      bytes


class CredentialVault:
    """
    Singleton-ish vault. Construct once at app startup; pass it down.

    All public methods are pure functions of their inputs and the KEK(s)
    held by the instance — no I/O, no DB. Wrapping/unwrapping DEKs and
    encrypting/decrypting credentials are completely separate concerns
    so callers can mix-and-match.
    """

    def __init__(self, master_key_b64: str, previous_key_b64: str = ""):
        self._kek = _decode_kek(master_key_b64, "MASTER_ENCRYPTION_KEY")
        self._kek_previous: bytes | None = (
            _decode_kek(previous_key_b64, "MASTER_ENCRYPTION_KEY_PREVIOUS")
            if previous_key_b64 else None
        )

    # ── DEK lifecycle (envelope outer layer) ─────────────────────────────────

    def new_user_dek(self) -> tuple[bytes, WrappedDEK]:
        """
        Generate a fresh 32-byte DEK and wrap it under the current KEK.

        Returns ``(plaintext_dek, wrapped)`` — the caller should store
        ``wrapped`` in the DB and immediately discard ``plaintext_dek``
        (it is NOT needed again until that user signs in and a credential
        needs decryption).
        """
        dek = os.urandom(_DEK_BYTES)
        nonce = os.urandom(_NONCE_BYTES)
        ct = AESGCM(self._kek).encrypt(nonce, dek, associated_data=b"dek")
        return dek, WrappedDEK(wrapped_dek=ct, dek_nonce=nonce, kek_version=1)

    def unwrap_dek(self, wrapped: bytes, nonce: bytes) -> bytes:
        """
        Decrypt a wrapped DEK using the current KEK. Falls back to the
        previous KEK if rotation is in progress. Raises ``InvalidTag`` if
        neither key works (DB tampering or wrong env vars).
        """
        try:
            return AESGCM(self._kek).decrypt(nonce, wrapped, associated_data=b"dek")
        except InvalidTag:
            if self._kek_previous is None:
                raise
            return AESGCM(self._kek_previous).decrypt(
                nonce, wrapped, associated_data=b"dek",
            )

    def rewrap_dek(self, wrapped: bytes, nonce: bytes) -> WrappedDEK:
        """Used by the rotation script: unwrap with old/new fallback, re-wrap with current."""
        dek = self.unwrap_dek(wrapped, nonce)
        new_nonce = os.urandom(_NONCE_BYTES)
        new_ct = AESGCM(self._kek).encrypt(new_nonce, dek, associated_data=b"dek")
        return WrappedDEK(wrapped_dek=new_ct, dek_nonce=new_nonce, kek_version=1)

    # ── Credential payload (envelope inner layer) ────────────────────────────

    def encrypt(self, dek: bytes, plaintext: str) -> Ciphertext:
        """Encrypt a credential string with the user's DEK."""
        nonce = os.urandom(_NONCE_BYTES)
        ct = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), associated_data=b"cred")
        return Ciphertext(ciphertext=ct, nonce=nonce)

    def decrypt(self, dek: bytes, ciphertext: bytes, nonce: bytes) -> str:
        """Decrypt a credential previously produced by ``encrypt``."""
        plain = AESGCM(dek).decrypt(nonce, ciphertext, associated_data=b"cred")
        return plain.decode("utf-8")
