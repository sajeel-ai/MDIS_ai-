import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ReviewWorkspace } from '../components/review/ReviewWorkspace'
import { isReviewWorkspaceEnabled } from '../config/featureFlags'

const entity = {
  id: 'entity-1', extraction_id: 'extraction-1', entity_type: 'diagnosis',
  raw_text: 'Asthma', normalized_value: 'Asthma', confidence: 0.91,
  assertion: 'present', section: 'ASSESSMENT', status: 'unreviewed',
  experiencer: 'patient', temporality: 'current', exclusion_reason: null,
  ocr_confidence: 0.88, extraction_confidence: 0.91, group: 'confirmed-active',
  source: 'ai_extracted', version: 2, validation_rule_codes: [],
  evidence_spans: [{ id: 'span-1', entity_id: 'entity-1', start_offset: 0, end_offset: 6,
    exact_text: 'Asthma', page_number: 1, bbox: [0.1, 0.2, 0.4, 0.3] }],
}

const baseTask = {
  id: 'task-1', document_id: 'doc-1', entity_id: entity.id, priority: 'normal',
  reason: 'Human review required', status: 'pending', assigned_to: 'reviewer-1',
  created_at: '2026-01-01T00:00:00Z', completed_at: null, decision: null, comment: null,
  version: 3, decision_actor: null, decision_at: null,
  document: { id: 'doc-1', file_name: 'synthetic-note.pdf', document_type: 'progress_note', review_status: 'pending' },
  patient: { id: 'patient-1', display_name: 'Synthetic patient', mrn: 'SYN-001' },
  entity,
  evidence: { id: 'span-1', text: 'Asthma', start_offset: 0, end_offset: 6, page_number: 1, bbox: [0.1, 0.2, 0.4, 0.3] },
  validation_results: [], source_text: 'Asthma',
}

let requests: Array<{ url: string; init?: RequestInit }> = []
let forceConflict = false

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  requests = []
  forceConflict = false
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    requests.push({ url, init })
    if (url.endsWith('/review/task-1')) return jsonResponse(baseTask)
      if (url.includes('/review/queue')) return jsonResponse({ items: [baseTask], total: 1, page: 1, page_size: 100, has_next: false })
    if (url.endsWith('/review/policy')) return jsonResponse({ policy: 'all', confidence_threshold: 0.85, high_priority_threshold: 0.5 })
    if (url.endsWith('/documents/doc-1/entities')) return jsonResponse([entity])
    if (url.endsWith('/documents/doc-1')) return jsonResponse({ ...baseTask.document, page_count: 1, mime_type: 'application/pdf' })
    if (url.endsWith('/documents/doc-1/pages/1/image')) return new Response(new Blob(['synthetic image']), { status: 200 })
    if (url.endsWith('/review/entities/entity-1/edit') && forceConflict) return jsonResponse({ detail: 'Entity changed' }, 409)
    if (url.includes('/review/')) return jsonResponse({ ...baseTask, entity: { ...entity, version: 3 } })
    return jsonResponse({ detail: 'Not found' }, 404)
  }))
  const NativeURL = globalThis.URL
  vi.stubGlobal('URL', class extends NativeURL {
    static createObjectURL = () => 'blob:synthetic-page'
    static revokeObjectURL = vi.fn()
  })
})

describe('Review workspace', () => {
  it('keeps the new workspace feature flag off unless explicitly enabled', () => {
    vi.stubEnv('VITE_ENABLE_REVIEW_WORKSPACE', 'false')
    expect(isReviewWorkspaceEnabled()).toBe(false)
  })

  it('renders all six groups, source label, confidence, and unavailable highlight state', async () => {
    const noBoxTask = { ...baseTask, entity: { ...entity, ocr_confidence: null, extraction_confidence: null, confidence: null, evidence_spans: [] }, evidence: null }
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/review/task-1')) return jsonResponse(noBoxTask)
      if (url.includes('/review/queue')) return jsonResponse({ items: [noBoxTask], total: 1, page: 1, page_size: 100, has_next: false })
      if (url.endsWith('/review/policy')) return jsonResponse({ policy: 'all', confidence_threshold: 0.85, high_priority_threshold: 0.5 })
      if (url.endsWith('/documents/doc-1/entities')) return jsonResponse([{ ...noBoxTask.entity, evidence_spans: [] }])
      if (url.endsWith('/documents/doc-1')) return jsonResponse({ ...baseTask.document, page_count: 1 })
      if (url.endsWith('/documents/doc-1/pages/1/image')) return new Response(new Blob(['image']))
      return jsonResponse({})
    })
    render(<ReviewWorkspace initialTaskId="task-1" />)
    expect(await screen.findByText(/Confirmed active/)).toBeInTheDocument()
    expect(screen.getByText(/Historical \/ resolved/)).toBeInTheDocument()
    expect(screen.getByText(/Family history/)).toBeInTheDocument()
    expect(screen.getByText(/Denied \/ ruled out/)).toBeInTheDocument()
    expect(screen.getByText(/Uncertain \/ needs review/)).toBeInTheDocument()
    expect(screen.getByText(/Instructions \/ conditional/)).toBeInTheDocument()
    expect(screen.getByText(/Evidence highlighting unavailable for this item/i)).toBeInTheDocument()
    expect(screen.getByText(/Confidence: not available/)).toBeInTheDocument()
    expect(screen.getAllByText('AI extracted').length).toBeGreaterThan(0)
  })

  it('selects from a source highlight and shows tabs for narrow layouts', async () => {
    render(<ReviewWorkspace initialTaskId="task-1" />)
    fireEvent.click(await screen.findByTestId('source-box-entity-1'))
    expect(screen.getByTestId('entity-card-entity-1')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('tab', { name: 'Document' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Findings' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Flags' })).toBeInTheDocument()
  })

  it('sends the entity version and proposed value when saving an edit', async () => {
    render(<ReviewWorkspace initialTaskId="task-1" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    expect(screen.getByTestId('edit-diff')).toHaveTextContent('Asthma')
    fireEvent.change(screen.getByLabelText('Proposed value'), { target: { value: 'Asthma, mild' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(requests.some((request) => request.url.endsWith('/review/entities/entity-1/edit'))).toBe(true))
    const request = requests.find((item) => item.url.endsWith('/review/entities/entity-1/edit'))
    expect(JSON.parse(String(request?.init?.body))).toEqual({ expected_version: 2, normalized_value: 'Asthma, mild' })
  })

  it('persists comment, reject, and undo through their API endpoints', async () => {
    render(<ReviewWorkspace initialTaskId="task-1" />)
    await screen.findByTestId('entity-card-entity-1')

    fireEvent.change(screen.getByLabelText('Comment'), { target: { value: 'Reviewed note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    await waitFor(() => expect(requests.some((request) => request.url.endsWith('/review/entities/entity-1/comment'))).toBe(true))
    const comment = requests.find((request) => request.url.endsWith('/review/entities/entity-1/comment'))
    expect(JSON.parse(String(comment?.init?.body))).toEqual({ expected_version: 2, comment: 'Reviewed note' })

    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))
    await waitFor(() => expect(requests.some((request) => request.url.endsWith('/review/entities/entity-1/reject'))).toBe(true))
    const reject = requests.find((request) => request.url.endsWith('/review/entities/entity-1/reject'))
    expect(JSON.parse(String(reject?.init?.body))).toEqual({ expected_version: 2 })

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(requests.some((request) => request.url.endsWith('/review/entities/entity-1/undo'))).toBe(true))
    const undo = requests.find((request) => request.url.endsWith('/review/entities/entity-1/undo'))
    expect(JSON.parse(String(undo?.init?.body))).toEqual({ expected_version: 2 })
  })

  it('requires override reason and sends approval through the decision endpoint', async () => {
    const flaggedTask = { ...baseTask, validation_results: [{ rule_code: 'DRUG_INTERACTION', severity: 'critical', status: 'warning', message: 'Review interaction' }] }
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      requests.push({ url, init })
      if (url.endsWith('/review/task-1')) return jsonResponse(flaggedTask)
      if (url.includes('/review/queue')) return jsonResponse({ items: [flaggedTask], total: 1, page: 1, page_size: 100, has_next: false })
      if (url.endsWith('/review/policy')) return jsonResponse({ policy: 'all', confidence_threshold: 0.85, high_priority_threshold: 0.5 })
      if (url.endsWith('/documents/doc-1/entities')) return jsonResponse([entity])
      if (url.endsWith('/documents/doc-1')) return jsonResponse({ ...baseTask.document, page_count: 1 })
      if (url.endsWith('/documents/doc-1/pages/1/image')) return new Response(new Blob(['image']))
      return jsonResponse({ ...flaggedTask, status: 'approved' })
    })
    render(<ReviewWorkspace initialTaskId="task-1" />)
    const approve = await screen.findByRole('button', { name: 'Accept' })
    expect(approve).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Written override reason/i), { target: { value: 'Reviewed by clinician' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /acknowledge critical or conflict/i }))
    expect(approve).toBeEnabled()
    fireEvent.click(approve)
    await waitFor(() => expect(requests.some((request) => request.url.includes('/review/task-1/decision')), JSON.stringify(requests.map((request) => request.url))).toBe(true))
    const request = requests.find((item) => item.url.endsWith('/review/task-1/decision'))
    expect(JSON.parse(String(request?.init?.body))).toMatchObject({ decision: 'approved', expected_version: 3, justification: 'Reviewed by clinician' })
  })

  it('shows a reload action for stale edit conflicts and documents unavailable add-item action', async () => {
    forceConflict = true
    render(<ReviewWorkspace initialTaskId="task-1" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('Proposed value'), { target: { value: 'Asthma' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/changed|conflict/i)
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add missing item/i })).toBeDisabled()
    expect(screen.getByText(/not available.*reviewer-added/i)).toBeInTheDocument()
  })

  it('opens the keyboard shortcut help with ?', async () => {
    render(<ReviewWorkspace initialTaskId="task-1" />)
    await screen.findByTestId('entity-card-entity-1')
    fireEvent.keyDown(window, { key: '?' })
    expect(screen.getByRole('dialog', { name: /keyboard shortcuts/i })).toBeInTheDocument()
  })
})
