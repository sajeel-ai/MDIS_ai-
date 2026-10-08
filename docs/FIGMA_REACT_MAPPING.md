# Figma to React Component & Architecture Mapping (M0 Audit)

This document establishes the official 1:1 mapping between the approved Figma design frames, components, variants, design tokens, and the React application component hierarchy.

---

## 1. Design Token Mapping

| Figma Variable / Token | CSS Variable (`src/index.css`) | Tailwind Class / Style Usage | Value / Token Definition |
| :--- | :--- | :--- | :--- |
| `Brand / Dark Navy` | `--brand-dark` | `bg-[#0f1923]` | Dark sidebar & header accents |
| `Brand / Primary Blue` | `--brand-primary` | `bg-[#2563eb]` / `text-[#2563eb]` | Interactive buttons, active tabs |
| `AI / Electric Cyan` | `--ai-accent` | `bg-[#06b6d4]` / `text-[#0891b2]` | AI extraction indicators |
| `Surface / Card Light` | `--surface-card` | `bg-white` | Card containers & panels |
| `Border / Subtle` | `--border-subtle` | `border-[#e2e6eb]` | Divider lines & card borders |
| `Status / Validated Green` | `--status-success` | `bg-[#f0fdf4]` / `text-[#15803d]` | High confidence / Validated |
| `Status / Review Amber` | `--status-warning` | `bg-[#fffbeb]` / `text-[#b45309]` | Needs review |
| `Status / Error Red` | `--status-error` | `bg-[#fef2f2]` / `text-[#b91c1c]` | Validation error / Failed |
| `Typography / Heading` | `--font-heading` | `font-['DM_Sans',sans-serif]` | Page titles & metric headers |
| `Typography / Body` | `--font-body` | `font-['Inter',sans-serif]` | General clinical body text |
| `Typography / Mono` | `--font-mono` | `font-['JetBrains_Mono',monospace]` | System status, codes, timestamps |

---

## 2. Route & Screen Mapping

| Figma Frame / Screen | React Route / View | Target Page Component | Layout Container |
| :--- | :--- | :--- | :--- |
| `01_Dashboard` | `/` | `src/pages/Dashboard.tsx` | `AppLayout` |
| `02_Documents` | `/documents` | `src/pages/Documents.tsx` | `AppLayout` |
| `03_ClinicalWorkspace` | `/workspace/:id` | `src/pages/ClinicalWorkspace.tsx` | `WorkspaceLayout` |
| `04_ReviewCenter` | `/review` | `src/pages/ReviewCenter.tsx` | `AppLayout` |
| `05_Workflows` | `/workflows` | `src/pages/Workflows.tsx` | `AppLayout` |
| `06_Integrations` | `/integrations` | `src/pages/Integrations.tsx` | `AppLayout` |
| `07_AIOperations` | `/ai-operations` | `src/pages/AIOperations.tsx` | `AppLayout` |
| `08_PatientTimeline` | `/timeline` | `src/pages/PatientTimeline.tsx` | `AppLayout` |
| `09_Audit` | `/audit` | `src/pages/Audit.tsx` | `AppLayout` |
| `10_Settings` | `/settings` | `src/pages/Settings.tsx` | `AppLayout` |

---

## 3. Component Taxonomy Mapping

### Generic Primitives (`src/components/ui/`)
- `Button`: Standard button with primary, secondary, outline, ghost, and danger variants matching Figma height (`36px`/`40px`) and radius (`6px`).
- `Card`: Surface container with `1px solid #e2e6eb`, `6px` radius, white background.
- `Badge`: Status badge with green/amber/red/blue colorways and monospace text.
- `Dialog` & `Drawer`: Accessible modal overlays & off-canvas drawer slides.
- `Tabs`: Segmented control tabs with active pill indicators.
- `Tooltip`: Hover tooltip with 150ms delay and dark background.

### Cognate Shared Components (`src/components/shared/`)
- `MetricCard`: KPI card displaying count, trend indicator, and comparison text.
- `PageHeader`: Page title, subtitle, breadcrumb, and quick action toolbar.
- `StatusIndicator`: Pulse dot + system nominal / active status label.
- `DataTable`: Table wrapper with sorting, pagination, and empty states.
- `CommandPalette`: `Cmd+K` global search modal with categorized results.

### Feature Domain Components (`src/components/features/`)
- `DocumentUpload`: Drag-and-drop file upload with 5-stage progress animation (Upload → OCR → Extraction → Validation → Structuring).
- `DocumentViewer`: Pan, zoom, search, and page navigation PDF/image viewer with text highlight overlay.
- `EntityCard`: Extracted clinical entity card with confidence percentage badge, validation status, and evidence highlight button.
- `EvidencePanel`: Side panel displaying exact source quote, page number, bounding box snippet, and confidence score.
- `ReviewQueueItem`: Priority card in Review Center supporting quick actions and hotkeys (`A` Approve, `R` Reject, `E` Edit, `V` View Evidence, `N` Next).
- `WorkflowNode`: Drag-and-drop workflow card node with inputs, outputs, and status badge.
- `ProcessingTimeline`: Step-by-step AI operations timeline with execution timestamps and failure inspection triggers.
