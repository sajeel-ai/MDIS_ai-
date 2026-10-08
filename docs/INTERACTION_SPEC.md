# Cognate AI — Interactive Features & Behavior Specification (`docs/INTERACTION_SPEC.md`)

This specification defines hover/active states, hotkey workflows, document viewer evidence mapping, and notification behaviors.

---

## 1. Global Command Palette (`Cmd + K` / `Ctrl + K`)

- **Trigger**: Global hotkey `Cmd+K` (macOS) or `Ctrl+K` (Windows/Linux), or clicking search bar in header.
- **Behavior**: Modal backdrop opens with auto-focused input field.
- **Search Scope**:
  - **Documents**: Filters document title, patient name, case ID.
  - **Patients**: Filters MRN, patient name, DOB.
  - **Reviews**: Filters pending high-priority review items.
  - **Workflows**: Quick actions for workflow creation & execution.
- **Keyboard Navigation**: `Up`/`Down` arrow keys select item, `Enter` executes navigation, `Esc` closes modal.

---

## 2. Review Center Power-User Hotkey Workflow

In the Review Center (`/review`), clinical reviewers can perform rapid validation using dedicated keyboard shortcuts:

| Key | Action | Description | Tooltip Label |
| :--- | :--- | :--- | :--- |
| `A` | **Approve** | Accepts AI extraction and marks entity as Validated | `Approve (A)` |
| `R` | **Reject** | Flag extraction as incorrect / conflict | `Reject (R)` |
| `E` | **Edit** | Opens inline entity correction dialog | `Edit Entity (E)` |
| `V` | **View Evidence** | Focuses document viewer on source text highlight | `View Evidence (V)` |
| `N` | **Next Case** | Moves focus to next queue item | `Next Case (N)` |

---

## 3. Interactive Document Viewer & Source Evidence Mapping

- **Bidirectional Highlighting**:
  - Clicking an extracted entity card (e.g., *Lisinopril 10 mg*) scrolls the document viewer to the exact source page and draws an electric cyan highlight box (`--ai-cyan`) around the supporting text snippet.
  - Hovering over a document highlight displays a popover with confidence score (e.g., `96% Confidence`), extraction schema, and reviewer validation status.
- **Controls Toolbar**: Zoom In/Out, Fit to Width, Page Jump (`1 / 4`), Search text within document.

---

## 4. Drag & Drop Document Upload Pipeline (5 Stages)

- **Upload Modal / Area**: Accepts PDF, PNG, JPG, DOCX files up to 25MB.
- **Visual Progress Pipeline Animation**:
  1. `Stage 1: Uploading File...` (Progress bar 0–100%)
  2. `Stage 2: OCR & Layout Analysis` (Pulse animation)
  3. `Stage 3: Clinical Entity Extraction` (Cyan progress indicator)
  4. `Stage 4: Validation & Confidence Scoring` (Amber/Green status compute)
  5. `Stage 5: Structuring FHIR Output` (Completed state checkmark `✓`)

---

## 5. AI Operations Telemetry & Metric Policy

- **Strict Data Policy**: The AI Operations view displays **ONLY backend-provided, evaluated metrics** with their associated:
  - Evaluation Context (e.g., *MIMIC-IV Clinical Test Set*)
  - Model Version (e.g., *Clinical-NLP-v2.4*)
  - Measurement Period (e.g., *Last 30 Days*)
- **Metrics Tracked**: Precision, Recall, F1 Score, Processing Latency (ms), Throughput (docs/min), Low-Confidence Review Rate (%), Error Logs with raw stack trace drawer.
