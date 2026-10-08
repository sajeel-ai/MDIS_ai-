/**
 * ============================================================
 *  COMPREHENSIVE PAGE TESTS — Every Page & View
 *  v4 — Uses importOriginal so ALL API exports are included.
 *  Only network-calling functions are overridden.
 * ============================================================
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

// ── Global API mock (importOriginal keeps all type exports intact) ─────────
vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>()
  return {
    ...actual,
    // Auth
    fetchCurrentUser: vi
      .fn()
      .mockResolvedValue({ id: "user-1", role: "reviewer", name: "Test User" }),
    login: vi
      .fn()
      .mockResolvedValue({ id: "user-1", role: "reviewer", name: "Test User" }),
    getAccessToken: vi.fn().mockReturnValue("mock-token"),
    clearAccessToken: vi.fn(),

    // Dashboard
    fetchDashboard: vi.fn().mockResolvedValue({
      metrics: {
        total_documents: 142,
        processed: 130,
        pending_review: 8,
        failed: 4,
        last_updated_at: new Date().toISOString(),
      },
      review_queue_summary: { pending: 8, high_priority: 3 },
      extraction_quality: [{ category: "diagnoses", accuracy: 0.94 }],
      recent_cases: [
        {
          id: "doc-001",
          patient_name: "Test Patient",
          doc_type: "Discharge Summary",
          status: "completed",
          confidence: "high",
          entity_count: 12,
          timestamp: new Date().toISOString(),
        },
      ],
    }),

    // Review
    fetchReviewStats: vi.fn().mockResolvedValue({
      pending: 8,
      high_priority: 3,
      approved: 45,
      rejected: 6,
    }),
    fetchReviewQueue: vi.fn().mockResolvedValue({
      items: [
        {
          id: "task-001",
          priority: "high",
          status: "pending",
          reason: "Low confidence extraction",
          entity: {
            id: "ent-001",
            raw_text: "Hypertension",
            normalized_value: "Hypertension",
            confidence: 0.72,
            entity_type: "diagnosis",
          },
          patient: { display_name: "Jane Doe" },
          document: { file_name: "discharge-summary.pdf" },
        },
      ],
      total: 1,
      page: 1,
      per_page: 50,
    }),
    fetchReviewTaskDetail: vi.fn().mockResolvedValue({
      id: "task-001",
      priority: "high",
      status: "pending",
      reason: "Low confidence extraction",
      entity: {
        id: "ent-001",
        raw_text: "Hypertension",
        normalized_value: "Hypertension",
        confidence: 0.72,
        entity_type: "diagnosis",
      },
      patient: { display_name: "Jane Doe", mrn: "MRN-001" },
      document: { file_name: "discharge-summary.pdf", id: "doc-001" },
      evidence: { text: "Patient has hypertension." },
      decision: null,
      pipeline_stages: [],
    }),
    startReviewTask: vi.fn().mockResolvedValue({
      id: "task-001",
      priority: "high",
      status: "pending",
      reason: "Low confidence extraction",
      entity: {
        id: "ent-001",
        raw_text: "Hypertension",
        normalized_value: "Hypertension",
        confidence: 0.72,
        entity_type: "diagnosis",
      },
      patient: { display_name: "Jane Doe", mrn: "MRN-001" },
      document: { file_name: "discharge-summary.pdf", id: "doc-001" },
      evidence: { text: "Patient has hypertension." },
      decision: null,
      pipeline_stages: [],
    }),
    fetchReviewPolicy: vi.fn().mockResolvedValue({
      auto_approve_threshold: 0.95,
      require_comment_on_reject: true,
    }),
    approveReviewTask: vi
      .fn()
      .mockResolvedValue({ id: "task-001", status: "approved" }),
    rejectReviewTask: vi
      .fn()
      .mockResolvedValue({ id: "task-001", status: "rejected" }),
    correctReviewTask: vi
      .fn()
      .mockResolvedValue({ id: "task-001", status: "corrected" }),
    approveCleanReviewItems: vi.fn().mockResolvedValue({ approved_count: 3 }),
    submitReviewDecision: vi.fn().mockResolvedValue({}),

    // Documents / Clinical Workspace
    fetchDocuments: vi.fn().mockResolvedValue({
      items: [
        {
          id: "doc-001",
          file_name: "test.pdf",
          status: "completed",
          case_id: "CASE-001",
          patient_name: "John Smith",
          mrn: "MRN-123",
          doc_type: "discharge_summary",
          last_updated: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      per_page: 10,
    }),
    fetchDocumentDetails: vi.fn().mockResolvedValue({
      id: "doc-001",
      case_id: "CASE-001",
      patient_name: "John Smith",
      mrn: "MRN-123",
      status: "completed",
      pipeline_stages: [
        { name: "OCR", detail: "Text extracted", status: "done" },
      ],
    }),
    fetchDocumentEntities: vi.fn().mockResolvedValue([
      {
        id: "ent-001",
        entity_type: "diagnosis",
        raw_text: "Hypertension",
        normalized_value: "Hypertension",
        confidence: 0.94,
        evidence_spans: [],
      },
      {
        id: "ent-002",
        entity_type: "medication",
        raw_text: "Lisinopril",
        normalized_value: "Lisinopril 10mg",
        confidence: 0.88,
        evidence_spans: [],
      },
    ]),
    fetchDocumentEvidence: vi.fn().mockResolvedValue([]),
    uploadDocument: vi.fn().mockResolvedValue({ id: "doc-002" }),
    processDocument: vi.fn().mockResolvedValue({ job_id: "job-001" }),
    retryDocumentProcessing: vi.fn().mockResolvedValue({ job_id: "job-002" }),
    fetchProcessingJob: vi
      .fn()
      .mockResolvedValue({ status: "completed", id: "job-001" }),

    // Patients
    fetchPatients: vi.fn().mockResolvedValue({
      items: [
        {
          id: "pat-001",
          display_name: "John Smith",
          first_name: "John",
          last_name: "Smith",
          mrn: "MRN-123",
        },
      ],
      total: 1,
      page: 1,
      per_page: 100,
    }),
    fetchPatientTimeline: vi.fn().mockResolvedValue({
      timeline_events: [
        {
          id: "tl-001",
          type: "diagnosis",
          title: "Hypertension",
          date: "2024-01-15",
          detail: "Confirmed diagnosis",
        },
      ],
    }),

    // AI Operations — field names match OperationalViews.tsx usage
    fetchAIOpsMetrics: vi.fn().mockResolvedValue({
      total_jobs: 130,
      completed_jobs: 120,
      failed_jobs: 4,
      avg_confidence: 0.87,
      high_confidence_pct: 0.72,
      avg_duration_ms: 3100,
    }),
    fetchAIOpsJobs: vi.fn().mockResolvedValue({
      jobs: [
        {
          job_id: "job-001",
          status: "completed",
          doc_type: "Discharge Summary",
          document_id: "doc-001",
          created_at: new Date().toISOString(),
          duration_ms: 3200,
        },
      ],
    }),
    fetchAIOpsHealth: vi.fn().mockResolvedValue({
      status: "healthy",
      pipeline: "running",
      queue_depth: 2,
      avg_latency_ms: 1200,
      model_version: "v2.1",
      active_jobs: 3,
    }),

    // Audit — field names match OperationalViews.tsx (event.action, event.user, event.resource_type, event.created_at)
    fetchAuditEvents: vi.fn().mockResolvedValue({
      items: [
        {
          id: "ev-001",
          action: "approved",
          user: "reviewer@cognate.ai",
          resource_type: "review_task",
          created_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      per_page: 50,
    }),

    // Integrations
    fetchFHIRMetadata: vi.fn().mockResolvedValue({
      reachable: true,
      configured: true,
      resource: { fhirVersion: "4.0.1" },
    }),

    // Health
    fetchHealthStatus: vi.fn().mockResolvedValue({
      status: "ok",
      service: "cognate-ai-api",
      database: "connected",
    }),
  }
})

// ─────────────────────────────────────────────────────────────────────────────
// 1. DASHBOARD PAGE
// ─────────────────────────────────────────────────────────────────────────────
describe("1. Dashboard page", () => {
  it("renders without crashing", async () => {
    const { Dashboard } = await import("../views/Dashboard")
    const { container } = render(<Dashboard onNavigate={vi.fn()} />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows page heading", async () => {
    const { Dashboard } = await import("../views/Dashboard")
    render(<Dashboard onNavigate={vi.fn()} />)
    expect(
      screen.getByText("Clinical Intelligence Dashboard"),
    ).toBeInTheDocument()
  })

  it("displays live metric total after API resolves", async () => {
    const { Dashboard } = await import("../views/Dashboard")
    render(<Dashboard onNavigate={vi.fn()} />)
    await waitFor(() => expect(screen.getByText("142")).toBeInTheDocument())
  })

  it("Export button shows info banner on click", async () => {
    const { Dashboard } = await import("../views/Dashboard")
    render(<Dashboard onNavigate={vi.fn()} />)
    fireEvent.click(screen.getByText("Export"))
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument())
  })

  it("New Extraction button shows info banner on click", async () => {
    const { Dashboard } = await import("../views/Dashboard")
    render(<Dashboard onNavigate={vi.fn()} />)
    fireEvent.click(screen.getByText("New Extraction"))
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument())
  })

  it("shows recent cases from API", async () => {
    const { Dashboard } = await import("../views/Dashboard")
    render(<Dashboard onNavigate={vi.fn()} />)
    await waitFor(() =>
      expect(screen.getByText("Test Patient")).toBeInTheDocument(),
    )
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 2. CLINICAL WORKSPACE
// ─────────────────────────────────────────────────────────────────────────────
describe("2. Clinical Workspace view", () => {
  it("renders without crashing", async () => {
    const { ClinicalWorkspace } = await import("../views/ClinicalWorkspace")
    const { container } = render(<ClinicalWorkspace documentId="doc-001" />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows loading spinner initially", async () => {
    const { ClinicalWorkspace } = await import("../views/ClinicalWorkspace")
    render(<ClinicalWorkspace documentId="doc-001" />)
    expect(document.querySelector(".animate-spin")).toBeInTheDocument()
  })

  it("displays patient name after data loads", async () => {
    const { ClinicalWorkspace } = await import("../views/ClinicalWorkspace")
    render(<ClinicalWorkspace documentId="doc-001" />)
    await waitFor(() =>
      expect(screen.getByText("John Smith")).toBeInTheDocument(),
    )
  })

  it("shows error panel with Retry button when API fails", async () => {
    const { fetchDocumentDetails } = await import("../services/api")
    ;(fetchDocumentDetails as any).mockRejectedValueOnce(
      new Error("Server error"),
    )
    const { ClinicalWorkspace } = await import("../views/ClinicalWorkspace")
    render(<ClinicalWorkspace documentId="doc-bad" />)
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument()
      expect(screen.getByText("Retry")).toBeInTheDocument()
    })
  })

  it("shows extracted diagnoses", async () => {
    const { ClinicalWorkspace } = await import("../views/ClinicalWorkspace")
    render(<ClinicalWorkspace documentId="doc-001" />)
    await waitFor(() =>
      expect(screen.getByText("Hypertension")).toBeInTheDocument(),
    )
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 3. REVIEW CENTER
// ─────────────────────────────────────────────────────────────────────────────
describe("3. Review Center view", () => {
  it("renders without crashing", async () => {
    const { ReviewCenter } = await import("../views/ReviewCenter")
    const { container } = render(<ReviewCenter onNavigate={vi.fn()} />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows Review Center heading", async () => {
    const { ReviewCenter } = await import("../views/ReviewCenter")
    render(<ReviewCenter onNavigate={vi.fn()} />)
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /Review Center/i }),
      ).toBeInTheDocument(),
    )
  })

  it("displays queue items from API", async () => {
    const { ReviewCenter } = await import("../views/ReviewCenter")
    render(<ReviewCenter onNavigate={vi.fn()} />)
    await waitFor(() =>
      expect(screen.getAllByText("Hypertension").length).toBeGreaterThan(0),
    )
  })

  it("does NOT call window.alert", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {})
    const { ReviewCenter } = await import("../views/ReviewCenter")
    render(<ReviewCenter onNavigate={vi.fn()} />)
    await new Promise((r) => setTimeout(r, 200))
    expect(alertSpy).not.toHaveBeenCalled()
    alertSpy.mockRestore()
  })

  it("shows inline success feedback after approve", async () => {
    const { ReviewCenter } = await import("../views/ReviewCenter")
    render(<ReviewCenter onNavigate={vi.fn()} initialTaskId="task-001" />)
    await waitFor(() =>
      expect(screen.getByText(/Approve Extraction/i)).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByText(/Approve Extraction/i))
    await waitFor(() => {
      const status = screen.getByRole("status")
      expect(status.textContent).toMatch(/approved/i)
    })
  })

  it("does not show hardcoded badge 60", async () => {
    const { ReviewCenter } = await import("../views/ReviewCenter")
    const { container } = render(<ReviewCenter onNavigate={vi.fn()} />)
    await waitFor(() => expect(container.textContent).not.toMatch(/\b60\b/))
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 4. SETTINGS PAGE
// ─────────────────────────────────────────────────────────────────────────────
describe("4. Settings page", () => {
  it("renders without crashing", async () => {
    const { SettingsPage } = await import("../pages/Settings")
    const { container } = render(<SettingsPage onNavigate={vi.fn()} />)
    expect(container.firstChild).toBeTruthy()
  })

  it('shows "Security Controls" section', async () => {
    const { SettingsPage } = await import("../pages/Settings")
    render(<SettingsPage onNavigate={vi.fn()} />)
    expect(screen.getByText("Security Controls")).toBeInTheDocument()
  })

  it('does NOT contain "HIPAA Compliant"', async () => {
    const { SettingsPage } = await import("../pages/Settings")
    const { container } = render(<SettingsPage onNavigate={vi.fn()} />)
    expect(container.textContent).not.toMatch(/HIPAA Complian/)
  })

  it('does NOT contain "AES-256 Bit Encryption enabled"', async () => {
    const { SettingsPage } = await import("../pages/Settings")
    const { container } = render(<SettingsPage onNavigate={vi.fn()} />)
    expect(container.textContent).not.toMatch(/AES-256 Bit Encryption enabled/)
  })

  it('does NOT contain "TLS 1.3 Transmission Security"', async () => {
    const { SettingsPage } = await import("../pages/Settings")
    const { container } = render(<SettingsPage onNavigate={vi.fn()} />)
    expect(container.textContent).not.toMatch(/TLS 1\.3 Transmission Security/)
  })

  it('shows "Deployment-Managed" badge', async () => {
    const { SettingsPage } = await import("../pages/Settings")
    const { container } = render(<SettingsPage onNavigate={vi.fn()} />)
    expect(container.textContent).toMatch(/Deployment-Managed/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 5. WORKFLOWS PAGE
// ─────────────────────────────────────────────────────────────────────────────
describe("5. Workflows page", () => {
  it("renders without crashing", async () => {
    const { WorkflowsPage } = await import("../pages/Workflows")
    const { container } = render(<WorkflowsPage onNavigate={vi.fn()} />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows the Workflows heading", async () => {
    const { WorkflowsPage } = await import("../pages/Workflows")
    render(<WorkflowsPage onNavigate={vi.fn()} />)
    expect(screen.getByText(/Clinical Workflows/i)).toBeInTheDocument()
  })

  it("renders Document Input node", async () => {
    const { WorkflowsPage } = await import("../pages/Workflows")
    render(<WorkflowsPage onNavigate={vi.fn()} />)
    expect(screen.getByText("Document Input")).toBeInTheDocument()
  })

  it("renders OCR Processing node", async () => {
    const { WorkflowsPage } = await import("../pages/Workflows")
    render(<WorkflowsPage onNavigate={vi.fn()} />)
    expect(screen.getByText("OCR Processing")).toBeInTheDocument()
  })

  it("workflow nodes are accessible buttons with aria-pressed", async () => {
    const { WorkflowsPage } = await import("../pages/Workflows")
    render(<WorkflowsPage onNavigate={vi.fn()} />)
    const nodeBtn = screen.getByRole("button", { name: /Document Input/i })
    expect(nodeBtn.tagName).toBe("BUTTON")
    expect(nodeBtn).toHaveAttribute("aria-pressed")
  })

  it("Test Pipeline shows info banner on click", async () => {
    const { WorkflowsPage } = await import("../pages/Workflows")
    render(<WorkflowsPage onNavigate={vi.fn()} />)
    fireEvent.click(screen.getByRole("button", { name: /Test Pipeline/i }))
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument())
  })

  it("New Workflow shows info banner on click", async () => {
    const { WorkflowsPage } = await import("../pages/Workflows")
    render(<WorkflowsPage onNavigate={vi.fn()} />)
    fireEvent.click(screen.getByRole("button", { name: /New Workflow/i }))
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument())
  })

  it("clicking a node toggles aria-pressed to true", async () => {
    const { WorkflowsPage } = await import("../pages/Workflows")
    render(<WorkflowsPage onNavigate={vi.fn()} />)
    const nodeBtn = screen.getByRole("button", { name: /Document Input/i })
    expect(nodeBtn).toHaveAttribute("aria-pressed", "false")
    fireEvent.click(nodeBtn)
    expect(nodeBtn).toHaveAttribute("aria-pressed", "true")
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 6. DOCUMENTS PAGE
// ─────────────────────────────────────────────────────────────────────────────
describe("6. Documents page", () => {
  it("renders without crashing", async () => {
    const { DocumentsPage } = await import("../pages/Documents")
    const { container } = render(<DocumentsPage onNavigate={vi.fn()} />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows document list from API", async () => {
    const { DocumentsPage } = await import("../pages/Documents")
    const { container } = render(<DocumentsPage onNavigate={vi.fn()} />)
    await waitFor(() => expect(container.textContent).toMatch(/CASE-001/))
  })

  it("shows patient list from API", async () => {
    const { DocumentsPage } = await import("../pages/Documents")
    render(<DocumentsPage onNavigate={vi.fn()} />)
    await waitFor(() =>
      expect(
        screen.getAllByText((t) => t.includes("John Smith")).length,
      ).toBeGreaterThan(0),
    )
  })

  it("does NOT crash when last_updated is undefined", async () => {
    const { fetchDocuments } = await import("../services/api")
    ;(fetchDocuments as any).mockResolvedValueOnce({
      items: [
        {
          id: "doc-999",
          file_name: "no-date.pdf",
          status: "completed",
          case_id: "C-999",
          patient_name: "No Date Patient",
          doc_type: "discharge_summary",
        },
      ],
      total: 1,
      page: 1,
      per_page: 10,
    })
    const { DocumentsPage } = await import("../pages/Documents")
    expect(() => render(<DocumentsPage onNavigate={vi.fn()} />)).not.toThrow()
  })

  it("does NOT crash when doc_type is undefined", async () => {
    const { fetchDocuments } = await import("../services/api")
    ;(fetchDocuments as any).mockResolvedValueOnce({
      items: [
        {
          id: "doc-998",
          file_name: "no-type.pdf",
          status: "completed",
          case_id: "C-998",
          patient_name: "No Type Patient",
          last_updated: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      per_page: 10,
    })
    const { DocumentsPage } = await import("../pages/Documents")
    expect(() => render(<DocumentsPage onNavigate={vi.fn()} />)).not.toThrow()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 7. INTEGRATIONS PAGE
// ─────────────────────────────────────────────────────────────────────────────
describe("7. Integrations page", () => {
  it("renders without crashing", async () => {
    const { IntegrationsPage } = await import("../pages/Integrations")
    const { container } = render(<IntegrationsPage onNavigate={vi.fn()} />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows System Connections heading", async () => {
    const { IntegrationsPage } = await import("../pages/Integrations")
    render(<IntegrationsPage onNavigate={vi.fn()} />)
    expect(screen.getByText("System Connections")).toBeInTheDocument()
  })

  it("shows connection cards", async () => {
    const { IntegrationsPage } = await import("../pages/Integrations")
    render(<IntegrationsPage onNavigate={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByText("Cognate API")).toBeInTheDocument()
      expect(screen.getByText("PostgreSQL")).toBeInTheDocument()
    })
  })

  it("shows FHIR version from API", async () => {
    const { IntegrationsPage } = await import("../pages/Integrations")
    render(<IntegrationsPage onNavigate={vi.fn()} />)
    await waitFor(() =>
      expect(screen.getByText(/FHIR 4\.0\.1/)).toBeInTheDocument(),
    )
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 8. HEADER COMPONENT
// ─────────────────────────────────────────────────────────────────────────────
describe("8. Header component", () => {
  it("renders without crashing", async () => {
    const { Header } = await import("../components/navigation/Header")
    const { container } = render(
      <Header
        onOpenSearch={vi.fn()}
        onToggleMobileNav={vi.fn()}
        onNavigate={vi.fn()}
      />,
    )
    expect(container.firstChild).toBeTruthy()
  })

  it('does NOT show hardcoded "All systems nominal"', async () => {
    const { Header } = await import("../components/navigation/Header")
    const { container } = render(
      <Header
        onOpenSearch={vi.fn()}
        onToggleMobileNav={vi.fn()}
        onNavigate={vi.fn()}
      />,
    )
    expect(container.textContent).not.toMatch(/All systems nominal/)
  })

  it("shows dynamic system status after health check", async () => {
    const { Header } = await import("../components/navigation/Header")
    render(
      <Header
        onOpenSearch={vi.fn()}
        onToggleMobileNav={vi.fn()}
        onNavigate={vi.fn()}
      />,
    )
    await waitFor(() =>
      expect(
        screen.getByText(/operational|degraded|unavailable|Checking/i),
      ).toBeInTheDocument(),
    )
  })

  it("Notifications button has aria-label", async () => {
    const { Header } = await import("../components/navigation/Header")
    render(
      <Header
        onOpenSearch={vi.fn()}
        onToggleMobileNav={vi.fn()}
        onNavigate={vi.fn()}
      />,
    )
    expect(
      screen.getAllByRole("button", { name: /notifications/i }).length,
    ).toBeGreaterThan(0)
  })

  it("Help button has aria-label", async () => {
    const { Header } = await import("../components/navigation/Header")
    render(
      <Header
        onOpenSearch={vi.fn()}
        onToggleMobileNav={vi.fn()}
        onNavigate={vi.fn()}
      />,
    )
    expect(screen.getByRole("button", { name: /help/i })).toBeInTheDocument()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 9. SIDEBAR
// ─────────────────────────────────────────────────────────────────────────────
describe("9. Sidebar navigation", () => {
  it("renders without crashing", async () => {
    const { Sidebar } = await import("../components/navigation/Sidebar")
    const { container } = render(
      <Sidebar activeView="dashboard" onNavigate={vi.fn()} />,
    )
    expect(container.firstChild).toBeTruthy()
  })

  it("shows all main nav items", async () => {
    const { Sidebar } = await import("../components/navigation/Sidebar")
    render(<Sidebar activeView="dashboard" onNavigate={vi.fn()} />)
    expect(
      screen.getByRole("button", { name: /Dashboard/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /Review Center/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /Workflows/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /Settings/i }),
    ).toBeInTheDocument()
  })

  it('does NOT show hardcoded "Dr. Sarah Chen"', async () => {
    const { Sidebar } = await import("../components/navigation/Sidebar")
    const { container } = render(
      <Sidebar activeView="dashboard" onNavigate={vi.fn()} />,
    )
    expect(container.textContent).not.toMatch(/Dr\. Sarah Chen/)
  })

  it("does NOT show hardcoded badge 60", async () => {
    const { Sidebar } = await import("../components/navigation/Sidebar")
    const { container } = render(
      <Sidebar activeView="dashboard" onNavigate={vi.fn()} />,
    )
    await waitFor(() => expect(container.textContent).not.toMatch(/\b60\b/))
  })

  it("shows live badge count from API (8)", async () => {
    const { Sidebar } = await import("../components/navigation/Sidebar")
    render(<Sidebar activeView="dashboard" onNavigate={vi.fn()} />)
    await waitFor(() =>
      expect(screen.getByLabelText(/8 pending reviews/i)).toBeInTheDocument(),
    )
  })

  it('active view gets aria-current="page"', async () => {
    const { Sidebar } = await import("../components/navigation/Sidebar")
    render(<Sidebar activeView="review" onNavigate={vi.fn()} />)
    expect(
      screen.getByRole("button", { name: /Review Center/i }),
    ).toHaveAttribute("aria-current", "page")
  })

  it("nav button calls onNavigate correctly", async () => {
    const { Sidebar } = await import("../components/navigation/Sidebar")
    const onNavigate = vi.fn()
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />)
    fireEvent.click(screen.getByRole("button", { name: /Review Center/i }))
    expect(onNavigate).toHaveBeenCalledWith("review")
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 10. AI OPERATIONS VIEW
// ─────────────────────────────────────────────────────────────────────────────
describe("10. AI Operations view", () => {
  it("renders without crashing", async () => {
    const { AIOperations } = await import("../views/AIOperations")
    const { container } = render(<AIOperations />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows AI Operations heading", async () => {
    const { AIOperations } = await import("../views/AIOperations")
    render(<AIOperations />)
    expect(screen.getByText("AI Operations")).toBeInTheDocument()
  })

  it("shows pipeline health status from API", async () => {
    const { AIOperations } = await import("../views/AIOperations")
    render(<AIOperations />)
    await waitFor(() =>
      expect(screen.getByText(/healthy/i)).toBeInTheDocument(),
    )
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 11. PATIENT TIMELINE VIEW
// ─────────────────────────────────────────────────────────────────────────────
describe("11. Patient Timeline view", () => {
  it("renders without crashing", async () => {
    const { PatientTimeline } = await import("../views/PatientTimeline")
    const { container } = render(<PatientTimeline />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows Clinical Timeline heading", async () => {
    const { PatientTimeline } = await import("../views/PatientTimeline")
    render(<PatientTimeline />)
    expect(screen.getByText(/Clinical Timeline/i)).toBeInTheDocument()
  })

  it("loads patients from API and shows patient name", async () => {
    const { PatientTimeline } = await import("../views/PatientTimeline")
    render(<PatientTimeline />)
    await waitFor(() =>
      expect(screen.getByText(/John Smith/)).toBeInTheDocument(),
    )
  })

  it("loads and shows timeline events", async () => {
    const { PatientTimeline } = await import("../views/PatientTimeline")
    render(<PatientTimeline />)
    await waitFor(() =>
      expect(screen.getByText("Hypertension")).toBeInTheDocument(),
    )
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 12. EXTRACTION PLACEHOLDER VIEW
// ─────────────────────────────────────────────────────────────────────────────
describe("12. AI Extraction placeholder view", () => {
  it("renders without crashing", async () => {
    const { ExtractionView } = await import("../views/Placeholders")
    const { container } = render(<ExtractionView onNavigate={vi.fn()} />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows AI Extraction heading", async () => {
    const { ExtractionView } = await import("../views/Placeholders")
    render(<ExtractionView onNavigate={vi.fn()} />)
    expect(
      screen.getByRole("heading", { name: /AI Extraction/i }),
    ).toBeInTheDocument()
  })

  it("shows navigation cards", async () => {
    const { ExtractionView } = await import("../views/Placeholders")
    render(<ExtractionView onNavigate={vi.fn()} />)
    expect(screen.getByText("Open Documents")).toBeInTheDocument()
    expect(screen.getByText("Open Review Center")).toBeInTheDocument()
  })

  it("action card calls onNavigate with correct view", async () => {
    const { ExtractionView } = await import("../views/Placeholders")
    const onNavigate = vi.fn()
    render(<ExtractionView onNavigate={onNavigate} />)
    fireEvent.click(screen.getByText("Open Review Center"))
    expect(onNavigate).toHaveBeenCalledWith("review")
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 13. ANALYTICS VIEW
// ─────────────────────────────────────────────────────────────────────────────
describe("13. Analytics view", () => {
  it("renders without crashing", async () => {
    const { AnalyticsView } = await import("../views/OperationalViews")
    const { container } = render(<AnalyticsView />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows Analytics heading", async () => {
    const { AnalyticsView } = await import("../views/OperationalViews")
    render(<AnalyticsView />)
    expect(
      screen.getByRole("heading", { name: /Analytics/i }),
    ).toBeInTheDocument()
  })

  it("displays total_jobs from API", async () => {
    const { AnalyticsView } = await import("../views/OperationalViews")
    render(<AnalyticsView />)
    await waitFor(() => expect(screen.getByText("130")).toBeInTheDocument())
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 14. PIPELINE VIEW
// ─────────────────────────────────────────────────────────────────────────────
describe("14. Pipeline view", () => {
  it("renders without crashing", async () => {
    const { PipelineView } = await import("../views/OperationalViews")
    const { container } = render(<PipelineView />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows Data Pipeline heading", async () => {
    const { PipelineView } = await import("../views/OperationalViews")
    render(<PipelineView />)
    expect(
      screen.getByRole("heading", { name: /Pipeline/i }),
    ).toBeInTheDocument()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 15. AUDIT VIEW
// ─────────────────────────────────────────────────────────────────────────────
describe("15. Audit & Compliance view", () => {
  it("renders without crashing", async () => {
    const { AuditView } = await import("../views/OperationalViews")
    const { container } = render(<AuditView />)
    expect(container.firstChild).toBeTruthy()
  })

  it("shows Audit heading", async () => {
    const { AuditView } = await import("../views/OperationalViews")
    render(<AuditView />)
    expect(screen.getByRole("heading", { name: /Audit/i })).toBeInTheDocument()
  })

  it("shows audit events from API", async () => {
    const { AuditView } = await import("../views/OperationalViews")
    render(<AuditView />)
    await waitFor(() =>
      expect(screen.getByText("approved")).toBeInTheDocument(),
    )
  })
})
