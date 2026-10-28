import uuid

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import Document
from app.services.dashboard.dashboard_service import DashboardService


def test_dashboard_scope_is_tenant_bound_and_fails_closed_without_organization():
    org_id = uuid.uuid4()
    scoped = DashboardService(session=None, organization_id=org_id)
    compiled = str(select(Document.id).where(scoped._organization_scope()).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))
    assert f"documents.organization_id = '{org_id}'" in compiled

    unscoped = DashboardService(session=None)
    unscoped_sql = str(select(Document.id).where(unscoped._organization_scope()).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))
    assert "WHERE false" in unscoped_sql
