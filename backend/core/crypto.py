"""
Application-level encryption for provider credentials (AES-256-GCM).

Why app-level (not pgsodium/Vault): ciphertext stays opaque to Postgres, so a
service-role leak or RLS misconfiguration exposes only ciphertext, never the
plaintext API key. Keys live solely in env, never in the database.

Ciphertext layouts (before base64):
  v1 (legacy):     nonce(12) || ct                — no AAD, single key
  v2 (AAD-bound):  0x02 || nonce(12) || ct        — AAD, single key  (F-014)
  v3 (rotation):   0x03 || keyver(1) || nonce(12) || ct  — AAD, key selected by version  (F-016)

Decrypt auto-detects the version from the leading byte and selects the right key,
so rotating keys never breaks existing ciphertext. New writes use v3 when a key
map (APP_ENCRYPTION_KEYS) + active version are configured, else v2 (single key).
"""
from __future__ import annotations

import base64

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings

_NONCE_BYTES = 12
_V2_MARKER = b"\x02"
_V3_MARKER = b"\x03"
KEY_VERSION = 1  # informational; rotation is driven by APP_ENCRYPTION_KEY_ACTIVE


def _decode_key(raw: str, label: str) -> bytes:
    try:
        key = base64.b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"{label} is not valid base64") from exc
    if len(key) != 32:
        raise RuntimeError(f"{label} must decode to 32 bytes for AES-256-GCM (got {len(key)})")
    return key


def _load_single_key() -> bytes:
    raw = settings.app_encryption_key
    if not raw:
        raise RuntimeError(
            "APP_ENCRYPTION_KEY is not set — cannot encrypt/decrypt provider credentials. "
            'Generate one: python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"'
        )
    return _decode_key(raw, "APP_ENCRYPTION_KEY")


def _load_key_map() -> dict[int, bytes]:
    """Parse APP_ENCRYPTION_KEYS ('ver:b64,ver:b64') into {version: key}. Empty if unset."""
    raw = settings.app_encryption_keys.strip()
    if not raw:
        return {}
    out: dict[int, bytes] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        try:
            ver_s, key_b64 = pair.split(":", 1)
            ver = int(ver_s.strip())
        except ValueError as exc:
            raise RuntimeError(f"APP_ENCRYPTION_KEYS entry malformed (want 'version:b64'): {pair!r}") from exc
        out[ver] = _decode_key(key_b64.strip(), f"APP_ENCRYPTION_KEYS[{ver}]")
    return out


def encrypt(plaintext: str, aad: bytes | None = None) -> str:
    """Encrypt a secret. With `aad`, produces AAD-bound ciphertext (binds to a row,
    e.g. user_id). Uses v3 (rotation) when a key map + active version are configured,
    else v2 (single key). Decrypting with a different AAD raises (F-014)."""
    key_map = _load_key_map()
    active = settings.app_encryption_key_active
    pt = plaintext.encode("utf-8")
    nonce = os.urandom(_NONCE_BYTES)

    if key_map and active in key_map:
        # v3 — versioned key
        ct = AESGCM(key_map[active]).encrypt(nonce, pt, aad)
        return base64.b64encode(_V3_MARKER + bytes([active & 0xFF]) + nonce + ct).decode("ascii")

    key = _load_single_key()
    ct = AESGCM(key).encrypt(nonce, pt, aad)
    if aad is not None:
        return base64.b64encode(_V2_MARKER + nonce + ct).decode("ascii")
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(token: str, aad: bytes | None = None) -> str:
    """Reverse of encrypt(). Auto-detects v1/v2/v3 by leading byte and selects the key.
    v1 legacy blobs always decrypt without AAD (back-compat)."""
    blob = base64.b64decode(token)
    marker = blob[:1]

    if marker == _V3_MARKER:
        key_ver = blob[1]
        key_map = _load_key_map()
        if key_ver not in key_map:
            raise RuntimeError(f"No key configured for ciphertext version {key_ver} (set APP_ENCRYPTION_KEYS)")
        key = key_map[key_ver]
        body = blob[2:]
    elif marker == _V2_MARKER:
        key = _load_single_key()
        body = blob[1:]
    else:
        # v1 legacy: no version prefix, no AAD was used at encrypt time
        key = _load_single_key()
        aad = None
        body = blob

    nonce, ct = body[:_NONCE_BYTES], body[_NONCE_BYTES:]
    return AESGCM(key).decrypt(nonce, ct, aad).decode("utf-8")
