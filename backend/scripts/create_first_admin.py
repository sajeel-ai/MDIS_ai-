"""Provision the first administrator through an interactive one-time CLI."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Organization, User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.security.auth import hash_password, validate_jwt_configuration, validate_password_policy


async def create_first_admin(email: str, full_name: str, password: str) -> None:
    async with AsyncSessionLocal() as session:
        if await session.scalar(select(User.id).where(User.role == UserRole.ADMIN).limit(1)):
            raise RuntimeError("An administrator already exists; first-admin creation is one-time")
        if await session.get(Organization, DEFAULT_ORGANIZATION_ID) is None:
            raise RuntimeError("Default organization is missing; apply migrations first")
        user = User(
            email=email.strip().lower(),
            display_name=full_name.strip(),
            password_hash=hash_password(password),
            password_changed_at=datetime.now(timezone.utc),
            role=UserRole.ADMIN,
            organization_id=DEFAULT_ORGANIZATION_ID,
            is_active=True,
        )
        session.add(user)
        await session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-production", action="store_true", help="Also require the interactive production confirmation phrase")
    args = parser.parse_args()
    is_production = (
        os.getenv("ENVIRONMENT", "").strip().lower() == "production"
        or (settings.environment or "").strip().lower() == "production"
        or settings.app_env.strip().lower() == "production"
    )
    if is_production:
        if not args.confirm_production:
            raise SystemExit("Refusing production first-admin creation without --confirm-production")
        if input("Type CREATE FIRST ADMIN to continue: ").strip() != "CREATE FIRST ADMIN":
            raise SystemExit("Production confirmation did not match")

    email = input("Administrator email: ").strip().lower()
    full_name = input("Administrator full name: ").strip()
    password = getpass.getpass("Administrator password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords did not match")
    try:
        validate_jwt_configuration()
        validate_password_policy(password, email=email, full_name=full_name)
        asyncio.run(create_first_admin(email, full_name, password))
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print("First administrator created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
