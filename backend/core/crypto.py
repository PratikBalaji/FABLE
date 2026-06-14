"""
Application-level encryption for provider credentials (AES-256-GCM).

Why app-level (not pgsodium/Vault): ciphertext stays opaque to Postgres, so a
service-role leak or RLS misconfiguration exposes only ciphertext, never the
plaintext API key. The 32-byte key lives solely in APP_ENCRYPTION_KEY (env),
never in the database.

Ciphertext layout v1 (legacy): base64(nonce(12) || ciphertext || GCM tag(16))
Ciphertext layout v2 (AAD-bound): base64(0x02 || nonce(12) || ciphertext || tag(16))

F-014 fix: v2 ciphertext binds to an AAD (e.g. user_id), preventing ciphertext
portability across user rows. Decrypt automatically detects version; v1 blobs
continue to decrypt without AAD for backward compatibility.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings

_NONCE_BYTES = 12
_V2_MARKER = b"\x02"
KEY_VERSION = 1  # bump + add a key map here when rotating keys


def _load_key() -> bytes:
    raw = settings.app_encryption_key
    if not raw:
        raise RuntimeError(
            "APP_ENCRYPTION_KEY is not set — cannot encrypt/decrypt provider credentials. "
            'Generate one: python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"'
        )
    try:
        key = base64.b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("APP_ENCRYPTION_KEY is not valid base64") from exc
    if len(key) != 32:
        raise RuntimeError(
            f"APP_ENCRYPTION_KEY must decode to 32 bytes for AES-256-GCM (got {len(key)})"
        )
    return key


def encrypt(plaintext: str, aad: bytes | None = None) -> str:
    """Encrypt a secret. When `aad` is provided, produces v2 (AAD-bound) ciphertext.

    AAD (Additional Authenticated Data) binds the ciphertext to a row-specific
    value (e.g. user_id). Decrypting with a different AAD raises an exception,
    preventing cross-user ciphertext reuse (F-014).
    """
    key = _load_key()
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), aad)
    if aad is not None:
        return base64.b64encode(_V2_MARKER + nonce + ciphertext).decode("ascii")
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str, aad: bytes | None = None) -> str:
    """Reverse of encrypt(). Auto-detects v1 (no AAD) vs v2 (AAD-bound) ciphertext.

    v1 legacy blobs (no version prefix) always decrypt without AAD regardless of
    what `aad` is passed — backward compatibility for existing stored credentials.
    """
    key = _load_key()
    blob = base64.b64decode(token)
    if blob[:1] == _V2_MARKER:
        blob = blob[1:]
        # v2: use caller-supplied AAD
    else:
        # v1 legacy: no AAD was used at encrypt time
        aad = None
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return AESGCM(key).decrypt(nonce, ciphertext, aad).decode("utf-8")
