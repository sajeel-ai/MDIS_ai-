"""Create local development admin/operator accounts from environment variables."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Organization, User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.security.auth import hash_password, validate_password_policy, verify_password

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SeedCredential:
    email: str
    password: str
    role: UserRole
    display_name: str


def require_development_environment(
    environment: str | None = None,
    app_environment: str | None = None,
) -> None:
    """Prevent dev credentials from being seeded into production or shared envs."""
    configured_environment = (environment or app_environment or "").strip().lower()
    configured_app_environment = (app_environment or "").strip().lower()
    if configured_environment == "production" or configured_app_environment == "production":
        raise RuntimeError("Refusing to seed development users in production")
    if configured_app_environment != "development":
        raise RuntimeError("Development users may only be seeded when APP_ENV=development")


def read_credentials(environ: Mapping[str, str] | None = None) -> tuple[SeedCredential, SeedCredential]:
    environ = os.environ if environ is None else environ
    credentials = (
        SeedCredential(
            email=environ.get("COGNATE_DEV_ADMIN_EMAIL", "").strip().lower(),
            password=environ.get("COGNATE_DEV_ADMIN_PASSWORD", ""),
            role=UserRole.ADMIN,
            display_name="Local Development Admin",
        ),
        SeedCredential(
            email=environ.get("COGNATE_DEV_OPERATOR_EMAIL", "").strip().lower(),
            password=environ.get("COGNATE_DEV_OPERATOR_PASSWORD", ""),
            role=UserRole.OPERATOR,
            display_name="Local Development Operator",
        ),
    )
    for credential in credentials:
        if not credential.email or "@" not in credential.email:
            raise RuntimeError(f"A valid email is required for the {credential.role.value} seed user")
        if len(credential.password) < 12:
            raise RuntimeError(f"Set a {credential.role.value} seed password with at least 12 characters")
        try:
            validate_password_policy(credential.password, email=credential.email, full_name=credential.display_name)
        except ValueError as exc:
            raise RuntimeError(f"The {credential.role.value} seed password does not meet password policy") from exc
    if credentials[0].email == credentials[1].email:
        raise RuntimeError("Admin and operator seed users must have different email addresses")
    return credentials


async def ensure_seed_user(session: AsyncSession, credential: SeedCredential) -> bool:
    """Create one account, or verify a matching account without changing it."""
    result = await session.execute(
        select(User).where(func.lower(User.email) == credential.email)
    )
    existing = result.scalars().first()
    if existing is not None:
        existing_role = existing.role.value if isinstance(existing.role, UserRole) else str(existing.role)
        if (
            existing_role != credential.role.value
            or not existing.is_active
            or not verify_password(credential.password, existing.password_hash)
        ):
            raise RuntimeError(
                f"A user already exists for the configured {credential.role.value} email; "
                "no account changes were made"
            )
        return False

    session.add(
        User(
            email=credential.email,
            password_hash=hash_password(credential.password),
            display_name=credential.display_name,
            role=credential.role,
            organization_id=DEFAULT_ORGANIZATION_ID,
            is_active=True,
        )
    )
    await session.flush()
    return True


async def seed_users(credentials: tuple[SeedCredential, SeedCredential]) -> tuple[bool, bool]:
    async with AsyncSessionLocal() as session:
        organization = await session.get(Organization, DEFAULT_ORGANIZATION_ID)
        if organization is None:
            raise RuntimeError("Default organization is missing; apply database migrations first")
        try:
            created_admin = await ensure_seed_user(session, credentials[0])
            created_operator = await ensure_seed_user(session, credentials[1])
            await session.commit()
            return created_admin, created_operator
        except Exception:
            await session.rollback()
            raise


def main() -> int:
    load_dotenv(BACKEND_ROOT / ".env", override=False)
    try:
        require_development_environment(os.getenv("ENVIRONMENT") or settings.environment, settings.app_env)
        credentials = read_credentials()
        created_admin, created_operator = asyncio.run(seed_users(credentials))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    admin_state = "created" if created_admin else "already exists"
    operator_state = "created" if created_operator else "already exists"
    print(f"Local development users: admin {admin_state}; operator {operator_state}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
