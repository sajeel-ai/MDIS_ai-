"""Cognate AI — Database Verification Script

Inspects all core PostgreSQL tables and prints count summaries and status checks.

Usage:
    python -m scripts.verify_database
"""

import asyncio
from sqlalchemy import select, func

from app.db import AsyncSessionLocal
from app.models import (
    User,
    Patient,
    Encounter,
    Document,
    DocumentVersion,
    ProcessingJob,
    ProcessingStep,
    Extraction,
    ClinicalEntity,
    EvidenceSpan,
    ValidationResult,
    ReviewTask,
    AuditEvent,
    IcdCode,
)


async def verify_database():
    print("🔍 Verifying Cognate AI database records...")
    async with AsyncSessionLocal() as session:
        tables = [
            ("users", User),
            ("patients", Patient),
            ("encounters", Encounter),
            ("documents", Document),
            ("document_versions", DocumentVersion),
            ("processing_jobs", ProcessingJob),
            ("processing_steps", ProcessingStep),
            ("extractions", Extraction),
            ("clinical_entities", ClinicalEntity),
            ("evidence_spans", EvidenceSpan),
            ("validation_results", ValidationResult),
            ("review_tasks", ReviewTask),
            ("audit_events", AuditEvent),
            ("icd_codes", IcdCode),
        ]

        print("-" * 50)
        print(f"{'Table Name':<25} | {'Record Count':<15}")
        print("-" * 50)

        total_records = 0
        for name, model in tables:
            res = await session.execute(select(func.count()).select_from(model))
            count = res.scalar() or 0
            total_records += count
            print(f"{name:<25} | {count:<15}")

        print("-" * 50)
        print(f"Total database records across all tables: {total_records}")
        print("-" * 50)


if __name__ == "__main__":
    asyncio.run(verify_database())
