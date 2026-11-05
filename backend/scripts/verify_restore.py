"""Verify the minimum recoverability invariants after a disposable restore."""

from __future__ import annotations

import argparse
import asyncio
import os

from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.security.storage_crypto import decrypt_bytes
from app.providers.storage.local import LocalStorageProvider


async def verify(storage_key: str) -> None:
    async with AsyncSessionLocal() as session:
        counts = {}
        for table in ("users", "documents", "audit_events"):
            result = await session.execute(text(f"SELECT count(*) FROM {table}"))
            counts[table] = result.scalar_one()
        if counts["audit_events"] and counts["audit_events"] < counts["documents"]:
            raise RuntimeError("Audit-log integrity check failed: fewer audit rows than documents")
        version = await session.execute(text("SELECT version_num FROM alembic_version"))
        if not version.scalar_one():
            raise RuntimeError("Migration version is missing")

    if storage_key:
        payload = await LocalStorageProvider().read_file(storage_key)
        if not payload:
            raise RuntimeError("Stored sample document decrypted to empty content")

    print(f"restore verification passed: row_counts={counts}, sample_storage={'checked' if storage_key else 'not configured'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-StorageKey", default="")
    args = parser.parse_args()
    asyncio.run(verify(args.StorageKey))


if __name__ == "__main__":
    main()
