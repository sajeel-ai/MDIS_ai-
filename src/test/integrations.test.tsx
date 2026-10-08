import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { IntegrationsPage } from "../pages/Integrations"
import { ApiError, fetchAIOpsHealth, fetchFHIRMetadata } from "../services/api"

vi.mock("../layouts/AppLayout", () => ({
  AppLayout: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}))

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>()
  return {
    ...actual,
    fetchAIOpsHealth: vi.fn(),
    fetchFHIRMetadata: vi.fn(),
  }
})

const healthyResponse = {
  status: "healthy",
  active_jobs: 0,
  avg_confidence: null,
  pipeline: "Not measured",
}

describe("Integrations page health status", () => {
  beforeEach(() => {
    vi.mocked(fetchAIOpsHealth).mockResolvedValue(healthyResponse)
    vi.mocked(fetchFHIRMetadata).mockResolvedValue({
      configured: true,
      reachable: true,
      resource: { resourceType: "CapabilityStatement", fhirVersion: "4.0.1" },
    })
  })

  it("shows connected status when health returns 200", async () => {
    render(<IntegrationsPage onNavigate={vi.fn()} />)

    expect(await screen.findAllByText("Connected")).toHaveLength(3)
    expect(screen.getByText("healthy")).toBeInTheDocument()
  })

  it("shows access restricted when health returns 403", async () => {
    vi.mocked(fetchAIOpsHealth).mockRejectedValueOnce(
      new ApiError(403, "User lacks required role: ['admin', 'operator']"),
    )
    render(<IntegrationsPage onNavigate={vi.fn()} />)

    expect(
      await screen.findAllByText("Access restricted (admin/operator only)"),
    ).toHaveLength(3)
    expect(screen.getAllByText("Connected")).toHaveLength(1)
  })

  it("shows unavailable when health returns a server failure", async () => {
    vi.mocked(fetchAIOpsHealth).mockRejectedValueOnce(
      new ApiError(500, "Internal Server Error"),
    )
    render(<IntegrationsPage onNavigate={vi.fn()} />)

    expect(await screen.findAllByText("Unavailable")).toHaveLength(3)
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Service error (HTTP 500). Please retry.",
    )
  })

  it("shows unavailable when the health request has a network failure", async () => {
    vi.mocked(fetchAIOpsHealth).mockRejectedValueOnce(
      new Error("Network error"),
    )
    render(<IntegrationsPage onNavigate={vi.fn()} />)

    expect(await screen.findAllByText("Unavailable")).toHaveLength(3)
  })

  it("loads FHIR metadata and displays its reachable server status", async () => {
    render(<IntegrationsPage onNavigate={vi.fn()} />)

    expect(
      await screen.findByText("FHIR R4 export (base-resource validated)"),
    ).toBeInTheDocument()
    expect(await screen.findByText("FHIR 4.0.1")).toBeInTheDocument()
    expect(fetchFHIRMetadata).toHaveBeenCalledOnce()
  })
})
