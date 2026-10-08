"""Database-backed auth throttling; bucket identifiers are irreversibly hashed."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AuthRateLimitBucket


async def enforce_auth_rate_limit(
    request: Request,
    db: AsyncSession,
    action: str,
    account_key: str | None = None,
    *,
    mfa: bool = False,
) -> None:
    """Enforce independent per-IP and per-account fixed-window counters."""
    now = datetime.now(timezone.utc)
    window_seconds = settings.auth_rate_limit_window_seconds
    if secrets.randbelow(128) == 0:
        await db.execute(delete(AuthRateLimitBucket).where(
            AuthRateLimitBucket.window_started_at < now - timedelta(seconds=window_seconds * 2)
        ))
    ip = request.client.host if request.client else "unknown"
    dimensions = [("ip", ip, settings.auth_rate_limit_per_ip)]
    if account_key:
        dimensions.append(("account", account_key.strip().casefold(), settings.auth_rate_limit_per_account))
    if mfa:
        dimensions.append(("mfa", account_key or ip, settings.auth_rate_limit_per_account))

    for dimension, value, limit in dimensions:
        material = f"{action}:{dimension}:{value}".encode()
        key_hash = hmac.new(settings.jwt_secret_key.encode(), material, hashlib.sha256).hexdigest()
        stmt = insert(AuthRateLimitBucket).values(
            key_hash=key_hash, window_started_at=now, attempts=1, blocked_until=None
        )
        expired = AuthRateLimitBucket.window_started_at < now - timedelta(seconds=window_seconds)
        stmt = stmt.on_conflict_do_update(
            index_elements=[AuthRateLimitBucket.key_hash],
            set_={
                "window_started_at": case((expired, now), else_=AuthRateLimitBucket.window_started_at),
                "attempts": case((expired, 1), else_=AuthRateLimitBucket.attempts + 1),
                "blocked_until": case((expired, None), else_=AuthRateLimitBucket.blocked_until),
            },
        )
        result = await db.execute(stmt.returning(AuthRateLimitBucket.attempts, AuthRateLimitBucket.blocked_until))
        current = result.first()
        if current is None:
            row = await db.get(AuthRateLimitBucket, key_hash)
            attempts = row.attempts if row else limit + 1
            blocked_until = row.blocked_until if row else now
        else:
            attempts, blocked_until = current
        if attempts > limit or (blocked_until and blocked_until > now):
            if attempts > limit and not blocked_until:
                await db.execute(
                    insert(AuthRateLimitBucket)
                    .values(key_hash=key_hash, window_started_at=now, attempts=attempts, blocked_until=now + timedelta(seconds=window_seconds))
                    .on_conflict_do_update(
                        index_elements=[AuthRateLimitBucket.key_hash],
                        set_={"attempts": attempts, "blocked_until": now + timedelta(seconds=window_seconds)},
                    )
                )
            await db.commit()
            raise HTTPException(status_code=429, detail="Too many authentication attempts. Try again later.", headers={"Retry-After": str(window_seconds)})
    await db.commit()
