"""TOTP and encrypted MFA-secret helpers (RFC 6238, SHA-1, 30-second step)."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _key() -> bytes:
    try:
        key = base64.urlsafe_b64decode(settings.auth_encryption_key.encode())
    except Exception as exc:
        raise RuntimeError("AUTH_ENCRYPTION_KEY must be a URL-safe base64 encoded 32-byte key") from exc
    if len(key) != 32:
        raise RuntimeError("AUTH_ENCRYPTION_KEY must decode to exactly 32 bytes")
    return key


def encrypt_secret(secret: str) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, secret.encode(), b"mdis-mfa-v1")
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_secret(ciphertext: str) -> str:
    payload = base64.urlsafe_b64decode(ciphertext.encode())
    return AESGCM(_key()).decrypt(payload[:12], payload[12:], b"mdis-mfa-v1").decode()


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp(secret: str, at: int | None = None) -> str:
    counter = int((at if at is not None else time.time()) // 30)
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp(secret: str, code: str, at: int | None = None) -> bool:
    if len(code) != 6 or not code.isdigit():
        return False
    now = at if at is not None else time.time()
    return any(hmac.compare_digest(totp(secret, int(now) + skew * 30), code) for skew in (-1, 0, 1))


def provisioning_uri(secret: str, email: str) -> str:
    label = quote(f"Cognate AI:{email}", safe="")
    issuer = quote("Cognate AI", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


def new_recovery_codes(count: int = 10) -> list[str]:
    return [secrets.token_urlsafe(12) for _ in range(count)]


def recovery_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()
