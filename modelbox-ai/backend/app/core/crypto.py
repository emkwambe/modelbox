"""Symmetric encryption for stored secrets (AES-256-GCM).

Used to encrypt database connection URIs at rest (NFR-3.1). The 32-byte key is
derived from ``settings.encryption_key`` via SHA-256, so any key string works;
production should set a strong, secret value.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_NONCE_BYTES = 12


def _key() -> bytes:
    return hashlib.sha256(get_settings().encryption_key.encode("utf-8")).digest()


def encrypt_secret(plaintext: str) -> str:
    """Return a base64 ``nonce || ciphertext`` token for ``plaintext``."""
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Reverse :func:`encrypt_secret`."""
    raw = base64.b64decode(token)
    nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
