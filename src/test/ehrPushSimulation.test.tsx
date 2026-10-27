import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApprovedFilesPage } from '../pages/ApprovedFiles'
import { fetchDocuments, fetchFHIRMetadata, fetchReviewQueue, pushSyntheticFHIR } from '../services/api'

vi.mock('../layouts/AppLayout', () => ({
  AppLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>()
  return {
    ...actual,
    fetchDocuments: vi.fn(),
    fetchFHIRMetadata: vi.fn(),
    fetchReviewQueue: vi.fn(),
    pushSyntheticFHIR: vi.fn(),
  }
})

describe('EHR push simulation labeling', () => {
  beforeEach(() => {
    vi.mocked(fetchDocuments).mockResolvedValue({
      items: [{ id: 'doc-1', case_id: 'CL-1', file_name: 'synthetic.pdf', patient_name: 'Test Patient', mrn: null, doc_type: 'progress_note', status: 'approved', confidence: 'high', last_updated: '2026-10-01T00:00:00Z' }],
      total: 1, page: 1, page_size: 100, has_next: false,
    })
    vi.mocked(fetchFHIRMetadata).mockResolvedValue({ configured: true, reachable: true, fhir_version: 'R4', resource: null })
    vi.mocked(fetchReviewQueue).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, has_next: false })
    vi.mocked(pushSyntheticFHIR).mockResolvedValue({ document_id: 'doc-1', status: 'success', simulation: true, mode: 'simulation', smart_on_fhir_configured: false })
  })

  it('labels the UI feedback as Simulation when the API reports simulation mode', async () => {
    render(<ApprovedFilesPage onNavigate={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /Test push \(Simulation\)/i }))
    expect(await screen.findByRole('status')).toHaveTextContent('Simulation')
    expect(pushSyntheticFHIR).toHaveBeenCalledWith('doc-1')
  })
})
