import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DocumentsPage } from '../pages/Documents'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('Documents upload and backend processing flow', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends a signature-checked unlinked file and shows the real processing stage response', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = []
    let uploaded = false
    let linked = false
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      requests.push({ url, init })
      if (url.endsWith('/documents/upload')) {
        uploaded = true
        return jsonResponse({ id: 'doc-synthetic-1', status: 'uploaded', review_status: 'not_required', patient_id: null })
      }
      if (url.endsWith('/documents/doc-synthetic-1/process')) {
        return jsonResponse({ job_id: 'job-synthetic-1', document_id: 'doc-synthetic-1', status: 'queued', message: 'Queued' })
      }
      if (url.endsWith('/documents/doc-synthetic-1/patient')) {
        linked = true
        return jsonResponse({ document_id: 'doc-synthetic-1', patient_id: 'patient-synthetic-1' })
      }
      if (url.endsWith('/processing/job-synthetic-1')) {
        return jsonResponse({
          job_id: 'job-synthetic-1', document_id: 'doc-synthetic-1', status: 'completed',
          pipeline_version: 'test-pipeline', warning_count: 0,
          steps: [{ id: 'step-1', step_name: 'ocr', status: 'completed' }],
        })
      }
      if (url.includes('/documents?')) return jsonResponse({
        items: uploaded ? [{
          id: 'doc-synthetic-1', case_id: 'CL-SYNTH', file_name: 'synthetic.pdf',
          patient_id: linked ? 'patient-synthetic-1' : null,
          patient_name: linked ? 'Synthetic Patient' : null,
          mrn: linked ? 'MRN-SYNTHETIC' : null, doc_type: 'synthetic_note',
          status: 'processing', review_status: 'not_required', confidence: 'not_available', last_updated: '2026-01-01T00:00:00Z',
        }] : [], total: uploaded ? 1 : 0, page: 1, page_size: 25, has_next: false,
      })
      if (url.includes('/patients?')) return jsonResponse({ items: [{
        id: 'patient-synthetic-1', external_patient_id: null, mrn: 'MRN-SYNTHETIC',
        first_name: 'Synthetic', last_name: 'Patient', gender: null, dob: null,
      }], total: 1, page: 1, page_size: 100, has_next: false })
      if (url.endsWith('/review/stats')) return jsonResponse({ pending: 0, high_priority: 0, approved: 0, rejected: 0 })
      if (url.endsWith('/health')) return jsonResponse({ status: 'ok', service: 'synthetic-test', database: 'available' })
      return jsonResponse({ items: [], total: 0, pending_count: 0, documents: [], patients: [], findings: [] })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<DocumentsPage onNavigate={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Upload Document' }))
    const file = new File(['%PDF-1.7 synthetic'], 'synthetic.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText(/document file/i), { target: { files: [file] } })
    await screen.findByText(/synthetic\.pdf/)
    fireEvent.submit(screen.getByLabelText(/document file/i).closest('form')!)
    await waitFor(() => expect(requests.map(({ url }) => url)).toContain('/api/v1/documents/upload'))
    await waitFor(() => expect(requests.map(({ url }) => url)).toContain('/api/v1/documents/doc-synthetic-1/process'))
    const upload = requests.find(({ url }) => url.endsWith('/documents/upload'))
    expect(upload?.init?.body).toBeInstanceOf(FormData)
    expect((upload?.init?.body as FormData).get('file')).toBeInstanceOf(File)
    expect((upload?.init?.body as FormData).has('patient_id')).toBe(false)
    expect(await screen.findByText('No patient linked')).toBeInTheDocument()
    expect(screen.getByText('Approval blocked until patient is linked.')).toBeInTheDocument()
    expect(await screen.findByText('Reading text')).toBeInTheDocument()
    expect(screen.getByText(/Section-finding is not reported as a separate backend stage/)).toBeInTheDocument()

    fireEvent.change(screen.getByRole('combobox', { name: 'Patient to link for CL-SYNTH' }), { target: { value: 'patient-synthetic-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Link patient' }))
    await screen.findByText('Synthetic Patient')
    const linkRequest = requests.find(({ url }) => url.endsWith('/documents/doc-synthetic-1/patient'))
    expect(JSON.parse(String(linkRequest?.init?.body))).toEqual({ patient_id: 'patient-synthetic-1' })
  })
})
