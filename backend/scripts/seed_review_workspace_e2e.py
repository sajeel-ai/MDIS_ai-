"""Create a synthetic end-to-end review workspace dataset on a *_test DB only.

Run after ``alembic upgrade head`` with DATABASE_URL and STORAGE_ENCRYPTION_KEY
set for a disposable test database. Documents are encrypted in STORAGE_PATH and
processed by the actual OCR, extraction, validation, and review workflow.
"""

from __future__ import annotations

import asyncio
import io
import os
import uuid

from sqlalchemy.engine import make_url


def _require_test_database() -> str:
    database_url = os.environ.get("DATABASE_URL", "")
    try:
        database_name = make_url(database_url).database or ""
    except Exception as exc:
        raise SystemExit("Set DATABASE_URL to a disposable PostgreSQL database ending in _test.") from exc
    if not database_name.lower().endswith("_test"):
        raise SystemExit(f"Refusing to seed database '{database_name}'; the name must end in _test.")
    if not os.environ.get("STORAGE_ENCRYPTION_KEY"):
        raise SystemExit("Set STORAGE_ENCRYPTION_KEY for the disposable test environment.")
    return database_name


DATABASE_NAME = _require_test_database()

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import pymupdf  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Document, Organization, Patient, User, UserRole  # noqa: E402
from app.providers.storage import get_storage_provider  # noqa: E402
from app.security.auth import hash_password  # noqa: E402
from app.services.processing.job_service import JobService  # noqa: E402
from app.workflows.clinical_processing import ClinicalProcessingWorkflow  # noqa: E402


def _synthetic_documents() -> list[tuple[str, str, bytes]]:
    typed = (
        "PROGRESS NOTE\nHPI: Patient reports cough and fever.\n"
        "ASSESSMENT: Asthma.\nPLAN: Return if fever persists.\n"
    ).encode("utf-8")

    image = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=42)
    draw.text((150, 300), "SYNTHETIC PROGRESS NOTE", fill="black", font=font)
    draw.text((150, 390), "Cough and asthma", fill="black", font=font)
    image = image.rotate(7, expand=True, fillcolor="white")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")

    pdf = pymupdf.open()
    page = pdf.new_page(width=612, height=792)
    page.insert_text((42, 50), "SYNTHETIC TWO COLUMN NOTE", fontsize=12)
    page.insert_text((42, 100), "HPI: cough and fever", fontsize=11)
    page.insert_text((42, 130), "ASSESSMENT: asthma", fontsize=11)
    page.insert_text((330, 100), "PLAN: continue observation", fontsize=11)
    page.insert_text((330, 130), "FOLLOW UP: primary care", fontsize=11)
    pdf_bytes = pdf.tobytes()
    pdf.close()

    return [
        ("synthetic-typed-note.txt", "text/plain", typed),
        ("synthetic-rotated-scan.png", "image/png", image_bytes.getvalue()),
        ("synthetic-two-column.pdf", "application/pdf", pdf_bytes),
    ]


async def _seed() -> None:
    settings.extraction_provider = "mock"
    settings.ocr_provider = "local"
    test_password = os.environ.get("MDIS_TEST_PASSWORD", "Synthetic-Test-Only-42!")
    org = Organization(name=f"Synthetic Review Workspace {uuid.uuid4().hex[:8]}")
    async with AsyncSessionLocal() as db:  # type: AsyncSession
        db.add(org)
        await db.flush()
        users = [
            User(email=f"{role.value}-{uuid.uuid4().hex[:8]}@example.test", password_hash=hash_password(test_password), display_name=f"Synthetic {role.value}", role=role, organization_id=org.id, is_active=True)
            for role in (UserRole.ADMIN, UserRole.REVIEWER, UserRole.CLINICIAN, UserRole.VIEWER)
        ]
        patient = Patient(
            organization_id=org.id, external_patient_id=f"SYN-{uuid.uuid4().hex[:10]}",
            first_name="Synthetic", last_name="Patient",
        )
        db.add_all([*users, patient])
        await db.flush()
        for user in users:
            print(f"synthetic_user role={user.role.value} email={user.email}")
        storage = get_storage_provider()

        for filename, mime_type, content in _synthetic_documents():
            key = f"review-workspace-e2e/{uuid.uuid4().hex}/{filename}"
            await storage.save_file(key, content)
            document = Document(
                organization_id=org.id, patient_id=patient.id,
                document_type="progress_note", source="UserUpload",
                file_name=filename, mime_type=mime_type, size_bytes=len(content),
                storage_key=key, status="uploaded", review_status="not_required",
            )
            db.add(document)
            await db.flush()
            job_request = await JobService(db).create_and_enqueue_job(document.id)
            await db.commit()
            await ClinicalProcessingWorkflow(db).execute_job(job_request.job.id)
            await db.refresh(document)
            print(f"document_id={document.id} status={document.status} file={filename}")

        await db.commit()
    print(f"Seeded synthetic review data in {DATABASE_NAME}.")


if __name__ == "__main__":
    asyncio.run(_seed())
