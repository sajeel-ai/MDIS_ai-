# Migration 026 patient deletion behavior

Migration 026 makes `documents.patient_id` nullable and sets its foreign key to
`ON DELETE SET NULL`. Deleting a patient therefore preserves the document row
and file while erasing its patient link. That avoids cascading document loss,
but it leaves a retained clinical document without its former patient
association; patient-scoped search, review, audit context, and FHIR export may
no longer resolve the relationship.

Options for policy review:

- **RESTRICT:** reject patient deletion while documents reference the patient.
  This preserves linkage and makes the deletion consequence explicit, but
  requires a documented archival/de-identification workflow.
- **Soft delete (recommended for review):** retain the patient row and
  identifiers with a deletion/retention state, block ordinary access, and
  preserve referential integrity for audit and retention workflows.
- **SET NULL:** retain current behavior, but accept and operationally handle
  orphaned documents and ensure downstream access/export behavior is clear.

No migration change is proposed for application without owner approval.
