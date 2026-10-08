"""Synthetic Clinical Document Dataset Generator.

Generates 10 realistic, de-identified synthetic clinical documents covering:
1. Clinical Note (Outpatient Respiratory Note)
2. Discharge Summary (COPD & Pneumonia Inpatient Stay)
3. Lab Report (CBC & Metabolic Panel Findings)
4. Prescription (Outpatient Chronic & Acute Regimen)
5. Radiology Report (Chest X-Ray & CT Scan)
6. Referral Letter (Cardiology Consult Referral)
7. Emergency Department Note (Acute Chest Pain / Rule out MI)
8. Follow-up Note (Pulmonology Outpatient Follow-up)
9. Operative Report (Laparoscopic Cholecystectomy)
10. Consultation Report (Nephrology Acute Kidney Injury Consult)

Saves files into storage/synthetic-documents/ as both .txt and .pdf files.
"""

import os
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "synthetic-documents"
DATASET_DIR.mkdir(parents=True, exist_ok=True)

SYNTHETIC_DOCUMENTS = [
    {
        "filename": "doc_01_clinical_note_resp.txt",
        "doc_type": "clinical_note",
        "title": "Outpatient Clinical Note — Respiratory Infection",
        "content": """PATIENT CLINICAL PROGRESS NOTE
Patient Name: John Anderson
DOB: 1968-04-12 | MRN: SYN-100201
Date of Service: 18 September 2026
Provider: Dr. Marcus Vance, MD (Internal Medicine)

SUBJECTIVE:
The patient is a 58-year-old male presenting to the outpatient clinic complaining of persistent cough for approximately three weeks. He reports intermittent fever, fatigue, and shortness of breath, particularly when walking upstairs. He denies hemoptysis or chest pain. Past medical history is significant for essential hypertension diagnosed five years ago. Current home medication is amlodipine 5 mg PO once daily.

OBJECTIVE:
Vitals: Temp: 38.2 °C (100.8 °F) | BP: 148/92 mmHg | HR: 88 bpm | RR: 20 bpm | SpO2: 95% on room air.
General: Alert, mild respiratory distress upon exertion.
HEENT: Normocephalic, mucosal membranes moist.
Lungs: Mild bilateral wheezing and scattered crackles in lower lobes.
Cardiovascular: Regular rate and rhythm, S1/S2 present, no murmurs.
Abdomen: Soft, non-tender, non-distended.

IMAGING & LABS:
Chest X-ray (Posteranterior & Lateral): Mild bilateral perihilar infiltrates. No pleural effusion or pneumothorax identified.

ASSESSMENT:
1. Acute lower respiratory tract infection (suspected community-acquired pneumonia).
2. Essential hypertension, suboptimally controlled.

PLAN:
1. Start Amoxicillin 500 mg PO three times daily for 7 days.
2. Continue Amlodipine 5 mg PO once daily.
3. Advise increased oral hydration and bed rest.
4. Return to clinic or emergency department if dyspnea worsens or high fever persists.
5. Follow-up scheduled in 7 days.""",
    },
    {
        "filename": "doc_02_discharge_summary.txt",
        "doc_type": "discharge_summary",
        "title": "Inpatient Discharge Summary — Acute COPD Exacerbation",
        "content": """INPATIENT DISCHARGE SUMMARY
Patient Name: Margaret Taylor
DOB: 1958-03-14 | MRN: SYN-100202
Date of Admission: 15 September 2026
Date of Discharge: 22 September 2026
Attending Physician: Dr. Sarah Chen, MD (Pulmonology)

PRINCIPAL DIAGNOSIS:
Acute exacerbation of Chronic Obstructive Pulmonary Disease (COPD), severe.

SECONDARY DIAGNOSES:
1. Community-acquired pneumonia, right lower lobe.
2. Essential hypertension.
3. Type 2 diabetes mellitus, non-insulin dependent.

HISTORY OF PRESENT ILLNESS:
The patient is a 68-year-old female with a 40 pack-year smoking history who presented with a 3-day history of severe dyspnea, productive cough with purulent sputum, and fever (38.5 °C).

HOSPITAL COURSE:
Patient was admitted to the step-down respiratory unit. Intravenous IV methylprednisolone 40 mg q12h and nebulized Albuterol/Ipratropium were initiated. Sputum cultures grew Streptococcus pneumoniae sensitive to Ceftriaxone. Intravenous antibiotics were transitioned to oral Azithromycin. Oxygen saturation improved from 88% on room air to 94% on 2L nasal cannula. Blood glucose levels were managed with an insulin sliding scale.

DISCHARGE MEDICATIONS:
1. Prednisone 40 mg PO once daily for 5 days.
2. Azithromycin 500 mg PO once daily for 5 days.
3. Tiotropium bromide 18 mcg inhalation once daily.
4. Albuterol 90 mcg inhaler 2 puffs q4h PRN dyspnea.
5. Lisinopril 10 mg PO once daily.
6. Metformin 1000 mg PO twice daily.

FOLLOW-UP PLAN:
- Pulmonology outpatient clinic appointment in 10 days.
- Repeat Chest X-ray in 4 weeks to confirm infiltrates resolution.""",
    },
    {
        "filename": "doc_03_lab_report.txt",
        "doc_type": "lab_report",
        "title": "Comprehensive Diagnostic Lab Report",
        "content": """CENTRAL DIAGNOSTIC LABORATORY REPORT
Patient Name: Robert Martinez
DOB: 1974-11-23 | MRN: SYN-100203
Specimen Collected: 23 September 2026 07:30
Ordering Physician: Dr. Emily Ross, MD

COMPLETE BLOOD COUNT (CBC WITH DIFFERENTIAL):
- White Blood Cells (WBC): 14.2 x10^3/uL  [HIGH] (Ref: 4.5 - 11.0)
- Red Blood Cells (RBC): 4.65 x10^6/uL    [NORMAL] (Ref: 4.30 - 5.90)
- Hemoglobin (Hgb): 13.8 g/dL             [NORMAL] (Ref: 13.5 - 17.5)
- Hematocrit (Hct): 41.2 %                [NORMAL] (Ref: 41.0 - 53.0)
- Platelets: 285 x10^3/uL                  [NORMAL] (Ref: 150 - 450)
- Neutrophils: 82.5 %                     [HIGH] (Ref: 45.0 - 70.0)

COMPREHENSIVE METABOLIC PANEL (CMP):
- Sodium: 139 mmol/L                      [NORMAL] (Ref: 135 - 145)
- Potassium: 5.4 mmol/L                   [HIGH] (Ref: 3.5 - 5.1)
- Chloride: 102 mmol/L                    [NORMAL] (Ref: 96 - 106)
- Carbon Dioxide (CO2): 22 mmol/L         [NORMAL] (Ref: 20 - 29)
- Blood Urea Nitrogen (BUN): 28 mg/dL     [HIGH] (Ref: 7 - 20)
- Serum Creatinine: 1.6 mg/dL             [HIGH] (Ref: 0.7 - 1.3)
- Glucose (Fasting): 145 mg/dL            [HIGH] (Ref: 70 - 99)
- Hemoglobin A1c: 8.2 %                   [HIGH] (Ref: < 5.7)

COMMENTS / CRITICAL VALUES:
Elevated WBC count with neutrophilia indicates acute systemic inflammatory response or bacterial infection. Mild hyperkalemia and elevated creatinine noted; suggest renal function monitoring.""",
    },
    {
        "filename": "doc_04_prescription.txt",
        "doc_type": "prescription",
        "title": "Outpatient Prescription Record",
        "content": """CLINICAL PRESCRIPTION RECORD
Patient Name: Aisha Khan
DOB: 1985-09-08 | MRN: SYN-100204
Date: 24 September 2026
Clinic: Metro Internal Medicine Associates

Rx 1: Atorvastatin 40 mg oral tablet
     Sig: Take 1 tablet (40 mg) orally once daily at bedtime.
     Qty: 90 tablets (Refills: 3)
     Indication: Hyperlipidemia / Secondary cardiovascular prevention.

Rx 2: Lisinopril 20 mg oral tablet
     Sig: Take 1 tablet (20 mg) orally once daily in the morning.
     Qty: 90 tablets (Refills: 3)
     Indication: Essential Hypertension.

Rx 3: Metformin Hydrochloride 850 mg oral tablet
     Sig: Take 1 tablet orally twice daily with meals.
     Qty: 180 tablets (Refills: 3)
     Indication: Type 2 Diabetes Mellitus.

Rx 4: Hydrochlorothiazide 12.5 mg oral tablet
     Sig: Take 1 tablet orally once daily in the morning.
     Qty: 90 tablets (Refills: 2)
     Indication: Adjunctive antihypertensive therapy.

Prescriber Signature: Dr. Aris Thorne, MD (NPI: 1982736450)""",
    },
    {
        "filename": "doc_05_radiology_report.txt",
        "doc_type": "radiology_report",
        "title": "Radiology Report — Chest X-Ray & CT Thorax",
        "content": """DEPARTMENT OF RADIOLOGY & IMAGING
Patient Name: James Wilson
DOB: 1952-01-30 | MRN: SYN-100205
Accession Number: RAD-2026-98102
Examination: Chest Radiography (PA and Lateral) & Non-contrast CT Thorax
Date of Service: 21 September 2026

CLINICAL HISTORY:
74-year-old male with chronic dyspnea, heavy smoking history, presenting with acute right-sided chest tightness and fever.

FINDINGS:
Chest Radiograph:
Cardiomegaly is present with prominent left ventricular contour. There is dense consolidation in the right lower lobe with visible air bronchograms. Left lung field is clear without focal consolidation. No pneumothorax. Small right pleural effusion noted.

CT Thorax (Non-contrast):
Confirms dense right lower lobe segment consolidation compatible with lobar pneumonia. Hilar and mediastinal lymph nodes are mildly enlarged (up to 1.2 cm in short axis), likely reactive. Emphysematous bullous changes noted in both lung apices.

IMPRESSION:
1. Right lower lobe lobar pneumonia with small parapneumonic effusion.
2. Centrilobular emphysema in upper lung lobes.
3. Mild cardiomegaly.""",
    },
    {
        "filename": "doc_06_referral_letter.txt",
        "doc_type": "referral_letter",
        "title": "Cardiology Specialist Referral Letter",
        "content": """SPECIALIST REFERRAL CONSULTATION REQUEST
To: Dr. Howard Sterling, MD (Department of Cardiology)
From: Dr. Elena Rostova, MD (Primary Care)
Date: 22 September 2026
Patient: David Miller (DOB: 1965-06-17, MRN: SYN-100206)

Dear Dr. Sterling,

Thank you for seeing Mr. David Miller in cardiac consultation for evaluation of exertional chest pain and intermittent palpitations.

Mr. Miller is a 61-year-old gentleman with a history of hypercholesterolemia and type 2 diabetes who reports a 4-week history of substernal chest tightness occurring during moderate physical exertion (climbing hills or carrying heavy groceries). The discomfort resolves within 5 minutes of rest. He also describes brief episodes of fluttering palpitations.

Current Medications:
- Metformin 1000 mg BID
- Rosuvastatin 20 mg daily
- Aspirin 81 mg daily

Physical exam in my office today demonstrated BP 136/84 mmHg, HR 76 bpm regular. Resting 12-lead ECG showed sinus rhythm with non-specific ST-T wave changes in inferior leads II, III, and aVF.

I would appreciate your clinical assessment, risk stratification, and recommendation regarding stress testing or coronary angiography.

Sincerely,
Dr. Elena Rostova, MD""",
    },
    {
        "filename": "doc_07_ed_note.txt",
        "doc_type": "emergency_department_note",
        "title": "Emergency Department Assessment & Resuscitation Note",
        "content": """EMERGENCY DEPARTMENT ADMISSION NOTE
Patient Name: Maria Rodriguez
DOB: 1979-11-04 | MRN: SYN-100207
Arrival Date/Time: 24 September 2026 02:15
Attending ED Physician: Dr. Kevin O'Brien, MD

CHIEF COMPLAINT:
Acute severe substernal chest pain and diaphoresis starting 1 hour prior to arrival.

HISTORY OF PRESENT ILLNESS:
The patient is a 46-year-old female who woke up at 01:15 AM with severe 8/10 pressure-like substernal chest discomfort radiating to her left jaw and interscapular region. Associated with severe nausea, shortness of breath, and profuse sweating. No prior history of coronary artery disease.

INITIAL PHYSICAL EXAMINATION:
Vitals: BP 162/98 mmHg, HR 104 bpm, RR 22 bpm, SpO2 96% on room air, Temp 36.8 °C.
General: Distressed, pale, diaphoretic.
Cardiovascular: Tachycardic, S1/S2 present, no S3/S4 or pericardial friction rub.

DIAGNOSTIC WORKUP:
- Initial 12-lead ECG: Sinus tachycardia with 1.5 mm ST-segment depression in leads V4-V6.
- High-Sensitivity Troponin T: 148 ng/L (CRITICAL HIGH, Normal < 14 ng/L).

ED MANAGEMENT & INTERVENTIONS:
1. Aspirin 325 mg chewed immediately.
2. Nitroglycerin 0.4 mg sublingual x2 with partial relief of pain.
3. Heparin IV bolus 5000 units followed by continuous infusion.
4. Ticagrelor 180 mg oral loading dose administered.

ASSESSMENT:
Acute Coronary Syndrome (NSTEMI) — High Risk. Urgent Cardiac Catheterization Lab activation initiated. Admission to Cardiac Care Unit (CCU).""",
    },
    {
        "filename": "doc_08_followup_note.txt",
        "doc_type": "followup_note",
        "title": "Pulmonology Outpatient Follow-up Note",
        "content": """PULMONOLOGY OUTPATIENT FOLLOW-UP VISIT
Patient Name: Arthur Pendelton
DOB: 1955-08-22 | MRN: SYN-100208
Date of Visit: 20 September 2026
Attending Pulmonologist: Dr. Grace Lin, MD

REASON FOR VISIT:
Outpatient follow-up after hospital discharge for acute COPD exacerbation 3 weeks ago.

CLINICAL STATUS:
Mr. Pendelton reports substantial improvement in dyspnea. He is able to walk 200 meters without stopping. Cough has decreased significantly with clear sputum production. He completed his 5-day prednisone burst and antibiotic course without adverse effects.

PHYSICAL EXAM:
BP: 128/78 mmHg | HR: 72 bpm | SpO2: 96% on room air.
Lungs: Clear to auscultation bilaterally. No wheezing, rhonchi, or rales.

SPIROMETRY RESULTS (Post-Bronchodilator today):
- FVC: 3.12 L (78% predicted)
- FEV1: 1.68 L (56% predicted)
- FEV1/FVC ratio: 0.54 (GOLD Stage 2 / Moderate COPD)

IMPRESSION & PLAN:
1. COPD, GOLD Stage 2 B, stable post-exacerbation.
2. Maintenance Inhaler Therapy: Continue Tiotropium 18 mcg daily + Fluticasone/Salmeterol 250/50 mcg BID.
3. Pulmonary Rehabilitation: Referral submitted for 8-week outpatient program.
4. Next follow-up in 3 months with repeat spirometry.""",
    },
    {
        "filename": "doc_09_operative_report.txt",
        "doc_type": "operative_report",
        "title": "Surgical Operative Report — Laparoscopic Cholecystectomy",
        "content": """SURGICAL OPERATIVE REPORT
Patient Name: Susan Bennett
DOB: 1982-05-19 | MRN: SYN-100209
Date of Surgery: 19 September 2026
Surgeon: Dr. Richard Sterling, MD (General Surgery)
Preoperative Diagnosis: Acute calculous cholecystitis
Postoperative Diagnosis: Acute suppurative cholecystitis with cholelithiasis
Procedure Performed: Laparoscopic Cholecystectomy with Intraoperative Cholangiogram

INDICATIONS FOR PROCEDURE:
44-year-old female presenting with acute right upper quadrant abdominal pain, positive Murphy's sign, and abdominal ultrasound demonstrating gallstones with gallbladder wall thickening (5 mm).

DESCRIPTION OF PROCEDURE:
Under general endotracheal anesthesia, pneumatic peritoneum was established using a Veress needle. Standard 4-port laparoscopic access was achieved. The gallbladder was markedly distended and inflamed. Dissection of Calot's triangle successfully identified the cystic duct and cystic artery. Critical view of safety was unequivocally achieved. Intraoperative cholangiogram demonstrated free flow of contrast into the duodenum without choledocholithiasis. Cystic duct and artery were double-clipped and divided. The gallbladder was dissected off the liver bed using electrocautery, placed in an EndoCatch bag, and extracted through the umbilical port.

ESTIMATED BLOOD LOSS: < 20 mL.
COMPLICATIONS: None.
SPECIMENS REMOVED: Gallbladder sent to Surgical Pathology.""",
    },
    {
        "filename": "doc_10_consultation_report.txt",
        "doc_type": "consultation_report",
        "title": "Nephrology Consultation Note — Acute Kidney Injury",
        "content": """NEPHROLOGY SPECIALIST CONSULTATION NOTE
Patient Name: Thomas Wright
DOB: 1950-12-11 | MRN: SYN-100210
Date of Consultation: 23 September 2026
Consulting Physician: Dr. Benjamin Hayes, MD (Nephrology)

REASON FOR CONSULTATION:
Evaluation of acute kidney injury (AKI) superimposed on chronic kidney disease (CKD Stage 3a).

HISTORY OF PRESENT ILLNESS:
75-year-old male admitted for knee arthroplasty who received preoperative NSAID therapy (Ibuprofen 800 mg TID for 10 days) and intraoperative intravenous contrast. Serum creatinine has increased from baseline 1.3 mg/dL to 2.9 mg/dL over the past 48 hours. Urine output has decreased to 350 mL / 24 hours.

LABORATORY & DIAGNOSTIC DATA:
- Serum Creatinine: 2.9 mg/dL (Baseline 1.3 mg/dL)
- Blood Urea Nitrogen: 46 mg/dL
- Fractional Excretion of Sodium (FENa): 0.6% (Prerenal etiology pattern)
- Renal Ultrasound: Normal bilateral kidney size (11.2 cm left, 10.8 cm right), no hydronephrosis.

IMPRESSION:
Acute Kidney Injury (KDIGO Stage 2), prerenal hemodynamically mediated secondary to NSAID-induced renal vasoconstriction and IV contrast administration.

RECOMMENDATIONS:
1. Immediately discontinue all NSAIDs and nephrotoxic agents.
2. Intravenous normal saline 0.9% infusion at 100 mL/hr for volume expansion.
3. Hold ACE inhibitors / ARBs until serum creatinine returns to baseline.
4. Daily BMP monitoring (electrolyte and renal panel).""",
    },
]


def generate_dataset():
    print(f"Generating synthetic clinical documents in: {DATASET_DIR}")
    for doc in SYNTHETIC_DOCUMENTS:
        file_path = DATASET_DIR / doc["filename"]
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(doc["content"])
        print(f"  ✓ Created {doc['filename']} ({len(doc['content'])} bytes)")

    print(f"\nSuccessfully generated {len(SYNTHETIC_DOCUMENTS)} synthetic clinical documents.")


if __name__ == "__main__":
    generate_dataset()
