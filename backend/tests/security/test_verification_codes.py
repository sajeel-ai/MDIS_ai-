"""Regression tests for hashed, single-use authentication codes."""

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks
from sqlalchemy import select, update
from starlette.requests import Request

from app.config import settings
from app.db import AsyncSessionLocal, engine
from app.models import AuditEvent, AuthVerificationCode, User, UserRole
from app.models.organization import DEFAULT_ORGANIZATION_ID
from app.services import verification_codes
from app.services.verification_codes import VerificationCodePurpose as Purpose
from app.security.auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_between_test_loops():
    await engine.dispose(close=False)
    yield
    await engine.dispose(close=False)


def request_context(ip: str | None = None) -> Request:
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/auth/codes",
        "raw_path": b"/auth/codes",
        "query_string": b"",
        "headers": [],
        "client": (ip or "192.0.2.11", 4567),
        "server": ("test", 80),
    })


async def make_user(*, active: bool = True, pending_approval: bool = False, mfa_enabled: bool = False) -> User:
    user = User(
        email=f"code-{uuid.uuid4()}@example.test",
        display_name="Synthetic Code User",
        password_hash=hash_password("synthetic verification password 44!"),
        role=UserRole.CLINICIAN,
        organization_id=DEFAULT_ORGANIZATION_ID,
        is_active=active,
        pending_approval=pending_approval,
        email_verified=active,
        registration_status="approved" if active else "pending_email_verification",
        mfa_enabled=mfa_enabled,
    )
    async with AsyncSessionLocal() as db:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def request_code(user: User, purpose: Purpose, monkeypatch, *, now_ip: str | None = None) -> list[str]:
    delivered: list[str] = []

    async def capture(_email: str, _purpose: str, code: str):
        delivered.append(code)
        return True

    monkeypatch.setattr(verification_codes, "email_delivery_available", lambda: True)
    monkeypatch.setattr(verification_codes, "send_verification_code", capture)
    background = BackgroundTasks()
    async with AsyncSessionLocal() as db:
        await verification_codes.request_verification_code(
            db, request_context(now_ip), background, user.email, purpose
        )
    for task in background.tasks:
        await task.func(*task.args, **task.kwargs)
    return delivered


@pytest.mark.asyncio
async def test_codes_are_six_digit_hashed_expiring_single_use_and_audited(monkeypatch, caplog):
    user = await make_user(active=False, pending_approval=True)
    delivered = await request_code(user, Purpose.VERIFY_EMAIL, monkeypatch)
    assert len(delivered) == 1
    code = delivered[0]
    assert re.fullmatch(r"\d{6}", code)
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(AuthVerificationCode).where(AuthVerificationCode.user_id == user.id))
        event = await db.scalar(select(AuditEvent).where(AuditEvent.user_id == user.id, AuditEvent.action == "CODE_REQUESTED"))
        assert row is not None and row.code_hash != code and len(row.code_hash) == 64
        assert row.expires_at - row.created_at <= timedelta(minutes=10, seconds=2)
        assert event is not None and code not in str(event.metadata_)
        assert code not in (event.user_agent or "")
        assert await verification_codes.verify_verification_code(db, request_context(), user.email, Purpose.VERIFY_EMAIL, code)
        assert not await verification_codes.verify_verification_code(db, request_context(), user.email, Purpose.VERIFY_EMAIL, code)
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(AuthVerificationCode).where(AuthVerificationCode.user_id == user.id))
        event = await db.scalar(select(AuditEvent).where(AuditEvent.user_id == user.id, AuditEvent.action == "CODE_VERIFIED"))
        assert row is not None and row.is_used
        assert event is not None and code not in str(event.metadata_)
        assert code not in caplog.text


@pytest.mark.asyncio
async def test_fifth_wrong_attempt_locks_code_and_emits_failure_events(monkeypatch):
    user = await make_user()
    monkeypatch.setattr(verification_codes.secrets, "randbelow", lambda _maximum: 123456)
    delivered = await request_code(user, Purpose.RESET_PASSWORD, monkeypatch)
    assert delivered == ["123456"]
    for _ in range(settings.email_code_max_attempts):
        async with AsyncSessionLocal() as db:
            assert not await verification_codes.verify_verification_code(
                db, request_context(), user.email, Purpose.RESET_PASSWORD, "654321"
            )
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(AuthVerificationCode).where(AuthVerificationCode.user_id == user.id))
        actions = list((await db.scalars(select(AuditEvent.action).where(AuditEvent.user_id == user.id))).all())
        assert row is not None and row.attempts == settings.email_code_max_attempts and row.invalidated_at is not None
        assert "CODE_LOCKED" in actions and actions.count("CODE_FAILED") == settings.email_code_max_attempts
        assert not await verification_codes.verify_verification_code(
            db, request_context(), user.email, Purpose.RESET_PASSWORD, "123456"
        )


@pytest.mark.asyncio
async def test_resend_cooldown_daily_cap_and_replacement_invalidate_old_code(monkeypatch):
    user = await make_user()
    monkeypatch.setattr(settings, "email_code_daily_limit", 2)
    monkeypatch.setattr(settings, "email_code_cooldown_seconds", 60)
    first = await request_code(user, Purpose.RESET_PASSWORD, monkeypatch)
    assert len(first) == 1
    assert await request_code(user, Purpose.RESET_PASSWORD, monkeypatch) == []
    async with AsyncSessionLocal() as db:
        await db.execute(update(AuthVerificationCode).where(AuthVerificationCode.user_id == user.id).values(created_at=datetime.now(timezone.utc) - timedelta(seconds=61)))
        await db.commit()
    second = await request_code(user, Purpose.RESET_PASSWORD, monkeypatch)
    assert len(second) == 1
    async with AsyncSessionLocal() as db:
        rows = list((await db.scalars(select(AuthVerificationCode).where(AuthVerificationCode.user_id == user.id).order_by(AuthVerificationCode.created_at))).all())
        assert len(rows) == 2
        assert rows[0].invalidated_at is not None and rows[1].invalidated_at is None
        await db.execute(update(AuthVerificationCode).where(AuthVerificationCode.id == rows[1].id).values(created_at=datetime.now(timezone.utc) - timedelta(seconds=61)))
        await db.commit()
    third = await request_code(user, Purpose.RESET_PASSWORD, monkeypatch)
    assert third == []
    async with AsyncSessionLocal() as db:
        count = await db.scalar(select(AuthVerificationCode.id).where(AuthVerificationCode.user_id == user.id))
        rows = list((await db.scalars(select(AuthVerificationCode).where(AuthVerificationCode.user_id == user.id))).all())
        assert count is not None and len(rows) == 2


@pytest.mark.asyncio
async def test_expired_or_unknown_code_fails_without_email_disclosure(monkeypatch):
    user = await make_user()
    delivered = await request_code(user, Purpose.RESET_PASSWORD, monkeypatch)
    assert delivered
    async with AsyncSessionLocal() as db:
        await db.execute(update(AuthVerificationCode).where(AuthVerificationCode.user_id == user.id).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    async with AsyncSessionLocal() as db:
        assert not await verification_codes.verify_verification_code(db, request_context(), user.email, Purpose.RESET_PASSWORD, delivered[0])
        assert not await verification_codes.verify_verification_code(db, request_context(), "unknown@example.test", Purpose.RESET_PASSWORD, delivered[0])


@pytest.mark.asyncio
async def test_mfa_fallback_is_supported_only_for_active_mfa_user(monkeypatch):
    user = await make_user(mfa_enabled=True)
    codes = await request_code(user, Purpose.MFA_FALLBACK, monkeypatch)
    assert len(codes) == 1
    disabled = await make_user(mfa_enabled=False)
    assert await request_code(disabled, Purpose.MFA_FALLBACK, monkeypatch) == []
