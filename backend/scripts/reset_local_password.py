"""Reset an existing account password from a local development shell only."""

from __future__ import annotations

import asyncio
import getpass
import os
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import RefreshToken, User
from app.security.auth import hash_password, validate_password_policy
from app.services.audit_service import record_audit_event


def require_development() -> None:
    app_env = settings.app_env.strip().lower()
    environment = (settings.environment or os.getenv("ENVIRONMENT", "")).strip().lower()
    if app_env != "development" or environment not in {"", "development"}:
        raise RuntimeError("Local password reset is available only in development")


async def reset_existing_account(email: str, password: str) -> bool:
    normalized_email = email.strip().lower()
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == normalized_email))
        if user is None:
            return False

        validate_password_policy(
            password,
            email=normalized_email,
            full_name=user.display_name or "",
        )
        now = datetime.now(timezone.utc)
        user.password_hash = hash_password(password)
        user.password_changed_at = now
        user.failed_login_count = 0
        user.locked_until = None
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await record_audit_event(
            session,
            action="PASSWORD_CHANGED",
            user_id=user.id,
            organization_id=user.organization_id,
        )
        await session.commit()
        return True


def main() -> int:
    try:
        require_development()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    email = input("Account email: ").strip().lower()
    password = getpass.getpass("New password: ")
    confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    try:
        updated = asyncio.run(reset_existing_account(email, password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not updated:
        raise SystemExit("No matching account was found")
    print("Password updated. Existing sessions have been revoked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
