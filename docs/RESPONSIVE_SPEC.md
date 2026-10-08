# Cognate AI — Responsive Engineering Specification (`docs/RESPONSIVE_SPEC.md`)

This specification governs responsive behavior across all device viewports.

---

## 1. Absolute Rule for Desktop (`1440px+`)

> [!IMPORTANT]
> **Desktop Layout Non-Alteration Rule**
> At `1440px+` screen width, the Figma desktop composition is the **absolute source of truth**. Responsive logic must NOT alter, compress, or reflow desktop panel dimensions, spacing, or proportions.

---

## 2. Breakpoint Matrix & Adaptation Strategy

| Breakpoint | Target Screen Width | Navigation Layout | Main Workspace Layout | Clinical Workspace Layout |
| :--- | :--- | :--- | :--- | :--- |
| **Desktop Wide** | `1440px+` | Expanded Sidebar (`220px`) | Full 3-Column / Wide Multi-card | **3 Panels**: Source Document (`35%`) \| Extracted Data (`40%`) \| Evidence (`25%`) |
| **Desktop / Laptop**| `1024px – 1439px` | Collapsible Sidebar (`72px` Icon-only) | Container max-width padding | **3 Panels**: Collapsible evidence drawer |
| **Tablet** | `768px – 1023px` | Collapsible Sidebar (`72px` Icon-only) | Single column scroll | **Tabbed Panel**: Toggle between Source, Extracted Data, and Evidence tabs |
| **Mobile Large** | `390px – 767px` | Mobile Header + Slide-out Drawer | Stacked cards | **Stacked Panel**: Vertical order (Document → Extracted Data → Evidence) |
| **Mobile Small** | `< 390px` | Mobile Header + Slide-out Drawer | Compact single column | **Stacked Panel**: Full-width compact cards |

---

## 3. Component-Level Responsive Behaviors

### Sidebar Navigation
- **`1440px+`**: Full persistent sidebar (`220px` width) displaying brand logo, section headers (`CLINICAL`, `AI`, `SYSTEM`), item labels, and badges.
- **`768px – 1439px`**: Collapsed icon bar (`72px` width) showing tooltips on hover.
- **`< 768px`**: Off-canvas slide-out drawer triggered by top header hamburger button `☰`.

### Clinical Workspace (Centerpiece Component)
- **`1440px+`**: Side-by-side 3-panel container:
  - **Left**: Interactive Source Document Viewer with highlight box.
  - **Middle**: Extracted Entity Cards (Diagnoses, Medications, Symptoms, Lab Results).
  - **Right**: Evidence & Audit Details panel.
- **`< 1024px`**: Switches from 3 fixed desktop columns to interactive tab navigation (`[Source Document]`, `[Extracted Data]`, `[Evidence Details]`) to ensure clean readability on touch devices without squishing text.
