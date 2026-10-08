"""Configured external integration checks and opt-in synthetic FHIR push."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.providers.fhir_server import get_fhir_server_provider
from app.security.authorization import authorize_document_access
from app.services.audit_service import record_audit_event
from app.services.fhir.fhir_service import FHIRProjectionService

router = APIRouter(prefix="/integrations/fhir", tags=["integrations"])


def ensure_synthetic_test_source(source: str) -> None:
    if source.lower() not in {"synthetic", "test"}:
        raise HTTPException(status_code=422, detail="Outbound push accepts synthetic/test documents only")


@router.get("/metadata", dependencies=[Depends(require_roles(*tuple(UserRole)))])
async def check_fhir_metadata():
    if not settings.fhir_test_server_url.strip():
        return {"configured": False, "reachable": False, "resource": None}
    try:
        metadata = await get_fhir_server_provider().get_metadata()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FHIR metadata check failed ({type(exc).__name__})") from None
    return {"configured": True, "reachable": True, "resource": metadata}


@router.post("/push/{document_id}", dependencies=[Depends(require_roles(UserRole.ADMIN))])
async def push_synthetic_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    if not settings.fhir_outbound_enabled:
        raise HTTPException(status_code=503, detail="Outbound FHIR is disabled")
    document = await authorize_document_access(document_id, current_user, db, request)
    ensure_synthetic_test_source(document.source)
    bundle = await FHIRProjectionService(db).generate_document_fhir_bundle(document_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        result = await get_fhir_server_provider().push_transaction(bundle)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    await record_audit_event(db, action="fhir_test_push", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document", resource_id=document_id)
    await db.commit()
    return {"document_id": str(document_id), **result}
