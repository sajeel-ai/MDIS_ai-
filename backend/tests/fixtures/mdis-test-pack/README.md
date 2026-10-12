# MDIS Synthetic Test Pack

5 fictional clinical documents (PDF) plus `ground_truth.json` with the expected extraction result
(60 entities). Every document is marked "SYNTHETIC TEST DOCUMENT - NOT REAL PATIENT DATA".
All names, MRNs and dates are invented. Do not mix this pack with real patient files.

## Documents
| ID | Type | What it tests |
|---|---|---|
| DOC-001 | Discharge summary | diagnoses, negated symptoms (denies chest pain), family history (mother, breast cancer), medication frequencies (BID, once daily, q8h PRN), HbA1c, blood pressure, different date formats |
| DOC-002 | Cardiology progress note | abbreviation "DM2", historical condition (stent 2019), "rule out"/"possible" phrasing, negation (no asthma/COPD), discontinued drug (aspirin), "twice daily" and "at bedtime" |
| DOC-003 | Lab report (table) | table extraction, flags (L), SI unit (mmol/L) next to mg/dL, family-history trap ("mother is a Type II diabetic" must NOT go to the patient) |
| DOC-004 | Chest X-ray report | laterality (right lower lobe), negated findings (no effusion, no pneumothorax), abbreviation "T2DM", COPD |
| DOC-005 | Referral + prescription | wording variant "diabetes mellitus type II", allergy with reaction, "OD" and "bd" frequencies, mcg dose, "rule out GERD", negated symptoms |

The five spellings of Type 2 diabetes appear across the pack: "Type 2 Diabetes" (001),
"DM2" (002), "Type II diabetic" (003, family), "T2DM" (004), "diabetes mellitus type II" (005).
All present-patient mentions should normalize to the same concept (SNOMED 44054006, ICD-10 E11.9).

## How to use
1. Upload the 5 PDFs through MDIS (upload, OCR, extraction).
2. Compare the extracted entities to `ground_truth.json`, by document.
3. Score each entity as: correct, wrong value, wrong assertion, missed, or extra (not in ground truth).
4. Report per category (diagnosis, symptom, medication, lab, vital, allergy):
   precision = correct / extracted, recall = correct / expected.
5. Check these separately, because they are the most dangerous failures:
   - negated items extracted as present (e.g. "denies chest pain")
   - family history assigned to the patient (DOC-001 breast cancer, DOC-003 diabetes)
   - "rule out" / "possible" items extracted as confirmed diagnoses
   - discontinued medication listed as current
   - wrong dose, unit or frequency
6. Make harder copies: print and photograph a PDF, rotate it slightly, lower the resolution, or
   add a stamp, to test OCR quality. Keep a copy of each result.

## Notes on the ground truth
- `assertion` values: present, negated, historical, family, possible, discontinued.
- Codes (SNOMED CT, ICD-10-CM, LOINC, RxNorm) are reference values written by hand. Verify them against a
  terminology server before treating them as final. Some entities have no code on purpose.
- The matching text in `text` is how the phrase appears in the document, so you can check evidence offsets.
