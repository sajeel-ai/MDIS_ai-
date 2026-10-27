"""Migration script: encrypt unencrypted files in storage at rest using AES-256-GCM.

Usage:
    python backend/scripts/migrate_storage_encryption.py [--dry-run] [--verify-only] [--storage-dir DIR]
"""

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.security.storage_crypto import (
    MAGIC_HEADER,
    decrypt_bytes,
    encrypt_bytes,
    get_storage_encryption_key,
    is_encrypted,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_storage_encryption")


def migrate_storage(storage_dir: Path, dry_run: bool = False, verify_only: bool = False) -> int:
    """Scan and encrypt files at rest using AES-256-GCM."""
    if not storage_dir.exists():
        logger.warning("Storage directory does not exist: %s", storage_dir)
        return 0

    key = get_storage_encryption_key()
    logger.info("Starting storage encryption migration in: %s", storage_dir)
    logger.info("Active encryption key verified (%d bytes). Mode: dry_run=%s, verify_only=%s", len(key), dry_run, verify_only)

    total_files = 0
    already_encrypted = 0
    newly_encrypted = 0
    errors = 0

    for root, _, files in os.walk(storage_dir):
        for filename in files:
            # Skip temporary upload files
            if filename.startswith("upload-") or filename.endswith(".tmp"):
                continue

            file_path = Path(root) / filename
            total_files += 1

            try:
                with open(file_path, "rb") as f:
                    content = f.read()

                if is_encrypted(content):
                    already_encrypted += 1
                    if verify_only:
                        # Ensure decrypts cleanly
                        decrypt_bytes(content, key=key, strict=True)
                        logger.debug("Verified encrypted file: %s", file_path)
                else:
                    if verify_only:
                        logger.warning("Found UNENCRYPTED file: %s", file_path)
                        continue

                    if dry_run:
                        logger.info("[DRY RUN] Would encrypt file: %s (%d bytes)", file_path, len(content))
                        newly_encrypted += 1
                    else:
                        encrypted = encrypt_bytes(content, key=key)
                        # Atomic write to temporary file then replace
                        temp_dest = file_path.with_suffix(file_path.suffix + ".enc_tmp")
                        with open(temp_dest, "wb") as f_tmp:
                            f_tmp.write(encrypted)

                        # Verify before replacing
                        with open(temp_dest, "rb") as f_verify:
                            verified_plain = decrypt_bytes(f_verify.read(), key=key, strict=True)
                            assert verified_plain == content, "Verification check failed for re-encrypted bytes"

                        temp_dest.replace(file_path)
                        logger.info("Encrypted and verified: %s (%d -> %d bytes)", file_path, len(content), len(encrypted))
                        newly_encrypted += 1

            except Exception as exc:
                logger.error("Error processing %s: %s", file_path, exc)
                errors += 1

    logger.info(
        "Migration summary: Total=%d, Newly Encrypted=%d, Already Encrypted=%d, Errors=%d",
        total_files,
        newly_encrypted,
        already_encrypted,
        errors,
    )
    return 1 if errors > 0 else 0


def main():
    parser = argparse.ArgumentParser(description="Encrypt stored MDIS documents using AES-256-GCM.")
    parser.add_argument("--storage-dir", type=str, default=None, help="Target storage directory (defaults to configured storage_local_path)")
    parser.add_argument("--dry-run", action="store_true", help="Report files to encrypt without modifying them")
    parser.add_argument("--verify-only", action="store_true", help="Verify that existing encrypted files can be decrypted")

    args = parser.parse_args()
    target_dir = Path(args.storage_dir) if args.storage_dir else Path(settings.storage_local_path).resolve()
    exit_code = migrate_storage(target_dir, dry_run=args.dry_run, verify_only=args.verify_only)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

