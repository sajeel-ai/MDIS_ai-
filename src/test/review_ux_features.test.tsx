import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ReviewCenter } from '../views/ReviewCenter';

// Mock API
vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
    fetchCurrentUser: vi.fn().mockResolvedValue({ id: 'user-admin', role: 'admin', name: 'Admin' }),
    fetchReviewStats: vi.fn().mockResolvedValue({ pending: 5, high_priority: 2, approved: 10, rejected: 1 }),
    fetchReviewPolicy: vi.fn().mockResolvedValue({ auto_approve_threshold: 0.95, require_comment_on_reject: false }),
    fetchReviewQueue: vi.fn().mockResolvedValue({
      items: [
        {
          id: 'task-test-01',
          document_id: 'doc-test-01',
          priority: 'high',
          status: 'pending',
          reason: 'Needs review',
          entity: {
            id: 'ent-01',
            raw_text: 'Type 2 Diabetes Mellitus',
            normalized_value: 'Type 2 Diabetes Mellitus',
            confidence: 0.96,
            entity_type: 'diagnosis',
          },
          patient: { id: 'pat-01', display_name: 'John Doe', mrn: 'MRN-001' },
          document: { id: 'doc-test-01', file_name: 'clinic_note.pdf', patient_id: 'pat-01' },
          validation_results: [],
        },
      ],
      total: 1,
      page: 1,
      per_page: 50,
    }),
    fetchReviewTaskDetail: vi.fn().mockResolvedValue({
      id: 'task-test-01',
      document_id: 'doc-test-01',
      priority: 'high',
      status: 'pending',
      reason: 'Needs review',
      entity: {
        id: 'ent-01',
        raw_text: 'Type 2 Diabetes Mellitus',
        normalized_value: 'Type 2 Diabetes Mellitus',
        confidence: 0.96,
        entity_type: 'diagnosis',
      },
      patient: { id: 'pat-01', display_name: 'John Doe', mrn: 'MRN-001' },
      document: { id: 'doc-test-01', file_name: 'clinic_note.pdf', patient_id: 'pat-01' },
      evidence: { text: 'Patient diagnosed with Type 2 Diabetes Mellitus' },
      decision: null,
      pipeline_stages: [],
      validation_results: [],
    }),
    startReviewTask: vi.fn().mockResolvedValue({
      id: 'task-test-01',
      document_id: 'doc-test-01',
      priority: 'high',
      status: 'pending',
      reason: 'Needs review',
      entity: {
        id: 'ent-01',
        raw_text: 'Type 2 Diabetes Mellitus',
        normalized_value: 'Type 2 Diabetes Mellitus',
        confidence: 0.96,
        entity_type: 'diagnosis',
      },
      patient: { id: 'pat-01', display_name: 'John Doe', mrn: 'MRN-001' },
      document: { id: 'doc-test-01', file_name: 'clinic_note.pdf', patient_id: 'pat-01' },
      evidence: { text: 'Patient diagnosed with Type 2 Diabetes Mellitus' },
      decision: null,
      pipeline_stages: [],
      validation_results: [],
    }),
    approveReviewTask: vi.fn().mockResolvedValue({ id: 'task-test-01', status: 'approved' }),
    approveCleanReviewItems: vi.fn().mockResolvedValue({ approved_count: 1 }),
  };
});

describe('Review UX Enhancements — Item 5', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('persists status filter to sessionStorage when filter changes', async () => {
    render(<ReviewCenter onNavigate={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('In Review')).toBeInTheDocument());

    fireEvent.click(screen.getByText('In Review'));
    expect(sessionStorage.getItem('mdis_review_status_filter')).toBe('in_review');
  });

  it('restores status filter from sessionStorage on mount', async () => {
    sessionStorage.setItem('mdis_review_status_filter', 'approved');
    render(<ReviewCenter onNavigate={vi.fn()} />);

    await waitFor(() => {
      const approvedBtn = screen.getByRole('button', { name: /^approved$/i });
      // Active filter has bg-[#071A3D] text-white class
      expect(approvedBtn.className).toContain('text-white');
    });
  });

  it('shows live diff view when reviewer enters correction mode', async () => {
    render(<ReviewCenter onNavigate={vi.fn()} initialTaskId="task-test-01" detailOnly={true} />);

    await waitFor(() => expect(screen.getAllByText(/Type 2 Diabetes Mellitus/i).length).toBeGreaterThan(0));

    // Click Correct button on normalized term
    const correctBtns = screen.getAllByRole('button', { name: /Correct/i });
    fireEvent.click(correctBtns[0]);

    // Diff view box should appear
    await waitFor(() => expect(screen.getByTestId('correction-diff-view')).toBeInTheDocument());
    expect(screen.getByText('Correction Diff')).toBeInTheDocument();

    // Type a proposed correction
    const input = screen.getByPlaceholderText(/Enter clinician corrected value/i);
    fireEvent.change(input, { target: { value: 'T2D with Neuropathy' } });

    // The proposed correction should be visible in diff
    expect(screen.getByText('T2D with Neuropathy')).toBeInTheDocument();
  });
});
