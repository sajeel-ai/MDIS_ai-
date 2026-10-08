# Cognate AI — Design System Tokens (`docs/DESIGN_TOKENS.md`)

This document defines the authoritative design tokens extracted from the Figma prototype for use across the React application. All tokens are declared as CSS custom properties in `src/index.css`.

---

## 1. Color System (HSL & HEX Tokens)

```css
:root {
  /* Brand Identity */
  --brand-dark: #0f1923;         /* Deep Navy - Navigation, Dark Headers */
  --brand-primary: #2563eb;      /* Royal Blue - Primary Buttons, Focus Rings */
  --brand-primary-hover: #1d4ed8;/* Darker Royal Blue - Button Hover */
  --brand-accent: #3b82f6;       /* Vibrant Blue - Highlights, Active Tabs */

  /* AI & Clinical Indicators */
  --ai-cyan: #06b6d4;           /* Electric Cyan - AI Operations & Extractions */
  --ai-cyan-bg: #ecfeff;        /* Cyan Surface Tint */
  --ai-cyan-border: #a5f3fc;    /* Cyan Border Tint */

  /* Surface & Background Colors */
  --bg-app: #f7f8fa;             /* Primary Application Background */
  --bg-surface: #ffffff;         /* Card / Panel Surface Background */
  --bg-surface-secondary: #f0f2f5;/* Hover / Inactive Surface Background */
  --bg-sidebar: #0f1923;         /* Sidebar Surface Background */

  /* Border Colors */
  --border-subtle: #e2e6eb;      /* Default Card & Divider Border */
  --border-sidebar: #1e2d3d;     /* Dark Sidebar Divider Border */
  --border-strong: #cbd5e1;      /* Input & Active Component Border */

  /* Status Colors (Clinical Validation) */
  --status-success-bg: #f0fdf4;  /* Validated Entity Background */
  --status-success-border: #bbf7d0;
  --status-success-text: #15803d;  /* Validated Entity Text */

  --status-warning-bg: #fffbeb;  /* Needs Review Background */
  --status-warning-border: #fef3c7;
  --status-warning-text: #b45309;  /* Needs Review Text */

  --status-error-bg: #fef2f2;    /* Validation Error Background */
  --status-error-border: #fecaca;
  --status-error-text: #b91c1c;    /* Validation Error Text */

  --status-info-bg: #eff6ff;     /* System Info Background */
  --status-info-border: #bfdbfe;
  --status-info-text: #1d4ed8;     /* System Info Text */

  /* Typography Text Colors */
  --text-primary: #0f1923;       /* Main Headings & Body */
  --text-secondary: #4a5568;     /* Subtitles & Form Labels */
  --text-muted: #8a9ab0;         /* Timestamps, Footers, Placeholders */
  --text-inverse: #ffffff;       /* Inverse Text on Dark Backgrounds */
}
```

---

## 2. Typography Tokens

```css
:root {
  /* Font Families */
  --font-heading: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-body: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  /* Font Sizes & Line Heights */
  --text-xs: 10px;    /* Monospace tags, status indicators */
  --text-sm: 12px;    /* Secondary text, table cells, metadata */
  --text-base: 13px;  /* Standard UI text, buttons, body copy */
  --text-md: 14px;    /* Section titles, card headings */
  --text-lg: 16px;    /* Primary modal & header titles */
  --text-xl: 20px;    /* KPI metric numbers, view titles */
  --text-2xl: 24px;   /* Major dashboard hero figures */

  /* Font Weights */
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;
}
```

---

## 3. Spacing, Radius & Shadow Tokens

```css
:root {
  /* Spacing Scale (Matching Figma 4px grid) */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;

  /* Corner Radius */
  --radius-sm: 4px;   /* Badges, tags, small inputs */
  --radius-md: 6px;   /* Standard buttons, input fields, cards */
  --radius-lg: 8px;   /* Dialogs, drawers, large panels */
  --radius-full: 9999px; /* Avatars, rounded pills */

  /* Elevation Shadows */
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
}
```
