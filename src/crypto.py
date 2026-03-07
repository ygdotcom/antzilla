"""AES-256-GCM encryption for secrets stored in the database.

The ENCRYPTION_KEY env var is a 32-byte hex string (64 hex chars).
Generate with: openssl rand -hex 32
"""

from __future__ import annotations

import os
import secrets as _secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_key() -> bytes:
    """Load the 32-byte encryption key from the environment."""
    hex_key = os.environ.get("ENCRYPTION_KEY", "")
    if not hex_key or len(hex_key) < 64:
        raise RuntimeError(
            "ENCRYPTION_KEY not set or too short. Generate with: openssl rand -hex 32"
        )
    return bytes.fromhex(hex_key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string with AES-256-GCM. Returns nonce+ciphertext as hex."""
    key = _get_key()
    nonce = _secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return (nonce + ciphertext).hex()


def decrypt(hex_data: str) -> str:
    """Decrypt a hex-encoded nonce+ciphertext string."""
    key = _get_key()
    raw = bytes.fromhex(hex_data)
    nonce = raw[:12]
    ciphertext = raw[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
