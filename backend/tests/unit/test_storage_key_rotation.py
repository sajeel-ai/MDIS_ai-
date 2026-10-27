from pathlib import Path
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings
from app.security.storage_crypto import MAGIC_HEADER, decrypt_bytes, encrypt_bytes, get_payload_key_id, get_storage_key_id
from scripts.rotate_storage_key import rotate_storage


def test_rotation_dry_run_apply_verify_and_repeat_idempotently(tmp_path, monkeypatch):
    old_key = b"o" * 32
    new_key = b"n" * 32
    monkeypatch.setattr(settings, "storage_encryption_key", new_key.hex())
    monkeypatch.setattr(settings, "storage_encryption_previous_keys", old_key.hex())
    document = tmp_path / "document.bin"
    plaintext = b"synthetic PHI fixture"
    old_encrypted = encrypt_bytes(plaintext, key=old_key)
    document.write_bytes(old_encrypted)

    preview = rotate_storage(tmp_path, dry_run=True)
    assert preview == {"scanned": 1, "rotated": 1, "unchanged": 0, "errors": 0}
    assert document.read_bytes() == old_encrypted

    applied = rotate_storage(tmp_path, dry_run=False)
    assert applied == {"scanned": 1, "rotated": 1, "unchanged": 0, "errors": 0}
    new_payload = document.read_bytes()
    assert get_payload_key_id(new_payload) == get_storage_key_id(new_key)
    assert decrypt_bytes(new_payload, key=new_key, strict=True) == plaintext

    repeat = rotate_storage(tmp_path, dry_run=False)
    assert repeat == {"scanned": 1, "rotated": 0, "unchanged": 1, "errors": 0}
    assert Path(document).read_bytes() == new_payload


def test_v1_storage_payload_remains_decryptable():
    key = b"legacy-v1-key-for-test-only-00000"[:32]
    nonce = os.urandom(12)
    plaintext = b"legacy encrypted content"
    payload = MAGIC_HEADER + nonce + AESGCM(key).encrypt(nonce, plaintext, MAGIC_HEADER)
    assert decrypt_bytes(payload, key=key, strict=True) == plaintext
