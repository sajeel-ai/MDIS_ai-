from sqlalchemy.dialects import postgresql
from sqlalchemy import select

from app.models import ClinicalEntity, ReviewTask
from app.services.review.review_service import review_queue_ordering


def test_review_queue_orders_critical_then_low_confidence_then_oldest():
    statement = (
        select(ReviewTask.id)
        .outerjoin(ClinicalEntity, ClinicalEntity.id == ReviewTask.entity_id)
        .order_by(*review_queue_ordering())
    )
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    normalized_sql = " ".join(sql.lower().split())

    assert "case when ((exists" in normalized_sql
    assert "rule_code in ('critical', 'conflict')" in normalized_sql
    assert "clinical_entities.confidence <" in normalized_sql
    assert "clinical_entities.confidence asc nulls last" in normalized_sql
    assert "review_tasks.created_at asc" in normalized_sql
