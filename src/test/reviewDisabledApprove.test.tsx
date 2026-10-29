/**
 * reviewDisabledApprove.test.tsx
 *
 * Clinical Safety Tests:
 * 1. Approve button is disabled with a visible reason when document has no linked patient.
 * 2. Approve button is disabled when med/lab validation flags are present until an override justification is provided.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { unlinkedTask, flaggedTask, lowConfidenceTask } = vi.hoisted(() => {
  const unlinked = {
    id: 'task-unlinked',
    document_id: 'doc-unlinked',
    entity_id: 'ent-1',
    priority: 'normal',
    reason: 'Normal review',
    status: 'pending',
    assigned_to: null,
    created_at: '2024-01-01T00:00:00Z',
    started_at: null,
    completed_at: null,
    decision: null,
    comment: null,
    document: {
      id: 'doc-unlinked',
      file_name: 'unlinked_doc.pdf',
      document_type: 'clinical_note',
      created_at: '2024-01-01T00:00:00Z',
      review_status: 'pending',
    },
    patient: null, // UNLINKED PATIENT
    entity: {
      id: 'ent-1',
      type: 'diagnosis',
      raw_text: 'Asthma',
      normalized_value: 'Asthma',
      confidence: 0.95,
      assertion: 'present',
      section: null,
      status: 'unreviewed',
      details: null,
      original_ai_value: null,
    },
    evidence: null,
    validation: null,
    validation_results: [],
    source_text: 'Patient has asthma.',
  }

  const flagged = {
    id: 'task-flagged',
    document_id: 'doc-flagged',
    entity_id: 'ent-2',
    priority: 'high',
    reason: 'Lab validation flag',
    status: 'pending',
    assigned_to: null,
    created_at: '2024-01-01T00:00:00Z',
    started_at: null,
    completed_at: null,
    decision: null,
    comment: null,
    document: {
      id: 'doc-flagged',
      file_name: 'flagged_doc.pdf',
      document_type: 'clinical_note',
      created_at: '2024-01-01T00:00:00Z',
      review_status: 'pending',
    },
    patient: {
      id: 'pat-1',
      display_name: 'John Doe',
      mrn: 'MRN-002',
    },
    entity: {
      id: 'ent-2',
      type: 'lab',
      raw_text: 'Potassium 6.8',
      normalized_value: 'Potassium',
      confidence: 0.95,
      assertion: 'present',
      section: null,
      status: 'unreviewed',
      details: null,
      original_ai_value: null,
    },
    evidence: null,
    validation: {
      rule_code: 'LAB_VALUE_UNIT',
      severity: 'warning',
      status: 'fail',
      message: 'Lab value missing unit.',
    },
    validation_results: [
      {
        rule_code: 'LAB_VALUE_UNIT',
        severity: 'warning',
        status: 'fail',
        message: 'Lab value missing unit.',
      },
    ],
    source_text: 'Potassium 6.8',
  }

  const lowConfidence = {
    ...flagged,
    id: 'task-low-confidence',
    entity: { ...flagged.entity, confidence: 0.4 },
    validation: null,
    validation_results: [],
  }

  return { unlinkedTask: unlinked, flaggedTask: flagged, lowConfidenceTask: lowConfidence }
})

vi.mock('../services/api', async (importActual) => {
  const actual = await importActual<typeof import('../services/api')>()
  return {
    ...actual,
    fetchReviewQueue: vi.fn().mockResolvedValue({
      items: [unlinkedTask, flaggedTask, lowConfidenceTask],
      total: 2,
      page: 1,
      page_size: 50,
      has_next: false,
    }),
    fetchReviewTaskDetail: vi.fn().mockImplementation((id: string) => {
      return Promise.resolve(id === 'task-flagged' ? flaggedTask : id === 'task-low-confidence' ? lowConfidenceTask : unlinkedTask)
    }),
    startReviewTask: vi.fn().mockImplementation((id: string) => {
      return Promise.resolve(id === 'task-flagged' ? flaggedTask : id === 'task-low-confidence' ? lowConfidenceTask : unlinkedTask)
    }),
    fetchReviewStats: vi.fn().mockResolvedValue({
      pending: 1,
      high_priority: 0,
      approved: 0,
      rejected: 0,
    }),
    fetchReviewPolicy: vi.fn().mockResolvedValue({
      policy: 'manual',
      confidence_threshold: 0.85,
      high_priority_threshold: 0.5,
    }),
    fetchCurrentUser: vi.fn().mockResolvedValue({
      id: 'u1',
      email: 'r@example.com',
      display_name: 'Reviewer',
      role: 'reviewer',
    }),
    approveReviewTask: vi.fn().mockResolvedValue(unlinkedTask),
    rejectReviewTask: vi.fn().mockResolvedValue(unlinkedTask),
    correctReviewTask: vi.fn().mockResolvedValue(unlinkedTask),
    approveCleanReviewItems: vi.fn().mockResolvedValue({ approved_count: 0 }),
  }
})

import { ReviewCenter } from '../views/ReviewCenter'

describe('Clinical Safety: Approve button disabled state & override justification', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('disables Approve button with visible reason when document has no linked patient', async () => {
    render(<ReviewCenter detailOnly initialTaskId="task-unlinked" />)

    // Approve button should be disabled
    const approveBtn = await screen.findByRole('button', { name: /approve extraction/i })
    expect(approveBtn).toBeDisabled()

    // Must show visible reason explaining patient linkage is required
    expect(screen.getByText(/cannot approve.*patient/i)).toBeInTheDocument()
  })

  it('requires justification to override medication/lab validation flags', async () => {
    render(<ReviewCenter detailOnly initialTaskId="task-flagged" />)

    const approveBtn = await screen.findByRole('button', { name: /approve extraction/i })
    
    // Initially disabled because justification is required
    expect(approveBtn).toBeDisabled()
    expect(screen.getByText(/justification required/i)).toBeInTheDocument()

    // Justification textarea must be present
    const justificationInput = screen.getByPlaceholderText(/state clinical reason for overriding/i)
    expect(justificationInput).toBeInTheDocument()
    await waitFor(() => expect(justificationInput).toBeEnabled())

    // Once user provides justification, Approve button is enabled
    fireEvent.change(justificationInput, {
      target: { value: 'Confirmed hyperkalemia clinically consistent with hemolysis artifact.' },
    })

    await waitFor(() => expect(approveBtn).toBeEnabled())
  })

  it('blocks batch approval when the selected finding has any validation flag', async () => {
    render(<ReviewCenter detailOnly initialTaskId="task-flagged" />)
    expect(await screen.findByRole('button', { name: /approve clean items/i })).toBeDisabled()
  })

  it('blocks batch approval when confidence is below the configured threshold', async () => {
    render(<ReviewCenter detailOnly initialTaskId="task-low-confidence" />)
    const button = await screen.findByRole('button', { name: /approve clean items/i })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', expect.stringMatching(/confidence is below/i))
  })
})
