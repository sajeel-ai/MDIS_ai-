"""AES-256-GCM encryption at rest for document files in storage."""

import base64
import binascii
import hashlib
import logging
import os
from typing import List, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

logger = logging.getLogger(__name__)

MAGIC_HEADER = b"MDIS_ENC_V1"
MAGIC_HEADER_V2 = b"MDIS_ENC_V2"
KEY_ID_LENGTH_BYTES = 16
NONCE_LENGTH_BYTES = 12
TAG_LENGTH_BYTES = 16
KEY_LENGTH_BYTES = 32



def _parse_key_bytes(raw: bytes | str) -> bytes:
    if isinstance(raw, bytes):
        if len(raw) == KEY_LENGTH_BYTES:
            return raw
        raise ValueError(f"Storage encryption key must be {KEY_LENGTH_BYTES} bytes, got {len(raw)}")

    raw_str = raw.strip()
    # Check if 64-char hex
    if len(raw_str) == 64:
        try:
            parsed = binascii.unhexlify(raw_str)
            if len(parsed) == KEY_LENGTH_BYTES:
                return parsed
        except binascii.Error:
            pass

    # Check if base64 encoded
    try:
        parsed = base64.b64decode(raw_str)
        if len(parsed) == KEY_LENGTH_BYTES:
            return parsed
    except Exception:
        pass

    # Direct utf-8 bytes
    utf8 = raw_str.encode("utf-8")
    if len(utf8) == KEY_LENGTH_BYTES:
        return utf8

    raise ValueError(f"Storage encryption key must be {KEY_LENGTH_BYTES} bytes (raw, hex, or base64)")


def get_storage_encryption_key(key: bytes | str | None = None) -> bytes:
    """Resolve active 256-bit encryption key from parameter, settings, or environment."""
    if key is not None:
        return _parse_key_bytes(key)

    configured = settings.storage_encryption_key or os.getenv("STORAGE_ENCRYPTION_KEY", "")
    if configured.strip():
        return _parse_key_bytes(configured)

    raise RuntimeError("STORAGE_ENCRYPTION_KEY must be configured in every environment")


def get_previous_storage_keys() -> List[bytes]:
    """Return configured previous/retired encryption keys for rotation."""
    raw = settings.storage_encryption_previous_keys or os.getenv("STORAGE_ENCRYPTION_PREVIOUS_KEYS", "")
    if not raw.strip():
        return []
    keys = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk:
            try:
                keys.append(_parse_key_bytes(chunk))
            except ValueError as exc:
                logger.warning("Ignoring invalid previous storage encryption key: %s", exc)
    return keys


def is_encrypted(payload: bytes) -> bool:
    """Return True for supported versioned MDIS ciphertext payloads."""
    return payload.startswith((MAGIC_HEADER, MAGIC_HEADER_V2))


def get_storage_key_id(key: bytes | str) -> str:
    """Return a non-secret stable identifier for a 256-bit encryption key."""
    return hashlib.sha256(_parse_key_bytes(key)).hexdigest()[:KEY_ID_LENGTH_BYTES]


def get_payload_key_id(payload: bytes) -> str | None:
    """Read the key identifier from V2 files; V1 files have no key id."""
    if not payload.startswith(MAGIC_HEADER_V2):
        return None
    start = len(MAGIC_HEADER_V2)
    end = start + KEY_ID_LENGTH_BYTES
    try:
        return payload[start:end].decode("ascii")
    except (UnicodeDecodeError, IndexError):
        return None


def encrypt_bytes(data: bytes, key: bytes | str | None = None) -> bytes:
    """Encrypt data as V2 AES-256-GCM with key id and unique nonce."""
    active_key = get_storage_encryption_key(key)
    aesgcm = AESGCM(active_key)
    nonce = os.urandom(NONCE_LENGTH_BYTES)
    key_id = get_storage_key_id(active_key).encode("ascii")
    authenticated_header = MAGIC_HEADER_V2 + key_id
    ciphertext = aesgcm.encrypt(nonce, data, associated_data=authenticated_header)
    return authenticated_header + nonce + ciphertext


def decrypt_bytes(payload: bytes, key: bytes | str | None = None, strict: bool = False) -> bytes:
    """Decrypt payload using AES-256-GCM.
    
    If payload is not encrypted and strict=False, returns payload unmodified
    (allowing graceful migration of pre-existing storage files).
    """
    if not is_encrypted(payload):
        if strict:
            raise ValueError("Payload is not encrypted with MDIS_ENC_V1")
        return payload

    is_v2 = payload.startswith(MAGIC_HEADER_V2)
    if is_v2:
        header_len = len(MAGIC_HEADER_V2) + KEY_ID_LENGTH_BYTES
        encoded_id = payload[len(MAGIC_HEADER_V2):header_len]
        try:
            expected_key_id = encoded_id.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("Encrypted payload has an invalid key identifier") from exc
        associated_data = payload[:header_len]
    else:
        header_len = len(MAGIC_HEADER)
        expected_key_id = None
        associated_data = MAGIC_HEADER
    nonce = payload[header_len : header_len + NONCE_LENGTH_BYTES]
    ciphertext = payload[header_len + NONCE_LENGTH_BYTES :]

    candidate_keys = [get_storage_encryption_key(key)]
    candidate_keys.extend(get_previous_storage_keys())

    last_error = None
    for k in candidate_keys:
        if expected_key_id is not None and get_storage_key_id(k) != expected_key_id:
            continue
        try:
            aesgcm = AESGCM(k)
            return aesgcm.decrypt(nonce, ciphertext, associated_data=associated_data)
        except Exception as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise ValueError("Decryption failed: no valid key found")

