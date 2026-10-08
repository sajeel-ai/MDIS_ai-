import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.models import User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.security.auth import hash_password, verify_password
from scripts.seed_dev_users import SeedCredential, ensure_seed_user, require_development_environment


def test_seed_refuses_production_environment():
    with pytest.raises(RuntimeError, match="production"):
        require_development_environment("production", "development")


def test_seed_requires_development_app_environment():
    with pytest.raises(RuntimeError, match="APP_ENV=development"):
        require_development_environment("staging", "staging")


@pytest.mark.asyncio
async def test_seed_creates_user_with_application_password_hash():
    session = AsyncMock()
    session.add = Mock()
    result = Mock()
    result.scalars.return_value.first.return_value = None
    session.execute.return_value = result
    credential = SeedCredential(
        email="dev-admin@example.test",
        password="synthesize-canvas-river-stone",
        role=UserRole.ADMIN,
        display_name="Local Development Admin",
    )

    created = await ensure_seed_user(session, credential)

    seeded_user = session.add.call_args.args[0]
    assert created is True
    assert seeded_user.role is UserRole.ADMIN
    assert seeded_user.organization_id == DEFAULT_ORGANIZATION_ID
    assert seeded_user.is_active is True
    assert verify_password(credential.password, seeded_user.password_hash)


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_does_not_rewrite_matching_user():
    credential = SeedCredential(
        email="dev-admin@example.test",
        password="synthesize-canvas-river-stone",
        role=UserRole.ADMIN,
        display_name="Local Development Admin",
    )
    existing = User(
        id=uuid.uuid4(),
        email=credential.email,
        password_hash=hash_password(credential.password),
        role=credential.role,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=True,
    )
    session = AsyncMock()
    result = Mock()
    result.scalars.return_value.first.return_value = existing
    session.execute.return_value = result

    created = await ensure_seed_user(session, credential)

    assert created is False
    session.add.assert_not_called()
