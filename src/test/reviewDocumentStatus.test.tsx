/**
 * reviewDocumentStatus.test.tsx
 *
 * Fix 1 regression tests:
 *  1. When task.status = in_review but document.review_status = approved,
 *     the header card shows APPROVED (not IN_REVIEW).
 *  2. Opening an approved document in detail mode shows no IN_REVIEW card
 *     in the header strip.
 *
 * NOTE: sandbox runs are UNVERIFIED — the user runs vitest in their terminal.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ── Mock api module ──────────────────────────────────────────────────────────
vi.mock('../services/api', async (importActual) => {
  const actual = await importActual<typeof import('../services/api')>()

  const approvedTask = {
    id: 'task-1',
    document_id: 'doc-1',
    entity_id: null,
    priority: 'normal',
    reason: 'Review required',
    status: 'in_review',        // task-level status is still in_review
    assigned_to: null,
    created_at: '2024-01-01T00:00:00Z',
    started_at: null,
    completed_at: null,
    decision: null,
    comment: null,
    document: {
      id: 'doc-1',
      file_name: 'clinic_note.pdf',
      document_type: 'clinical_note',
      created_at: '2024-01-01T00:00:00Z',
      review_status: 'approved',   // document-level status is approved
    },
    patient: {
      id: 'pat-1',
      display_name: 'Jane Doe',
      mrn: 'MRN-001',
    },
    entity: null,
    evidence: null,
    validation: null,
    validation_results: [],
    source_text: null,
  }

  return {
    ...actual,
    fetchReviewQueue: vi.fn().mockResolvedValue({
      items: [approvedTask],
      total: 1,
      page: 1,
      page_size: 50,
      has_next: false,
    }),
    fetchReviewTaskDetail: vi.fn().mockResolvedValue(approvedTask),
    startReviewTask: vi.fn().mockResolvedValue(approvedTask),
    fetchReviewStats: vi.fn().mockResolvedValue({
      pending: 0,
      high_priority: 0,
      approved: 1,
      rejected: 0,
    }),
    fetchReviewPolicy: vi.fn().mockResolvedValue({ policy: 'manual', confidence_threshold: 0.85, high_priority_threshold: 0.5 }),
    fetchCurrentUser: vi.fn().mockResolvedValue({ id: 'u1', email: 'r@example.com', display_name: 'Reviewer', role: 'reviewer' }),
    approveReviewTask: vi.fn().mockResolvedValue(approvedTask),
    rejectReviewTask: vi.fn().mockResolvedValue(approvedTask),
    correctReviewTask: vi.fn().mockResolvedValue(approvedTask),
    approveCleanReviewItems: vi.fn().mockResolvedValue({ approved_count: 0 }),
  }
})

import { ReviewCenter } from '../views/ReviewCenter'

describe('Fix 1 – Header card status uses document.review_status', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows APPROVED on header card when task.status=in_review but document.review_status=approved', async () => {
    render(
      <ReviewCenter
        detailOnly
        initialTaskId="task-1"
        fromStatus="approved"
      />,
    )

    const headerNav = await screen.findByRole('navigation', { name: /review documents/i })
    const buttons = within(headerNav).getAllByRole('button')

    // Find the card for clinic_note.pdf
    const targetCard = buttons.find((btn) => btn.textContent?.includes('clinic_note.pdf'))
    expect(targetCard).toBeDefined()

    // Must show approved, not in_review
    expect(within(targetCard!).getByText(/approved/i)).toBeInTheDocument()
    expect(within(targetCard!).queryByText(/in_review/i)).not.toBeInTheDocument()
  })

  it('opening an approved document in detail mode shows no IN_REVIEW card in header strip', async () => {
    render(
      <ReviewCenter
        detailOnly
        initialTaskId="task-1"
        fromStatus="approved"
      />,
    )

    const headerNav = await screen.findByRole('navigation', { name: /review documents/i })
    const buttons = within(headerNav).getAllByRole('button')

    expect(buttons.length).toBeGreaterThan(0)
    for (const card of buttons) {
      // No card should display "in_review"
      expect(within(card).queryByText(/in_review/i)).not.toBeInTheDocument()
    }
  })
})

