"""Cognate AI — Synthetic Dataset Seeder

Populates PostgreSQL with synthetic clinical records linked to MIMIC patients/encounters.
Creates:
  Document -> DocumentVersion -> ProcessingJob -> ProcessingSteps -> Extraction -> ClinicalEntity -> EvidenceSpan -> ValidationResult -> ReviewTask -> AuditEvent

Usage:
    python3 -m scripts.seed_synthetic
"""

import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

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
)


SYNTHETIC_DOCUMENTS = [
    {
        "doc_type": "discharge_summary",
        "title": "Discharge Summary — Pneumonia & Hypertension",
        "text": (
            "DISCHARGE SUMMARY\n"
            "Admission Date: 2026-09-10 | Discharge Date: 2026-09-15\n\n"
            "CHIEF COMPLAINT: High fever, productive cough, and shortness of breath for 3 days.\n\n"
            "HISTORY OF PRESENT ILLNESS: Patient presented with high fever (38.9 C), "
            "purulent sputum, and right-sided pleuritic chest pain. Chest X-ray demonstrates right lower lobe infiltrate "
            "consistent with community-acquired pneumonia. White blood cell count elevated at 14.5 x 10^9/L.\n\n"
            "DISCHARGE DIAGNOSES:\n"
            "1. Right lower lobe pneumonia (ICD-10 J18.9)\n"
            "2. Essential hypertension (ICD-10 I10)\n"
            "3. Type 2 diabetes mellitus (ICD-10 E11.9)\n\n"
            "MEDICATIONS ON DISCHARGE:\n"
            "- Amoxicillin 500 mg PO TID for 7 days\n"
            "- Lisinopril 10 mg PO daily\n"
            "- Metformin 500 mg PO BID\n\n"
            "DISCHARGE INSTRUCTIONS: Follow up with primary care physician in 1 week. Re-evaluation if fever recurs."
        ),
        "entities": [
            {
                "type": "diagnosis",
                "raw": "Right lower lobe pneumonia",
                "normalized": "Community-acquired pneumonia",
                "code": "J18.9",
                "code_system": "ICD-10",
                "confidence": 0.96,
                "span_text": "community-acquired pneumonia",
                "start": 308,
                "end": 336,
                "page": 1,
            },
            {
                "type": "diagnosis",
                "raw": "Essential hypertension",
                "normalized": "Essential primary hypertension",
                "code": "I10",
                "code_system": "ICD-10",
                "confidence": 0.98,
                "span_text": "Essential hypertension",
                "start": 447,
                "end": 469,
                "page": 1,
            },
            {
                "type": "medication",
                "raw": "Amoxicillin 500 mg",
                "normalized": "Amoxicillin 500 mg",
                "code": "308182",
                "code_system": "RxNorm",
                "confidence": 0.95,
                "span_text": "Amoxicillin 500 mg PO TID for 7 days",
                "start": 560,
                "end": 596,
                "page": 1,
            },
            {
                "type": "symptom",
                "raw": "high fever",
                "normalized": "High fever",
                "code": "386661006",
                "code_system": "SNOMED",
                "confidence": 0.92,
                "span_text": "high fever (38.9 C)",
                "start": 196,
                "end": 215,
                "page": 1,
            },
        ],
        "validation_rules": [
            {"rule": "MEDICATION_HAS_DOSAGE", "status": "pass", "severity": "info", "message": "Amoxicillin has 500 mg dosage specified"},
            {"rule": "ENTITY_HAS_EVIDENCE", "status": "pass", "severity": "info", "message": "All extracted entities have ground truth evidence spans"},
            {"rule": "CONFIDENCE_ABOVE_THRESHOLD", "status": "pass", "severity": "info", "message": "Average entity confidence is 0.95 (threshold 0.85)"},
        ],
        "review_status": "approved",
    },
    {
        "doc_type": "progress_note",
        "title": "Progress Note — Angina Evaluation",
        "text": (
            "PROGRESS NOTE\n"
            "Date: 2026-09-18\n\n"
            "SUBJECTIVE: Patient reports persistent retrosternal chest tightness with exertion. "
            "Denies diaphoresis or radiation to jaw. Takes Atorvastatin intermittently.\n\n"
            "OBJECTIVE: BP 142/88 mmHg, HR 76 bpm. ECG shows normal sinus rhythm without ST elevation. "
            "Troponin T levels normal (<0.01 ng/mL).\n\n"
            "ASSESSMENT:\n"
            "1. Stable angina pectoris (ICD-10 I20.8)\n"
            "2. Hyperlipidemia (ICD-10 E78.5)\n\n"
            "PLAN: Increase Atorvastatin to 40 mg PO daily. Refer for outpatient stress echocardiogram."
        ),
        "entities": [
            {
                "type": "diagnosis",
                "raw": "Stable angina pectoris",
                "normalized": "Angina pectoris",
                "code": "I20.8",
                "code_system": "ICD-10",
                "confidence": 0.88,
                "span_text": "Stable angina pectoris",
                "start": 304,
                "end": 326,
                "page": 1,
            },
            {
                "type": "medication",
                "raw": "Atorvastatin",
                "normalized": "Atorvastatin 40 mg",
                "code": "83367",
                "code_system": "RxNorm",
                "confidence": 0.72,
                "span_text": "Takes Atorvastatin intermittently",
                "start": 153,
                "end": 186,
                "page": 1,
            },
        ],
        "validation_rules": [
            {"rule": "MEDICATION_HAS_DOSAGE", "status": "warning", "severity": "warning", "message": "Initial medication mentions Atorvastatin without dosage in HPI"},
            {"rule": "CONFIDENCE_ABOVE_THRESHOLD", "status": "warning", "severity": "warning", "message": "Atorvastatin confidence (0.72) below auto-approval threshold (0.85)"},
        ],
        "review_status": "pending",
    },
    {
        "doc_type": "consultation_report",
        "title": "Endocrinology Consult Note",
        "text": (
            "ENDOCRINOLOGY CONSULTATION\n"
            "Date: 2026-09-20\n\n"
            "REASON FOR CONSULTATION: Evaluation of poorly controlled Type 1 Diabetes Mellitus.\n"
            "HBA1C: 9.4% (elevated). Patient reports frequent nocturnal hypoglycemia.\n\n"
            "IMPRESSION: Type 1 diabetes mellitus with ketoacidosis risk.\n"
            "RECOMMENDATION: Initiate Insulin Glargine 18 units SC at bedtime, Insulin Lispro 5 units SC before meals."
        ),
        "entities": [
            {
                "type": "diagnosis",
                "raw": "Type 1 Diabetes Mellitus",
                "normalized": "Type 1 diabetes mellitus",
                "code": "E10.9",
                "code_system": "ICD-10",
                "confidence": 0.97,
                "span_text": "Type 1 Diabetes Mellitus",
                "start": 98,
                "end": 122,
                "page": 1,
            },
            {
                "type": "medication",
                "raw": "Insulin Glargine",
                "normalized": "Insulin Glargine 18 units",
                "code": "274332",
                "code_system": "RxNorm",
                "confidence": 0.94,
                "span_text": "Insulin Glargine 18 units SC at bedtime",
                "start": 272,
                "end": 311,
                "page": 1,
            },
        ],
        "validation_rules": [
            {"rule": "MEDICATION_HAS_DOSAGE", "status": "pass", "severity": "info", "message": "Insulin Glargine dosage 18 units specified"},
            {"rule": "CONFIDENCE_ABOVE_THRESHOLD", "status": "pass", "severity": "info", "message": "Confidence values above 0.85"},
        ],
        "review_status": "approved",
    },
    {
        "doc_type": "radiology_report",
        "title": "Chest CT Radiology Report",
        "text": (
            "CHEST CT WITH IV CONTRAST\n"
            "Date: 2026-09-21\n\n"
            "FINDINGS: 2.4 cm spiculated solitary pulmonary nodule in the right upper lobe. "
            "No mediastinal lymphadenopathy. Mild centrilobular emphysema.\n\n"
            "IMPRESSION: Suspicious right upper lobe pulmonary nodule (Fleischner Criteria high risk). PET-CT recommended."
        ),
        "entities": [
            {
                "type": "diagnosis",
                "raw": "solitary pulmonary nodule",
                "normalized": "Solitary pulmonary nodule",
                "code": "R91.1",
                "code_system": "ICD-10",
                "confidence": 0.91,
                "span_text": "2.4 cm spiculated solitary pulmonary nodule in the right upper lobe",
                "start": 54,
                "end": 121,
                "page": 1,
            },
            {
                "type": "diagnosis",
                "raw": "centrilobular emphysema",
                "normalized": "Centrilobular emphysema",
                "code": "J43.2",
                "code_system": "ICD-10",
                "confidence": 0.89,
                "span_text": "Mild centrilobular emphysema",
                "start": 156,
                "end": 184,
                "page": 1,
            },
        ],
        "validation_rules": [
            {"rule": "EVIDENCE_HAS_EXACT_MATCH", "status": "pass", "severity": "info", "message": "Nodule measurements match source text"},
            {"rule": "REVIEW_ROUTING_REQUIRED", "status": "pass", "severity": "info", "message": "High risk radiology finding routed to reviewer"},
        ],
        "review_status": "in_review",
    },
    {
        "doc_type": "emergency_note",
        "title": "Emergency Department Assessment",
        "text": (
            "EMERGENCY DEPARTMENT NOTE\n"
            "Date: 2026-09-22\n\n"
            "CHIEF COMPLAINT: Right lower quadrant abdominal pain, nausea, and anorexia.\n"
            "PHYSICAL EXAM: McBurney point tenderness, positive Rovsing sign. Low grade fever 37.8 C.\n"
            "LABS: WBC 16.2 x 10^9/L. Ultrasound confirms non-compressible 8 mm appendix.\n\n"
            "DIAGNOSIS: Acute appendicitis without perforation (ICD-10 K35.80).\n"
            "PLAN: Emergency laparoscopic appendectomy scheduled."
        ),
        "entities": [
            {
                "type": "diagnosis",
                "raw": "Acute appendicitis",
                "normalized": "Acute appendicitis",
                "code": "K35.80",
                "code_system": "ICD-10",
                "confidence": 0.99,
                "span_text": "Acute appendicitis without perforation",
                "start": 298,
                "end": 336,
                "page": 1,
            },
            {
                "type": "procedure",
                "raw": "laparoscopic appendectomy",
                "normalized": "Laparoscopic appendectomy",
                "code": "47562",
                "code_system": "CPT",
                "confidence": 0.96,
                "span_text": "Emergency laparoscopic appendectomy scheduled",
                "start": 361,
                "end": 406,
                "page": 1,
            },
        ],
        "validation_rules": [
            {"rule": "PROCEDURE_SCHEDULED_VALID", "status": "pass", "severity": "info", "message": "Appendectomy mapped to CPT/SNOMED"},
            {"rule": "CONFIDENCE_ABOVE_THRESHOLD", "status": "pass", "severity": "info", "message": "Confidence 0.98 >= 0.85"},
        ],
        "review_status": "approved",
    },
]


async def seed_synthetic_data():
    print("🌱 Seeding Cognate AI synthetic dataset linked to PostgreSQL patients/encounters...")
    async with AsyncSessionLocal() as session:
        # Create default clinician user for review tasks / audit events
        u_res = await session.execute(select(User).where(User.email == "dr.smith@cognate.ai"))
        user = u_res.scalars().first()
        if not user:
            user = User(
                email="dr.smith@cognate.ai",
                display_name="Dr. Sarah Smith",
                role="clinician",
            )
            session.add(user)
            await session.flush()

        # Fetch existing MIMIC patients
        p_res = await session.execute(select(Patient).limit(10))
        patients = p_res.scalars().all()
        if not patients:
            print("⚠️ No patients found in database. Create MIMIC patient first.")
            return

        for idx, doc_spec in enumerate(SYNTHETIC_DOCUMENTS):
            patient = patients[idx % len(patients)]

            # Fetch or create encounter for patient
            e_res = await session.execute(
                select(Encounter).where(Encounter.patient_id == patient.id)
            )
            encounter = e_res.scalars().first()
            if not encounter:
                encounter = Encounter(
                    patient_id=patient.id,
                    external_encounter_id=f"2900{idx}00",
                    admit_time=datetime.now(timezone.utc) - timedelta(days=10 - idx),
                    discharge_time=datetime.now(timezone.utc) - timedelta(days=5 - idx),
                    los_hours=120.0,
                )
                session.add(encounter)
                await session.flush()

            # 1. Document
            doc = Document(
                patient_id=patient.id,
                encounter_id=encounter.id,
                document_type=doc_spec["doc_type"],
                source="synthetic",
                file_name=f"synth_{doc_spec['doc_type']}_{idx+1}.txt",
                mime_type="text/plain",
                size_bytes=len(doc_spec["text"].encode("utf-8")),
                storage_key=f"local:documents/{patient.id}/{doc_spec['doc_type']}_{idx+1}.txt",
                status="completed",
                review_status=doc_spec["review_status"],
            )
            session.add(doc)
            await session.flush()

            # 2. Document Version
            raw_text = doc_spec["text"]
            text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            doc_version = DocumentVersion(
                document_id=doc.id,
                version_number=1,
                raw_text=raw_text,
                text_hash=text_hash,
                page_count=1,
            )
            session.add(doc_version)
            await session.flush()

            # 3. Processing Job
            job = ProcessingJob(
                document_id=doc.id,
                pipeline_version="v1.4.2",
                status="completed",
                started_at=datetime.now(timezone.utc) - timedelta(minutes=15),
                completed_at=datetime.now(timezone.utc) - timedelta(minutes=14),
                processing_ms=1240,
            )
            session.add(job)
            await session.flush()

            # 4. Processing Steps
            steps = [
                ("upload_validation", 50),
                ("ocr", 120),
                ("text_normalization", 60),
                ("clinical_extraction", 500),
                ("entity_normalization", 120),
                ("evidence_linking", 80),
                ("validation", 100),
                ("review_routing", 50),
            ]
            for step_name, ms in steps:
                step = ProcessingStep(
                    processing_job_id=job.id,
                    step_name=step_name,
                    status="completed",
                    processing_ms=ms,
                    model_version="mock-v1.0",
                )
                session.add(step)

            # 5. Extraction
            extraction = Extraction(
                document_id=doc.id,
                processing_job_id=job.id,
                model_name="mock_clinical_extractor",
                model_version="v1.0",
                status="completed",
            )
            session.add(extraction)
            await session.flush()

            # 6. Clinical Entities & Evidence Spans
            first_entity = None
            for ent_data in doc_spec["entities"]:
                conf = float(ent_data["confidence"])
                entity = ClinicalEntity(
                    extraction_id=extraction.id,
                    entity_type=ent_data["type"],
                    raw_text=ent_data["raw"],
                    normalized_value=ent_data["normalized"],
                    confidence=conf,
                    status="approved" if doc_spec["review_status"] == "approved" else "unreviewed",
                    details={
                        "code": ent_data["code"],
                        "code_system": ent_data["code_system"],
                    },
                )
                session.add(entity)
                await session.flush()

                if not first_entity:
                    first_entity = entity

                span = EvidenceSpan(
                    entity_id=entity.id,
                    document_version_id=doc_version.id,
                    page_number=ent_data["page"],
                    start_offset=ent_data["start"],
                    end_offset=ent_data["end"],
                    text=ent_data["span_text"],
                )
                session.add(span)

            # 7. Validation Results
            for val_rule in doc_spec["validation_rules"]:
                if first_entity:
                    val_res = ValidationResult(
                        entity_id=first_entity.id,
                        validation_rule=val_rule["rule"],
                        status=val_rule["status"],
                        severity=val_rule["severity"],
                        message=val_rule["message"],
                    )
                    session.add(val_res)

            # 8. Review Task
            review_task = ReviewTask(
                document_id=doc.id,
                entity_id=first_entity.id if first_entity else None,
                assigned_to=user.id,
                status=doc_spec["review_status"],
                priority="high" if doc_spec["review_status"] == "pending" else "normal",
                reason=f"Synthetic review task for {doc_spec['title']}",
            )
            session.add(review_task)
            await session.flush()

            # 9. Audit Event
            audit = AuditEvent(
                user_id=user.id,
                action="DOCUMENT_PROCESSED",
                resource_type="document",
                resource_id=doc.id,
                metadata_={"details": f"Synthetic document processing completed for document {doc.id}"},
            )
            session.add(audit)

        await session.commit()
        print("✅ Synthetic clinical document pipeline successfully seeded into PostgreSQL!")


if __name__ == "__main__":
    asyncio.run(seed_synthetic_data())
