"""Reusable dependency for auditing READ access to clinical resources."""

import uuid
from typing import Callable, Optional
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import UserContext, get_current_user
from app.services.audit_service import record_audit_event


def audit_read_access(action: str, resource_type: str = "document") -> Callable:
    """Dependency factory recording an append-only audit event for every read operation.
    
    Captures:
      - user_id: ID of the authenticated user making the read request
      - resource_id: UUID extracted from path parameters (document_id, task_id, etc.)
      - action: Read action name (e.g. 'view_document', 'view_entities', 'export_fhir')
      - timestamp: Populated via server_default (AuditEvent.created_at)
      - ip_address: Client IP address extracted safely from request
    """

    async def audit_dependency(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: UserContext = Depends(get_current_user),
    ) -> None:
        resource_id_raw = (
            request.path_params.get("document_id")
            or request.path_params.get("resource_id")
            or request.path_params.get("task_id")
            or request.path_params.get("id")
        )
        resource_id: Optional[uuid.UUID] = None
        if resource_id_raw:
            try:
                resource_id = uuid.UUID(str(resource_id_raw))
            except (ValueError, TypeError):
                resource_id = None

        await record_audit_event(
            db,
            action=action,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            resource_type=resource_type,
            resource_id=resource_id,
            request=request,
        )
        await db.commit()

    return audit_dependency

