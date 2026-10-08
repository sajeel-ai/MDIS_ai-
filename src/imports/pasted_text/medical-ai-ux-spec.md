Medical AI Agent — Production UX Specification
1. Product UX Vision
Product concept

Clinical Intelligence & Medical AI Agent Platform

The platform transforms unstructured clinical documentation into structured, validated clinical information while maintaining a clear human-in-the-loop workflow.

The UX should communicate:

AI assists clinical professionals; it does not replace clinical judgment.

The primary design goals are:

Clinical clarity
Trust and transparency
Fast review
Traceability
Low cognitive load
Structured information
Safe handling of uncertainty
Enterprise-grade security
Scalability for multiple healthcare workflows
2. Primary Users / Personas
Persona	Primary Goal	UX Need
Physician / Clinician	Quickly understand extracted patient information	Concise clinical summary + evidence
Nurse	Review symptoms, medications and events	Structured patient timeline
Clinical Reviewer	Validate AI-generated extraction	Side-by-side source and AI output
Medical Coder	Review diagnoses and standardized concepts	Coding/terminology view
Clinical Researcher	Search and analyze structured clinical data	Advanced search/filtering
Health Information Manager	Monitor documentation quality	Quality and exception dashboards
Administrator	Manage users, permissions and system	Admin console
AI/ML Operations User	Monitor AI performance	Model/evaluation dashboard
Compliance/Security User	Audit data access	Audit and activity logs
Executive	Understand system utilization and outcomes	High-level analytics dashboard
3. UX Information Architecture

The application should use a clear enterprise navigation model.

Medical AI Platform
│
├── Dashboard
│
├── Clinical Workspace
│   ├── Cases
│   ├── Patient Records
│   ├── Documents
│   └── Clinical Timeline
│
├── AI Extraction
│   ├── New Extraction
│   ├── Processing Queue
│   ├── Results
│   └── Failed / Needs Review
│
├── Review Center
│   ├── Pending Review
│   ├── High Priority
│   ├── AI Conflicts
│   └── Completed Reviews
│
├── Medical Intelligence
│   ├── Diagnoses
│   ├── Medications
│   ├── Symptoms
│   ├── Procedures
│   └── Clinical Events
│
├── Knowledge / Terminology
│   ├── ICD
│   ├── SNOMED
│   ├── RxNorm
│   └── Custom Mappings
│
├── Analytics
│   ├── Extraction Performance
│   ├── Clinical Metrics
│   ├── Processing Metrics
│   └── AI Quality
│
├── Administration
│   ├── Users
│   ├── Roles
│   ├── Organizations
│   ├── Integrations
│   └── Configuration
│
├── Audit & Compliance
│   ├── Audit Logs
│   ├── Access History
│   └── Data Events
│
└── Settings
4. Global Application Layout

The desktop application should use a professional enterprise layout.

┌─────────────────────────────────────────────────────────────────┐
│ Logo   Search clinical records...        Alerts  Help  Profile │
├──────────────┬──────────────────────────────────────────────────┤
│              │                                                  │
│ Dashboard    │                                                  │
│              │                                                  │
│ Clinical     │              MAIN WORKSPACE                      │
│ Workspace    │                                                  │
│              │                                                  │
│ AI           │                                                  │
│ Extraction   │                                                  │
│              │                                                  │
│ Review       │                                                  │
│ Center       │                                                  │
│              │                                                  │
│ Analytics    │                                                  │
│              │                                                  │
│ Admin        │                                                  │
│              │                                                  │
│ Audit        │                                                  │
│              │                                                  │
└──────────────┴──────────────────────────────────────────────────┘
Design characteristics
Desktop-first for clinical/enterprise users
Responsive tablet experience
Persistent navigation
Breadcrumb navigation
Global search
Contextual actions
Keyboard shortcuts
Minimal modal usage
Consistent page hierarchy
5. Dashboard UX

The dashboard should answer four questions immediately:

1. What is happening?
2. What needs my attention?
3. How is the AI performing?
4. Are there any problems?
Dashboard structure
┌─────────────────────────────────────────────────────────┐
│ Clinical Intelligence Dashboard                         │
│ Last updated: 2 minutes ago                             │
├────────────┬────────────┬────────────┬─────────────────┤
│ Documents  │ Processed  │ Review     │ Failed          │
│ 12,480     │ 11,932     │ 348        │ 200             │
├────────────┴────────────┴────────────┴─────────────────┤
│                                                         │
│ AI Processing Activity                                  │
│                                                         │
│              [Processing trend chart]                   │
│                                                         │
├────────────────────────────┬────────────────────────────┤
│ Review Required             │ AI Quality                │
│                            │                            │
│ 12 High Priority           │ Extraction Accuracy        │
│ 48 Medium                  │ Schema Validity            │
│ 288 Normal                 │ Review Rate                │
├────────────────────────────┴────────────────────────────┤
│ Recent Clinical Cases                                   │
│                                                        │
│ Case ID | Document | Status | Confidence | Action      │
└─────────────────────────────────────────────────────────┘

The dashboard should prioritize actionable information, not decorative analytics.

6. Clinical Workspace

This is the most important UX area.

The clinician should be able to open a case and immediately understand the patient's extracted information.

Recommended layout
┌─────────────────────────────────────────────────────────────┐
│ Patient / Case                                             │
│ Case #CL-102938       Processing: Completed                │
├─────────────────────────────────────────────────────────────┤
│ Summary | Diagnoses | Medications | Symptoms | Timeline     │
├───────────────────────┬─────────────────────────────────────┤
│ SOURCE DOCUMENT       │ AI CLINICAL EXTRACTION              │
│                       │                                     │
│ Original clinical     │ Diagnoses                          │
│ note                  │ ┌─────────────────────────────────┐ │
│                       │ │ Hypertension                     │ │
│ "Patient presents    │ │ Active                           │ │
│ with..."              │ │ Evidence: "...history of..."    │ │
│                       │ └─────────────────────────────────┘ │
│                       │                                     │
│                       │ Medications                         │
│                       │ Lisinopril 10 mg once daily         │
│                       │                                     │
│                       │ Symptoms                            │
│                       │ Headache                            │
└───────────────────────┴─────────────────────────────────────┘

This source-to-extraction relationship is critical for trust.

The user should never have to wonder:

"Where did the AI get this information?"

Clicking an extracted entity should highlight the supporting text in the original document.

7. AI Extraction Results UX

Each extracted entity should be represented as a structured card.

Diagnosis card
┌─────────────────────────────────────────┐
│ Diagnosis                               │
│                                         │
│ Hypertension                            │
│                                         │
│ Status       Active                     │
│ Confidence   High                       │
│ Standard     SNOMED CT                  │
│                                         │
│ Evidence                                │
│ "Patient has a history of..."           │
│                                         │
│ [View Source] [Review]                  │
└─────────────────────────────────────────┘
Medication card
┌─────────────────────────────────────────┐
│ Medication                              │
│                                         │
│ Lisinopril                              │
│                                         │
│ Dose       10 mg                        │
│ Frequency  Once daily                    │
│ Route      Oral                         │
│ Status     Active                       │
│                                         │
│ Interaction Check   ✓ No Flag           │
│                                         │
│ [View Source] [Verify]                  │
└─────────────────────────────────────────┘
8. Confidence UX

Do not simply show:

AI Confidence: 92%

That can create false confidence.

Instead, use confidence as a review prioritization signal.

Example:

HIGH CONFIDENCE
✓ Hypertension

MEDIUM CONFIDENCE
⚠ Chronic kidney disease

LOW CONFIDENCE
⚠ Possible pneumonia

Clicking the warning should explain:

Why this requires review:

• Evidence was ambiguous
• Multiple possible interpretations
• Terminology mapping uncertain

Source:
"...possible evidence of pneumonia..."

The UI should distinguish:

AI confidence
schema validity
source evidence
clinical review status

These are different concepts.

9. Review Center

This should be one of the most important screens.

Review Center

┌──────────────────────────────────────────────────────────────┐
│ Pending Review: 348                                         │
├─────────┬──────────────┬──────────┬────────────┬────────────┤
│ Priority│ Patient/Case │ Entity   │ Reason     │ Action     │
├─────────┼──────────────┼──────────┼────────────┼────────────┤
│ High    │ CL-1023      │ Drug     │ Interaction│ Review     │
│ High    │ CL-1031      │ Diagnosis│ Ambiguous  │ Review     │
│ Medium  │ CL-1054      │ Symptom  │ Low conf.  │ Review     │
└─────────┴──────────────┴──────────┴────────────┴────────────┘
Review screen

Use a three-panel review workflow:

┌───────────────────┬───────────────────┬─────────────────────┐
│ SOURCE            │ AI EXTRACTION     │ REVIEW              │
│                   │                   │                     │
│ Clinical note     │ Diagnosis         │ Accept              │
│                   │ Pneumonia         │                     │
│ "...possible      │                   │ Edit                │
│ pneumonia..."     │ Confidence: Low   │                     │
│                   │                   │ Reject              │
│                   │ Evidence           │                     │
│                   │ highlighted        │ Comment             │
└───────────────────┴───────────────────┴─────────────────────┘

This dramatically reduces review time because the reviewer doesn't have to switch between screens.

10. Clinical Timeline

The system should transform extracted events into a chronological view.

2026-09-01
│
├── Diagnosis
│   Hypertension
│
├── Medication
│   Lisinopril 10 mg
│
2026-09-05
│
├── Symptom
│   Headache
│
2026-09-08
│
├── Clinical Event
│   Follow-up consultation
│
└── Medication
    Dosage updated

Use visual differentiation for:

Diagnosis
Medication
Symptoms
Procedures
Lab results
Clinical encounters

But avoid relying solely on color; use icons and labels as well.

11. Document Viewer UX

The original clinical document should remain accessible.

Required features
Search within document
Page navigation
Zoom
Highlight extracted evidence
Entity highlighting
Click entity → show structured interpretation
Document metadata
Version history
Processing status

Example:

Clinical Note

Patient presents with persistent cough and fever.

[Symptom: cough] [Symptom: fever]

Diagnosed with community-acquired pneumonia.

[Diagnosis: pneumonia]

Started on azithromycin 500 mg once daily.

[Medication]
[Drug: azithromycin]
[Dose: 500 mg]
[Frequency: once daily]

This creates a powerful explainability experience.

12. Medical Terminology UX

For production use, users may need to see how an extracted term was normalized.

Extracted Term

"HTN"

        ↓

Normalized Concept

"Hypertension"

        ↓

Terminology

SNOMED CT

        ↓

Status

Verified

The user should be able to:

Accept mapping
Change mapping
Search terminology
See alternative mappings
Report incorrect mapping
13. Medication Safety UX

Medication-related information requires particularly careful presentation.

Example:

Medication Review

┌─────────────────────────────────────────┐
│ Lisinopril                              │
│ 10 mg • Once daily • Oral                │
│                                         │
│ Interaction Review                      │
│                                         │
│ ⚠ Potential interaction identified      │
│                                         │
│ Evidence: Medication A + Medication B   │
│                                         │
│ Source: Drug interaction service         │
│                                         │
│ [View Details] [Send for Review]        │
└─────────────────────────────────────────┘

Avoid presenting an automated interaction flag as a definitive clinical conclusion.

Use language such as:

"Potential interaction identified — review recommended."

rather than:

"Patient has a dangerous interaction."

14. AI Transparency

Every AI-generated result should have an accessible AI Details section.

AI Details

Model: [model name]
Model version: [version]
Extraction timestamp: [timestamp]
Prompt version: [version]
Processing pipeline: v1.4

Source evidence:
"..."

Validation:
✓ Schema valid
✓ Required fields present
✓ Terminology normalized

Review status:
Pending clinical review

This becomes extremely valuable for enterprise customers.

15. Processing Status UX

The user should see exactly where a document is in the pipeline.

Document Processing

✓ Uploaded
✓ Validated
✓ Preprocessed
✓ NLP Analysis
✓ LLM Extraction
✓ Schema Validation
✓ Medical Normalization
● Final Review
○ Completed

For failures:

⚠ Processing requires attention

Step:
Medical terminology normalization

Reason:
Unable to map extracted diagnosis.

[Retry] [Review Manually]

This is far better than simply showing:

"Processing failed."

16. AI Operations Dashboard

For administrators/AI teams:

AI Operations

┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Documents    │ Success Rate │ Review Rate  │ Failed       │
│ 125,430      │ 98.2%        │ 7.4%         │ 1.8%         │
└──────────────┴──────────────┴──────────────┴──────────────┘

Extraction Quality

Diagnosis        █████████████ 96%
Medication       ████████████  94%
Symptoms         ███████████   91%
Temporal         █████████     87%

Pipeline Performance

Ingestion → NLP → LLM → Validation → Normalization

Track:

Extraction accuracy
Schema validity
Review percentage
Failure rate
Latency
Token usage
Cost
Model version
Prompt version
Retry rate
17. Data Engineering Monitoring UX

Because the production architecture includes data engineering, provide an operational pipeline screen.

DATA PIPELINE

EHR/EMR
   │
   ▼
Ingestion             ✓ Healthy
   │
   ▼
Kafka                  ✓ Healthy
   │
   ▼
Raw Storage            ✓ Healthy
   │
   ▼
Preprocessing          ✓ Healthy
   │
   ▼
Clinical NLP            ⚠ 3 failures
   │
   ▼
LLM Extraction          ✓ Healthy
   │
   ▼
Validation              ✓ Healthy
   │
   ▼
PostgreSQL              ✓ Healthy

Clicking a stage should expose:

Throughput
Failed records
Processing latency
Error logs
Retry count
Current health

This is for technical/operations users, not clinicians.

18. Role-Based UX

The platform should dynamically adapt to the user's role.

Role	Primary Interface
Physician	Clinical Workspace
Nurse	Patient Timeline
Clinical Reviewer	Review Center
Coder	Terminology/Coding
Researcher	Search + Analytics
Administrator	Administration
AI Engineer	AI Operations
Data Engineer	Pipeline Monitoring
Security Officer	Audit & Security
Executive	Executive Dashboard

Don't expose every function to every user.

This reduces cognitive overload and improves security.

19. Design System

For the visual language, I recommend a modern clinical enterprise aesthetic.

Design principles
Clean
Calm
Professional
Minimal
High information density without visual clutter
Strong typography
Generous spacing
Clear hierarchy
Accessible contrast
Consistent status indicators
Suggested visual hierarchy
Primary
   ↓
Page title
   ↓
Section heading
   ↓
Clinical entity
   ↓
Supporting metadata
   ↓
Evidence
   ↓
Secondary actions

Avoid excessive gradients, glassmorphism, animations, or consumer-chatbot styling.

The application should feel closer to a modern clinical/EHR enterprise system than ChatGPT.

20. Color System

I recommend using semantic colors rather than decorative colors.

Meaning	Suggested Treatment
Primary action	Blue
Success / validated	Green
Warning / review	Amber
Critical / attention	Red
Informational	Blue/neutral
Neutral	Gray
AI-generated	Subtle indigo/purple indicator
Human verified	Green verification indicator

Important:

Never communicate medical meaning through color alone.

For example:

⚠ Review required

rather than only displaying an amber-colored card.

21. Accessibility

Production healthcare UX should target WCAG 2.2 AA.

Include:

Keyboard navigation
Screen-reader support
Accessible form labels
Focus indicators
Adequate contrast
Scalable typography
Non-color status indicators
Accessible tables
Error messages adjacent to fields
Keyboard-accessible evidence navigation
22. Search UX

Global clinical search should support:

Search:
"hypertension"

Results

Patients
Cases
Documents
Diagnoses
Medications
Clinical Events

Advanced filters:

Date
Department
Diagnosis
Medication
Document type
Review status
AI confidence
Processing status
Reviewer

For large datasets, use semantic search in addition to keyword search.

23. Notifications

Notifications should be action-oriented.

Bad:

"AI processing completed."

Better:

12 clinical cases require review.

Example:

Notifications

🔴 3 high-priority reviews
   Medication validation required

🟡 12 cases require review
   Low-confidence extraction

🔵 1 pipeline issue
   Terminology service unavailable
24. Error UX

Errors should explain:

What happened?
Why?
What can the user do?

Example:

Unable to normalize diagnosis

The AI extracted:
"Possible viral pneumonia"

The terminology service could not
identify a matching standardized concept.

[Search Manually]
[Retry]
[Send for Review]

Never show raw backend errors to clinicians.

25. Empty States

Every major screen needs intentional empty states.

Example:

No cases require review

✓ All clinical extraction results have
  been reviewed.

Last updated: 2 minutes ago

Not:

"No data."

26. Mobile / Tablet Strategy

The primary experience should be desktop-first because clinical review requires dense information.

Tablet:

Clinical review
Patient timeline
Document reading
Basic approvals

Mobile:

Notifications
Review alerts
Quick status
Simple approvals

Don't attempt to reproduce the entire desktop clinical workspace on a phone.

27. UX Flow — Complete Clinical Journey
LOGIN
  ↓
ROLE IDENTIFICATION
  ↓
DASHBOARD
  ↓
SELECT CASE
  ↓
VIEW CLINICAL DOCUMENT
  ↓
AI PROCESSING
  ↓
CLINICAL NLP
  ↓
AI EXTRACTION
  ↓
STRUCTURED RESULTS
  ↓
VALIDATION
  ↓
┌─────────────────────┐
│                     │
▼                     ▼
High Confidence    Requires Review
│                     │
▼                     ▼
Accept              Review Center
│                     │
│              Source ↔ AI Output
│                     │
│                 Edit/Accept
│                     │
└──────────┬──────────┘
           ↓
      NORMALIZATION
           ↓
      FHIR-LITE DATA
           ↓
      PATIENT RECORD
           ↓
       ANALYTICS
28. UX Team Deliverables

I would ask your UX team to produce the following artifacts:

#	UX Deliverable	Details
1	User Personas	Physician, reviewer, admin, AI engineer, etc.
2	User Journey Maps	End-to-end workflows
3	Information Architecture	Navigation and hierarchy
4	Design System	Colors, typography, spacing, components
5	Dashboard Wireframes	Executive + operational
6	Clinical Workspace	Primary clinical interface
7	Document Viewer	Source/evidence interface
8	AI Extraction Screen	Structured medical results
9	Review Center	Human-in-the-loop workflow
10	Patient Timeline	Chronological clinical events
11	Medication UX	Medication and validation interface
12	Terminology UX	ICD/SNOMED/RxNorm mapping
13	AI Explainability	Evidence and model metadata
14	Data Pipeline Dashboard	Engineering/operations monitoring
15	AI Operations Dashboard	Model quality and performance
16	Admin Console	Users, roles, configuration
17	Audit Interface	Security/compliance activity
18	Search UX	Keyword + semantic search
19	Error/Empty States	System-wide state design
20	Responsive Designs	Desktop + tablet
21	Accessibility Specification	WCAG 2.2 AA
22	Interactive Prototype	Figma prototype
23	Developer Handoff	Components, states, measurements
24	Usability Testing	Clinician/reviewer testing
25	Design QA	Validate implementation against Figma
29. Recommended Frontend Technology

For the engineering team, I would use:

Technology	Purpose
Next.js	Production React framework
React + TypeScript	UI development
Tailwind CSS	Design implementation
shadcn/ui	Enterprise component foundation
TanStack Query	API/server-state management
Zustand	Lightweight client state
React Hook Form	Complex forms
Zod	Frontend validation
Recharts / Apache ECharts	Analytics
React PDF / PDF.js	Document viewing
WebSocket/SSE	Live processing status
Figma	UX/UI design
Storybook	Component documentation
Playwright	End-to-end testing
Vitest/Jest	Unit testing
30. Most Important UX Principle

The defining experience should be:

"Show me the AI result, show me the evidence, tell me whether it is reliable, and let me verify it quickly."

That means every important clinical extraction should have this relationship:

              AI RESULT
                  │
       ┌──────────┼──────────┐
       ↓          ↓          ↓
    Evidence   Confidence  Validation
       │          │          │
       └──────────┼──────────┘
                  ↓
             Human Review
                  ↓
            Verified Data

That is what will make the product feel like a professional clinical intelligence platform rather than simply another LLM interface.

For your UX team, I would make Clinical Workspace + Source/Evidence Viewer + Review Center + Patient Timeline the four highest-priority experiences. Everything else—analytics, administration, AI monitoring, data pipeline monitoring—should support those core workflows.