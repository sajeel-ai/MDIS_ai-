"""Idempotently re-encrypt stored files with the configured active key.

Dry-run is the default. Configure STORAGE_ENCRYPTION_PREVIOUS_KEYS with old
keys during rotation, then run with --apply; remove retired keys only after
verification and backup retention policy approval.
"""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from app.config import settings
from app.security.storage_crypto import (
    decrypt_bytes,
    encrypt_bytes,
    get_payload_key_id,
    get_storage_encryption_key,
    get_storage_key_id,
    is_encrypted,
)


def rotate_storage(storage_dir: Path, *, dry_run: bool = True) -> dict[str, int]:
    active_key = get_storage_encryption_key()
    active_id = get_storage_key_id(active_key)
    stats = {"scanned": 0, "rotated": 0, "unchanged": 0, "errors": 0}
    if not storage_dir.exists():
        return stats

    for path in storage_dir.rglob("*"):
        if not path.is_file() or path.name.endswith((".tmp", ".enc_tmp")):
            continue
        stats["scanned"] += 1
        temp_path: Path | None = None
        try:
            original = path.read_bytes()
            if is_encrypted(original) and get_payload_key_id(original) == active_id:
                decrypt_bytes(original, key=active_key, strict=True)
                stats["unchanged"] += 1
                continue

            plaintext = decrypt_bytes(original, key=active_key, strict=is_encrypted(original))
            if dry_run:
                stats["rotated"] += 1
                continue

            rewritten = encrypt_bytes(plaintext, key=active_key)
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".rotate.tmp", delete=False
            ) as stream:
                temp_path = Path(stream.name)
                stream.write(rewritten)
                stream.flush()
                os.fsync(stream.fileno())

            verified = decrypt_bytes(temp_path.read_bytes(), key=active_key, strict=True)
            if verified != plaintext or get_payload_key_id(temp_path.read_bytes()) != active_id:
                raise ValueError("Rotated payload failed decrypt or key-id verification")
            os.replace(temp_path, path)
            temp_path = None
            stats["rotated"] += 1
        except Exception:
            stats["errors"] += 1
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-dir", type=Path, default=Path(settings.storage_local_path))
    parser.add_argument("--apply", action="store_true", help="Perform atomic re-encryption (default: dry-run)")
    args = parser.parse_args()
    dry_run = not args.apply
    stats = rotate_storage(args.storage_dir.resolve(), dry_run=dry_run)
    print(f"mode={'dry-run' if dry_run else 'apply'} {stats}")
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
