"""Audit event creation with identifiers only."""

import uuid
import re
from fastapi import Request

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent


def _safe_user_agent(value: str | None) -> str | None:
    if not value:
        return None
    sanitized = re.sub(r"[\r\n\x00-\x1f\x7f]", " ", value)
    sanitized = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [redacted]", sanitized)
    sanitized = re.sub(r"(?i)(token|password|secret)=([^\s;]+)", r"\1=[redacted]", sanitized)
    sanitized = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", sanitized)
    return sanitized[:512]


async def record_audit_event(
    session: AsyncSession,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    request: Request | None = None,
) -> AuditEvent:
    if request is not None:
        ip_address = request.client.host if request.client else ip_address
        user_agent = request.headers.get("user-agent", user_agent)
        request_id = getattr(request.state, "request_id", request_id)
    event = AuditEvent(
        action=action,
        user_id=user_id,
        organization_id=organization_id,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=_safe_user_agent(user_agent),
        request_id=request_id,
        metadata_={
            "action": action,
            "resource_id": str(resource_id) if resource_id else None,
            "organization_id": str(organization_id) if organization_id else None,
        },
    )
    session.add(event)
    await session.flush()
    return event
