"""Symmetric encryption for provider API keys stored at rest.

Uses Fernet (AES-128-CBC + HMAC). In production set QUORUM_ENCRYPTION_KEY to a
generated Fernet key. For local dev, a stable key is derived from a fixed salt so
existing rows stay decryptable across restarts.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_DEV_SALT = b"quorum-gatherer-dev-salt-v1"


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if settings.encryption_key:
        key = settings.encryption_key.encode()
    else:
        # Derive a deterministic dev key so encrypted rows survive restarts.
        digest = hashlib.sha256(_DEV_SALT).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
