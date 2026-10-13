# MDIS verification audit (read-only)

Generated from the current working tree. No application, test, fixture, or ground-truth files were changed by this audit.

## Frozen scorer: 84-entity fixture pack

| Document | Category | Strict P/R/F1 | Lenient P/R/F1 | Method |
|---|---|---:|---:|---|
| DOC-001 | diagnosis | 0.667/0.4/0.5 | 1.0/0.6/0.75 | text_layer |
| DOC-001 | symptom | 0.8/1.0/0.889 | 0.8/1.0/0.889 | text_layer |
| DOC-001 | medication | 1.0/0.667/0.8 | 1.0/0.667/0.8 | text_layer |
| DOC-001 | lab | 0.0/0.0/0.0 | 0.5/1.0/0.667 | text_layer |
| DOC-001 | vital | 1.0/1.0/1.0 | 1.0/1.0/1.0 | text_layer |
| DOC-001 | allergy | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-002 | diagnosis | 0.5/0.125/0.2 | 1.0/0.25/0.4 | text_layer |
| DOC-002 | symptom | 0.333/0.333/0.333 | 0.667/0.667/0.667 | text_layer |
| DOC-002 | medication | 1.0/0.75/0.857 | 1.0/0.75/0.857 | text_layer |
| DOC-002 | lab | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-002 | vital | 1.0/1.0/1.0 | 1.0/1.0/1.0 | text_layer |
| DOC-002 | allergy | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-003 | diagnosis | 0.0/0.0/0.0 | 0.0/0.0/0.0 | text_layer |
| DOC-003 | symptom | 1.0/0.5/0.667 | 1.0/0.5/0.667 | text_layer |
| DOC-003 | medication | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-003 | lab | 0.0/0.0/0.0 | 1.0/0.167/0.286 | text_layer |
| DOC-003 | vital | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-003 | allergy | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-004 | diagnosis | 0.333/0.333/0.333 | 0.667/0.667/0.667 | text_layer |
| DOC-004 | symptom | 1.0/1.0/1.0 | 1.0/1.0/1.0 | text_layer |
| DOC-004 | medication | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-004 | lab | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-004 | vital | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-004 | allergy | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-005 | diagnosis | 0.5/0.333/0.4 | 1.0/0.667/0.8 | text_layer |
| DOC-005 | symptom | 0.0/0.0/0.0 | 0.0/0.0/0.0 | text_layer |
| DOC-005 | medication | 1.0/0.25/0.4 | 1.0/0.25/0.4 | text_layer |
| DOC-005 | lab | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-005 | vital | n/a/n/a/n/a | n/a/n/a/n/a | text_layer |
| DOC-005 | allergy | 0.0/0.0/0.0 | 0.0/0.0/0.0 | text_layer |
| DOC-006 | diagnosis | 0.5/0.333/0.4 | 0.5/0.333/0.4 | text_layer,text_layer |
| DOC-006 | symptom | 0.533/0.667/0.593 | 0.533/0.667/0.593 | text_layer,text_layer |
| DOC-006 | medication | 1.0/0.5/0.667 | 1.0/0.5/0.667 | text_layer,text_layer |
| DOC-006 | lab | 0.0/0.0/0.0 | 0.0/0.0/0.0 | text_layer,text_layer |
| DOC-006 | vital | 1.0/1.0/1.0 | 1.0/1.0/1.0 | text_layer,text_layer |
| DOC-006 | allergy | 0.0/0.0/0.0 | 0.0/0.0/0.0 | text_layer,text_layer |

### Overall strict

| Category | Precision | Recall | F1 |
|---|---:|---:|---:|
| diagnosis | 0.5 | 0.25 | 0.333 |
| symptom | 0.615 | 0.593 | 0.604 |
| medication | 1.0 | 0.538 | 0.7 |
| lab | 0.0 | 0.0 | 0.0 |
| vital | 1.0 | 1.0 | 1.0 |
| allergy | 0.0 | 0.0 | 0.0 |

### Overall lenient

| Category | Precision | Recall | F1 |
|---|---:|---:|---:|
| diagnosis | 0.833 | 0.417 | 0.556 |
| symptom | 0.654 | 0.63 | 0.642 |
| medication | 1.0 | 0.538 | 0.7 |
| lab | 0.4 | 0.286 | 0.333 |
| vital | 1.0 | 1.0 | 1.0 |
| allergy | 0.0 | 0.0 | 0.0 |

Assertion accuracy: 40/44.
Code accuracy: 21/46; any-system 21/29.
Dangerous errors: 0.

## Requirement status

| # | Requirement | Status | Evidence |
|---:|---|---|---|
| A1 | Vitals in sentences, abbreviations, tables | FAIL | `local.py:234-242` extracts sentence forms. BP, Blood Pressure-over, B/P, and T/HR/RR/SpO2 produced real vital output. The requested multi-row table raises IndexError in `_add_vital_entities` because the second BP regex has two groups while code reads group 3. |
| A2 | Unextracted vital mention flagged | NOT IMPLEMENTED | No missing-vital warning path found. |
| A3 | Bullet/sentence symptom lists | PARTIAL | Vocabulary extraction exists; no complete dedicated bullet-list measurement was found. |
| A4 | Denied symptoms and conditional advice | PARTIAL | Advice example produced no entity; generalized assertion/pain code exists. Complete requested-form test evidence is missing. |
| A5 | Main diagnosis as documented | NOT IMPLEMENTED | No main-diagnosis field or selection rule found. |
| A6 | Per-page OCR method and image accuracy | PARTIAL | Frozen scorer reports text_layer for digital fixtures. Held-out images exist but cannot be scored because no held-out ground_truth.json exists. |
| A7 | Accuracy and 99% targets | FAIL | Measured fixture F1 is below 99%; full table above. Held-out scoring is blocked by missing ground_truth.json. |
| B8 | Extract/Re-extract shared status function | FAIL | Documents uses inline status branching and `window.confirm` (`src/pages/Documents.tsx:123-137,431-437`); no shared button function/test found. |
| B9 | Re-extract history/pending/stale FHIR | PARTIAL | Confirmation and reprocess endpoint exist; complete archived-history and stale-FHIR evidence is missing. |
| C10 | Correction API/audit/UI persistence | PARTIAL | Review correction service and audit test exist; full corrected-badge/persistence evidence is missing. |
| C11 | Present/Denied symptom groups | NOT IMPLEMENTED | No matching grouped UI/test found. |
| C12 | Main diagnosis review display | NOT IMPLEMENTED | No main-diagnosis review field found. |
| C13 | Complete server-side pre-approval checklist | PARTIAL | Some validation/confidence checks exist; complete checklist/blocking acknowledgement evidence is missing. |
| D14 | Approval and Approved Files actions | PARTIAL | Approved Files has FHIR JSON and test-push buttons; complete transition evidence is missing. |
| D15 | R4 Bundle/denied inactive/vital Observations | PARTIAL | FHIR projection tests and vital LOINC extraction exist; fresh bundle proof and denied-condition assertion were not produced. |
| D16 | Fixture-wide Playwright/equivalent | NOT IMPLEMENTED | No suite covering every fixture was found. |
| E17 | Backend/frontend engineering gates | PARTIAL | Existing logs: pytest 1 failed/216 passed/1 skipped; Vitest 15 failed/115 passed. Both UNVERIFIED. Typecheck/lint/build evidence not present in inspected logs. |
| E18 | Tests not weakened/package/scorer unchanged | FAIL | `git diff ab41747` shows many test/fixture changes, including entity-contract assertion edits. Package files have no diff and scorer diff from 3cf7225 is empty, but full test-change justification is not established. |
| E19 | Dangerous errors/nighttime frequency | PARTIAL | Frozen scorer reports 0 dangerous errors. Raw nighttime text and four forms are preserved; no normalized once-daily-at-bedtime value is stored. |

## Non-PASS items

1. Fix vital-table extraction crash and add table tests.
2. Add missing-vital warnings and pre-approval handling.
3. Add main-diagnosis selection and display.
4. Add allergy/NKDA extraction.
5. Complete lab-table parsing.
6. Complete re-extraction version history and stale FHIR.
7. Add denied-symptom grouping and checklist coverage.
8. Add fixture-wide E2E tests and rerun gates.
9. Add held-out ground_truth.json before scoring held-out documents.

## Confirmation commands

```powershell
cd "C:/Users/Meta/project z/Cognate-AI main/Cognate-AI/backend"
$env:DEBUG="false"
.env\Scripts\python.exe -m pytest tests --timeout=60 -q
cd ..
npm run typecheck
npm run lint
npm test -- --run
npm run build
```

All pytest/Vitest results from logs remain UNVERIFIED until confirmed in your terminal.
