"""Tests for the envelope-encryption credential vault."""

from __future__ import annotations

import base64
import os

import pytest
from cryptography.exceptions import InvalidTag

from src.security.crypto import CredentialVault


def _new_kek_b64() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def test_round_trip_encrypt_decrypt():
    kek = _new_kek_b64()
    vault = CredentialVault(kek)
    dek, wrapped = vault.new_user_dek()

    secret = "sk_live_supersecret_4f2a"
    ct = vault.encrypt(dek, secret)

    assert ct.ciphertext != secret.encode()
    assert vault.decrypt(dek, ct.ciphertext, ct.nonce) == secret


def test_unwrap_with_wrong_kek_raises():
    vault_a = CredentialVault(_new_kek_b64())
    _, wrapped = vault_a.new_user_dek()

    vault_b = CredentialVault(_new_kek_b64())
    with pytest.raises(InvalidTag):
        vault_b.unwrap_dek(wrapped.wrapped_dek, wrapped.dek_nonce)


def test_kek_rotation_via_previous_fallback():
    kek_old = _new_kek_b64()
    vault_old = CredentialVault(kek_old)
    dek, wrapped = vault_old.new_user_dek()
    ct = vault_old.encrypt(dek, "telegram_token_xyz")

    # Operator generates a fresh KEK and demotes the old one to PREVIOUS
    kek_new = _new_kek_b64()
    vault_new = CredentialVault(kek_new, previous_key_b64=kek_old)

    # Old wrapped DEK still decrypts via fallback
    dek_recovered = vault_new.unwrap_dek(wrapped.wrapped_dek, wrapped.dek_nonce)
    assert vault_new.decrypt(dek_recovered, ct.ciphertext, ct.nonce) == "telegram_token_xyz"

    # Re-wrap and verify the new wrapping uses the new KEK (fails on old-only vault)
    rewrapped = vault_new.rewrap_dek(wrapped.wrapped_dek, wrapped.dek_nonce)
    vault_old_only = CredentialVault(kek_old)
    with pytest.raises(InvalidTag):
        vault_old_only.unwrap_dek(rewrapped.wrapped_dek, rewrapped.dek_nonce)


def test_tampered_ciphertext_rejected():
    vault = CredentialVault(_new_kek_b64())
    dek, _ = vault.new_user_dek()
    ct = vault.encrypt(dek, "coindcx_secret")

    # Flip one bit anywhere in the body — GCM's auth tag must catch it.
    tampered = bytearray(ct.ciphertext)
    tampered[0] ^= 0x01
    with pytest.raises(InvalidTag):
        vault.decrypt(dek, bytes(tampered), ct.nonce)


def test_tampered_dek_rejected():
    vault = CredentialVault(_new_kek_b64())
    _, wrapped = vault.new_user_dek()

    tampered = bytearray(wrapped.wrapped_dek)
    tampered[-1] ^= 0x01  # corrupt the GCM tag
    with pytest.raises(InvalidTag):
        vault.unwrap_dek(bytes(tampered), wrapped.dek_nonce)


def test_invalid_master_key_refuses_to_construct():
    with pytest.raises(RuntimeError, match="not set"):
        CredentialVault("")

    with pytest.raises(RuntimeError, match="32 bytes"):
        # 16 bytes — too short for AES-256
        CredentialVault(base64.urlsafe_b64encode(os.urandom(16)).decode())


def test_distinct_users_have_distinct_deks():
    vault = CredentialVault(_new_kek_b64())
    dek_a, wrapped_a = vault.new_user_dek()
    dek_b, wrapped_b = vault.new_user_dek()

    assert dek_a != dek_b
    assert wrapped_a.wrapped_dek != wrapped_b.wrapped_dek
    assert wrapped_a.dek_nonce != wrapped_b.dek_nonce
