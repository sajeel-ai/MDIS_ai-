import React, { useEffect, useState } from 'react';
import {
  fetchReviewQueue,
  fetchReviewTaskDetail,
  fetchCurrentUser,
  startReviewTask,
  fetchReviewStats,
  approveReviewTask,
  rejectReviewTask,
  correctReviewTask,
  approveCleanReviewItems,
  fetchReviewPolicy,
  type ReviewTask,
  type ReviewStats,
  type ReviewPolicy,
  type DocumentReviewSummary,
  safeApiErrorMessage,
} from '../services/api';
import {
  CheckCircle2,
  XCircle,
  Edit3,
  Search,
  RefreshCw,
  AlertTriangle,
  FileText,
  User,
  ShieldAlert,
  ChevronRight,
  ArrowLeft,
  Sparkles,
  Database,
} from 'lucide-react';

export type ReviewStatus = 'all' | 'pending' | 'in_review' | 'approved' | 'rejected' | 'corrected' | 'escalated';

export function resolveDocumentReviewStatus(
  document?: DocumentReviewSummary | null,
  items: ReviewTask[] = [],
): string {
  const docStatus = document?.review_status?.toLowerCase();
  if (docStatus && ['pending', 'in_review', 'approved', 'rejected', 'escalated'].includes(docStatus)) {
    return docStatus;
  }
  if (!items.length) return 'unknown';
  if (items.some((item) => item.status === 'pending')) return 'pending';
  if (items.some((item) => item.status === 'in_review')) return 'in_review';
  if (items.some((item) => item.status === 'rejected')) return 'rejected';
  if (items.every((item) => item.status === 'approved')) return 'approved';
  if (items.some((item) => item.status === 'corrected')) return 'corrected';
  return 'unknown';
}

export interface ReviewCenterProps {
  onNavigate?: (view: string, documentId?: string, reviewTaskId?: string, fromStatus?: string | null) => void;
  initialTaskId?: string | null;
  detailOnly?: boolean;
  fromStatus?: string | null;
}

const PriorityBadge = ({ priority }: { priority: string }) => {
  const isHigh = priority?.toLowerCase() === 'high';
  return (
    <span className="inline-flex items-center gap-1.5 text-[#52627A] text-[10px] font-mono font-semibold uppercase tracking-wider">
      <span className={`w-1.5 h-1.5 rounded-full ${isHigh ? 'bg-[#d97706]' : 'bg-[#146EF5]'}`} />
      {priority}
    </span>
  );
};

const StatusBadge = ({ status }: { status: string }) => {
  const map: Record<string, { bg: string; text: string }> = {
    pending: { bg: 'bg-amber-50 border-amber-200', text: 'text-amber-700' },
    in_review: { bg: 'bg-[#EAF5FF] border-[#DCE7F3]', text: 'text-[#146EF5]' },
    approved: { bg: 'bg-emerald-50 border-emerald-200', text: 'text-emerald-700' },
    rejected: { bg: 'bg-rose-50 border-rose-200', text: 'text-rose-700' },
    corrected: { bg: 'bg-[#EAF5FF] border-[#DCE7F3]', text: 'text-[#071A3D]' },
  };
  const s = map[status] || map.pending;
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono font-medium border uppercase ${s.bg} ${s.text}`}>
      {status}
    </span>
  );
};

export function ReviewCenter({ onNavigate, initialTaskId, detailOnly = false, fromStatus }: ReviewCenterProps) {
  // Validate fromStatus to prevent injection of arbitrary values into query
  const validFromStatus = fromStatus && ['pending', 'in_review', 'approved', 'rejected', 'escalated'].includes(fromStatus) ? fromStatus : null;
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [stats, setStats] = useState<ReviewStats>({
    pending: 0,
    high_priority: 0,
    approved: 0,
    rejected: 0,
  });
  const [loading, setLoading] = useState(true);
  const [reviewPolicy, setReviewPolicy] = useState<ReviewPolicy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentUserRole, setCurrentUserRole] = useState<string | null>(null);

  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(initialTaskId || null);
  const [mobilePanel, setMobilePanel] = useState<'source' | 'extraction' | 'decision'>('source');
  const [detailTask, setDetailTask] = useState<ReviewTask | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const canReview = currentUserRole === 'reviewer' || currentUserRole === 'admin';

  // Filters
  const initialFilters = new URLSearchParams(window.location.search);
  const getInitialStatusFilter = () => {
    if (initialTaskId) return 'all';
    const saved = initialFilters.get('status');
    if (saved && ['pending', 'in_review', 'approved', 'rejected', 'all'].includes(saved)) return saved;
    return 'pending';
  };
  const [statusFilter, setStatusFilter] = useState(getInitialStatusFilter);

  const [priorityFilter, setPriorityFilter] = useState(() => {
    const priority = initialFilters.get('priority');
    return priority && ['all', 'high', 'medium', 'normal'].includes(priority) ? priority : 'all';
  });
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    const params = new URLSearchParams();
    params.set('status', statusFilter);
    params.set('priority', priorityFilter);
    window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`);
  }, [statusFilter, priorityFilter]);

  // Action States
  const [submitting, setSubmitting] = useState(false);
  const [commentInput, setCommentInput] = useState('');
  const [correctionMode, setCorrectionMode] = useState(false);
  const [correctedValueInput, setCorrectedValueInput] = useState('');
  const [rejectReasonInput, setRejectReasonInput] = useState('');
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [conflictAcknowledged, setConflictAcknowledged] = useState(false);
  const [justificationInput, setJustificationInput] = useState('');
  // Inline action feedback — replaces browser alert()
  const [actionFeedback, setActionFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const showFeedback = (type: 'success' | 'error', message: string) => {
    setActionFeedback({ type, message });
    setTimeout(() => setActionFeedback(null), 5000);
  };

  const loadData = async (targetDocumentId?: string) => {
    setLoading(true);
    setError(null);
    try {
      const [queueRes, statsRes] = await Promise.all([
        fetchReviewQueue(1, 50, priorityFilter, validFromStatus || statusFilter, searchQuery, targetDocumentId),
        fetchReviewStats(),
      ]);

      setTasks(queueRes.items || []);
      setStats(statsRes);

      if (detailOnly && initialTaskId) {
        setSelectedTaskId(initialTaskId);
      } else if (queueRes.items.length > 0) {
        if (!selectedTaskId || !queueRes.items.some((t) => t.id === selectedTaskId)) {
          setSelectedTaskId(queueRes.items[0].id);
        }
      } else {
        setSelectedTaskId(null);
        setDetailTask(null);
      }
    } catch (err: any) {
      setError(safeApiErrorMessage(err, 'Access restricted (admin/operator only)'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // In detailOnly mode without a status context the header cards are loaded
    // after the task detail resolves (see the selectedTaskId effect below).
    if (detailOnly && !validFromStatus) return;
    loadData();
  }, [statusFilter, priorityFilter, detailOnly, validFromStatus]);

  useEffect(() => {
    fetchReviewPolicy().then(setReviewPolicy).catch(() => setReviewPolicy(null));
    fetchCurrentUser().then((user) => setCurrentUserRole(user.role)).catch(() => setCurrentUserRole(null));
  }, []);

  // The detail route can change while this component stays mounted. Keep the
  // selected task in sync so clicking another document refreshes the panels.
  useEffect(() => {
    if (detailOnly && initialTaskId) {
      setSelectedTaskId(initialTaskId);
    }
  }, [detailOnly, initialTaskId]);

  // Handle search debouncing / trigger
  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadData();
  };

  // Load single task detail with full source text when selection changes
  useEffect(() => {
    if (!selectedTaskId) {
      setDetailTask(null);
      return;
    }
    let isSubscribed = true;
    setDetailLoading(true);
    const loadTaskDetails = canReview
      ? startReviewTask(selectedTaskId)
      : fetchReviewTaskDetail(selectedTaskId);
    loadTaskDetails
      .then((t) => {
        if (isSubscribed) {
          setDetailTask(t);
          setTasks((items) => items.map((item) => item.id === t.id ? { ...item, status: t.status } : item));
          setCorrectedValueInput(t.entity?.normalized_value || t.entity?.raw_text || '');
          setCommentInput('');
          setCorrectionMode(false);
          // In detailOnly mode without a list context, derive the document from
          // the loaded task and fetch ONLY tasks for that document.
          if (detailOnly && !validFromStatus && t.document_id) {
            loadData(t.document_id);
          }
        }
      })
      .catch((err) => {
        const message = safeApiErrorMessage(err, 'Access restricted (admin/operator only)');
        showFeedback('error', message);
      })
      .finally(() => {
        if (isSubscribed) setDetailLoading(false);
      });

    return () => {
      isSubscribed = false;
    };
  }, [detailOnly, selectedTaskId, canReview]);

  // Shared post-action refresh: reload the list (scoped by document in detailOnly mode)
  // and refresh the detail task so status badges update immediately.
  const refreshAfterAction = async (targetTaskId?: string) => {
    const taskId = targetTaskId || selectedTaskId || undefined;
    const docId = detailTask?.document_id;
    await loadData(detailOnly && !validFromStatus && docId ? docId : undefined);
    if (taskId) {
      try {
        const refreshed = await fetchReviewTaskDetail(taskId);
        setDetailTask(refreshed);
      } catch {
        // handled gracefully
      }
    }
  };

  // Actions
  useEffect(() => {
    setConflictAcknowledged(false);
    setJustificationInput('');
  }, [selectedTaskId]);

  const hasLinkedPatient = !!(detailTask?.patient?.id || detailTask?.patient?.mrn);
  const allValidationResults = detailTask?.validation_results || [];
  const singleValidationRule = detailTask?.validation?.rule_code;

  const hasConflict =
    allValidationResults.some(
      (v) =>
        ['CONFLICT', 'CRITICAL'].includes((v.rule_code || '').toUpperCase()) ||
        (v.severity || '').toLowerCase() === 'critical'
    ) || ['CONFLICT', 'CRITICAL'].includes((singleValidationRule || '').toUpperCase());

  const hasMedOrLabFlag =
    allValidationResults.some((v) =>
      ['MED_DOSE_UNIT', 'LAB_VALUE_UNIT', 'DRUG_INTERACTION', 'ABNORMAL_LAB'].includes(
        (v.rule_code || '').toUpperCase()
      )
    ) ||
    ['MED_DOSE_UNIT', 'LAB_VALUE_UNIT', 'DRUG_INTERACTION', 'ABNORMAL_LAB'].includes(
      (singleValidationRule || '').toUpperCase()
    );

  const hasAnyBatchValidationFlag = allValidationResults.length > 0 || Boolean(singleValidationRule);
  const belowBatchConfidenceThreshold = Boolean(
    detailTask?.entity && (detailTask.entity.source === 'reviewer_added' || detailTask.entity.confidence == null || (reviewPolicy && detailTask.entity.confidence < reviewPolicy.confidence_threshold))
  );
  const batchApprovalDisabledReason = !hasLinkedPatient
    ? 'Cannot batch approve: document has no linked patient record.'
    : hasAnyBatchValidationFlag
      ? 'Cannot batch approve: validation flags require manual review.'
      : belowBatchConfidenceThreshold
        ? detailTask?.entity?.source === 'reviewer_added'
          ? 'Cannot batch approve: reviewer-added findings require individual review.'
          : detailTask?.entity?.confidence == null
            ? 'Cannot batch approve: confidence is not available.'
            : 'Cannot batch approve: confidence is below the review threshold.'
        : null;

  let approvalDisabledReason: string | null = null;
  if (detailTask) {
    if (!hasLinkedPatient) {
      approvalDisabledReason = 'Cannot approve: document has no linked patient record.';
    } else if (hasConflict && !conflictAcknowledged) {
      approvalDisabledReason =
        'Cannot approve: unacknowledged conflict validation flag. Please review and acknowledge below.';
    } else if (hasMedOrLabFlag && !justificationInput.trim()) {
      approvalDisabledReason = 'Override justification required for medication or lab validation flags.';
    }
  }

  const handleApprove = async () => {
    if (!selectedTaskId || !canReview) return;
    setSubmitting(true);
    if (approvalDisabledReason) return;
    try {
      await approveReviewTask(
        selectedTaskId,
        commentInput || undefined,
        conflictAcknowledged,
        justificationInput.trim() || undefined
      );
      showFeedback('success', 'Document approved successfully.');
      await refreshAfterAction(selectedTaskId);
    } catch (err: any) {
      showFeedback('error', safeApiErrorMessage(err, 'Unable to approve the document. Please try again.'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRejectConfirm = async () => {
    if (!selectedTaskId || !canReview) return;
    setSubmitting(true);
    try {
      await rejectReviewTask(selectedTaskId, rejectReasonInput || undefined);
      showFeedback('success', 'Document rejected and recorded in audit log.');
      setShowRejectModal(false);
      setRejectReasonInput('');
      await refreshAfterAction(selectedTaskId);
    } catch (err: any) {
      showFeedback('error', 'Unable to reject the document. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCorrectSubmit = async () => {
    if (!selectedTaskId || !canReview || !correctedValueInput.trim()) return;
    setSubmitting(true);
    try {
      await correctReviewTask(selectedTaskId, correctedValueInput.trim(), commentInput || undefined);
      showFeedback('success', 'Correction saved and recorded in audit log.');
      setCorrectionMode(false);
      await refreshAfterAction(selectedTaskId);
    } catch (err: any) {
      showFeedback('error', 'Unable to save the correction. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSkip = () => {
    if (!tasks.length || !selectedTaskId) return;
    const currentIndex = tasks.findIndex((t) => t.id === selectedTaskId);
    const nextTask = tasks[(currentIndex + 1) % tasks.length];
    if (nextTask) {
      setSelectedTaskId(nextTask.id);
    }
  };

  // Helper to render source document text with highlighted evidence span
  const renderSourceDocumentExcerpt = () => {
    if (!detailTask) return null;
    const fullText = detailTask.source_text;
    const ev = detailTask.evidence;

    if (!fullText) {
      return (
        <div className="p-4 text-center text-xs text-[#52627A] italic">
          No document OCR source text available.
        </div>
      );
    }

    if (!ev || ev.start_offset === undefined || ev.end_offset === undefined || ev.start_offset >= ev.end_offset) {
      return (
        <div className="p-3 bg-white border border-[#DCE7F3] rounded-md text-xs font-mono text-[#071A3D] whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto">
          {fullText}
        </div>
      );
    }

    const before = fullText.slice(0, ev.start_offset);
    const match = fullText.slice(ev.start_offset, ev.end_offset);
    const after = fullText.slice(ev.end_offset);

    return (
      <div className="p-3 bg-white border border-[#DCE7F3] rounded-md font-mono text-xs text-[#071A3D] whitespace-pre-wrap leading-relaxed max-h-[420px] overflow-y-auto">
        <span>{before}</span>
        <mark className="bg-amber-200 text-amber-900 px-1 py-0.5 rounded font-semibold border-b-2 border-amber-500">
          {match || ev.text}
        </mark>
        <span>{after}</span>
      </div>
    );
  };

  const handleApproveCleanItems = async () => {
    if (!canReview || !detailTask?.document_id) return;
    setSubmitting(true);
    try {
      const result = await approveCleanReviewItems(detailTask.document_id);
      showFeedback('success', `Approved clean items: ${result.approved_count}.`);
      await refreshAfterAction(selectedTaskId ?? undefined);
    } catch {
      showFeedback('error', 'Unable to approve clean items. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const queueDocuments = Array.from(
    tasks.reduce((groups, task) => {
      const group = groups.get(task.document_id) || [];
      group.push(task);
      groups.set(task.document_id, group);
      return groups;
    }, new Map<string, ReviewTask[]>()).entries(),
  ).map(([documentId, items]) => {
    const activeTask = items.find((item) => item.status === 'pending')
      || items.find((item) => item.status === 'in_review')
      || items[0];
    const status = resolveDocumentReviewStatus(activeTask.document, items);
    const priority = items.some((item) => item.priority === 'high')
      ? 'high'
      : items.some((item) => item.priority === 'medium')
        ? 'medium'
        : 'normal';
    return { documentId, items, activeTask, status, priority };
  });
  const selectedQueueDocument = queueDocuments.find((group) =>
    group.items.some((item) => item.id === selectedTaskId),
  );

  return (
    <div className="flex min-h-full min-w-0 flex-1 flex-col overflow-x-hidden bg-[#F5FAFF] md:h-full md:overflow-y-hidden">
      {/* Inline action feedback banner — replaces browser alert() */}
      {actionFeedback && (
        <div
          role="status"
          aria-live="polite"
          className={`flex items-center gap-3 px-4 py-3 text-xs font-medium border-b ${
            actionFeedback.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-red-50 border-red-200 text-red-800'
          }`}
        >
          {actionFeedback.type === 'success'
            ? <CheckCircle2 size={15} className="flex-shrink-0" aria-hidden="true" />
            : <AlertTriangle size={15} className="flex-shrink-0" aria-hidden="true" />}
          {actionFeedback.message}
        </div>
      )}

      {detailOnly && (
        <div className="flex-shrink-0 border-b border-[#DCE7F3] bg-white px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => onNavigate?.('review')}
                className="inline-flex items-center gap-1 rounded-md border border-[#DCE7F3] px-2.5 py-1.5 text-xs font-semibold text-[#146EF5] hover:bg-[#EAF5FF]"
              >
                <ArrowLeft size={14} /> Back to Review Center
              </button>
              <div>
                <div className="text-sm font-bold text-[#071A3D]">Review document</div>
                <div className="text-[11px] text-[#52627A]">Select a document to update the review panels</div>
              </div>
            </div>
            <span className="font-mono text-[10px] uppercase tracking-wider text-[#52627A]">
              {queueDocuments.length} document{queueDocuments.length === 1 ? '' : 's'}
            </span>
          </div>
          <nav aria-label="Review documents" className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {queueDocuments.map((group) => {
              const task = group.activeTask;
              const active = group.items.some((item) => item.id === selectedTaskId);
              return (
                <button
                  key={task.id}
                  type="button"
                  onClick={() => onNavigate?.('review-document', undefined, task.id, validFromStatus || statusFilter || undefined)}
                  aria-current={active ? 'page' : undefined}
                  className={`min-w-[13rem] max-w-[18rem] shrink-0 rounded-lg border px-3 py-2 text-left transition-colors ${
                    active
                      ? 'border-[#146EF5] bg-[#EAF5FF]'
                      : 'border-[#DCE7F3] bg-white hover:bg-[#F5FAFF]'
                  }`}
                >
                  <div className="truncate text-xs font-semibold text-[#071A3D]">
                    {task.document?.file_name || 'Untitled document'}
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-[#52627A]">
                    <span className="truncate">{task.patient?.display_name || 'Patient unavailable'}</span>
                    <StatusBadge status={group.status} />
                  </div>
                </button>
              );
            })}
          </nav>
        </div>
      )}

      {/* Top Header & Operational Metrics (queue view only) */}
      {!detailOnly && <div className="bg-white border-b border-[#DCE7F3] px-4 sm:px-6 py-4 flex-shrink-0 page-header-edge page-header-edge-inset page-header-edge-pad-4 page-header-edge-pad-sm-6">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-sans text-lg sm:text-xl font-bold text-[#071A3D]">Review Center</h1>
              <span className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                <Database size={12} /> PostgreSQL Direct
              </span>
            </div>
            <p className="font-sans text-xs text-[#52627A] mt-0.5">
              Human validation and audit of AI-extracted clinical entities and evidence provenance
            </p>
          </div>

          {/* Metric Summary Cards */}
          <div className="grid w-full grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3 lg:w-auto">
            <div className="px-3 py-2 bg-[#F5FAFF] border border-[#DCE7F3] rounded-lg">
              <div className="text-[10px] font-mono font-medium text-[#52627A] uppercase">Pending Docs</div>
              <div className="text-lg font-bold font-mono text-[#071A3D]">{stats.pending}</div>
            </div>
            <div className="px-3 py-2 bg-red-50/60 border border-red-200/80 rounded-lg">
              <div className="text-[10px] font-mono font-medium text-red-600 uppercase">High Priority Docs</div>
              <div className="text-lg font-bold font-mono text-red-700">{stats.high_priority}</div>
            </div>
            <div className="px-3 py-2 bg-emerald-50/60 border border-emerald-200/80 rounded-lg">
              <div className="text-[10px] font-mono font-medium text-emerald-600 uppercase">Approved Docs</div>
              <div className="text-lg font-bold font-mono text-emerald-700">{stats.approved}</div>
            </div>
            <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg">
              <div className="text-[10px] font-mono font-medium text-slate-500 uppercase">Rejected/Corrected Docs</div>
              <div className="text-lg font-bold font-mono text-slate-700">{stats.rejected}</div>
            </div>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="mt-4 flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 border-t border-[#EAF5FF]">
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
            <span className="text-xs font-medium text-[#52627A] mr-1">Status:</span>
            {['pending', 'in_review', 'approved', 'rejected', 'all'].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-3 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                  statusFilter === st
                    ? 'bg-[#071A3D] text-white'
                    : 'bg-[#EAF5FF] text-[#52627A] hover:bg-[#DCE7F3]'
                }`}
              >
                  {st === 'in_review' ? 'In Review' : st}
              </button>
            ))}

            <div className="h-4 w-[1px] bg-[#DCE7F3] mx-1" />

            <span className="text-xs font-medium text-[#52627A] mr-1">Priority:</span>
            {['all', 'high', 'medium', 'normal'].map((pr) => (
              <button
                key={pr}
                onClick={() => setPriorityFilter(pr)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                  priorityFilter === pr
                    ? 'bg-[#146EF5] text-white'
                    : 'bg-[#EAF5FF] text-[#52627A] hover:bg-[#DCE7F3]'
                }`}
              >
                {pr}
              </button>
            ))}
          </div>

          <form onSubmit={handleSearchSubmit} className="flex items-center gap-2 w-full sm:w-72">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-2.5 top-2.5 text-[#52627A]" />
              <input
                type="text"
                placeholder="Search patient, doc, entity..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 bg-[#F5FAFF] border border-[#DCE7F3] rounded-md text-xs text-[#071A3D] outline-none focus:border-[#146EF5]"
              />
            </div>
            <button
              type="button"
              onClick={() => loadData()}
              className="p-2 text-[#52627A] hover:text-[#071A3D] hover:bg-[#EAF5FF] rounded-md transition-colors"
              title="Refresh queue"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
          </form>
        </div>
      </div>}

      {/* Main Workspace Body */}
      <div className="flex min-h-[30rem] flex-1 flex-col overflow-visible md:min-h-0 md:flex-row md:overflow-hidden">
        {/* Left Queue Panel */}
        {!detailOnly && <div
          className={`flex min-h-[20rem] w-full flex-col border-r border-[#DCE7F3] bg-white flex-shrink-0 md:min-h-0 ${
            queueDocuments.length === 0 ? 'md:w-full md:border-r-0' : 'md:w-80 lg:w-96'
          } ${
            selectedTaskId ? 'hidden md:flex' : 'flex'
          }`}
        >
          <div className="px-4 py-2.5 bg-[#F5FAFF] border-b border-[#DCE7F3] flex items-center justify-between">
            <span className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider">
              Documents · {queueDocuments.length}
            </span>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto divide-y divide-[#EAF5FF]">
            {loading ? (
              <div className="p-4 space-y-3">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-16 bg-[#EAF5FF] animate-pulse rounded-lg" />
                ))}
              </div>
            ) : error ? (
              <div className="p-6 text-center">
                <AlertTriangle size={24} className="text-amber-500 mx-auto mb-2" />
                <div className="font-sans text-xs font-semibold text-[#071A3D]">Unable to load review tasks</div>
                <div className="text-[11px] text-[#52627A] mt-1">{error}</div>
                <button
                  onClick={() => loadData()}
                  className="mt-3 px-3 py-1.5 bg-[#146EF5] text-white text-xs font-medium rounded-md hover:bg-[#146EF5]"
                >
                  Retry
                </button>
              </div>
            ) : queueDocuments.length === 0 ? (
              <div className="p-8 text-center">
                <CheckCircle2 size={32} className="text-emerald-500 mx-auto mb-2" />
                <div className="font-sans text-sm font-semibold text-[#071A3D]">No review tasks</div>
                <div className="text-xs text-[#52627A] mt-1 leading-relaxed">
                  No extracted entities require review matching current filters. Processed clinical entities will appear here after document processing.
                </div>
              </div>
            ) : (
              queueDocuments.map((group) => {
                const t = group.activeTask;
                const isSelected = group.items.some((item) => item.id === selectedTaskId);
                const patientName = t.patient?.display_name || 'Patient';
                const docName = t.document?.file_name || 'Document';

                return (
                  <button
                    key={t.id}
                    onClick={() => detailOnly
                      ? onNavigate?.('review-document', undefined, t.id, validFromStatus || statusFilter || undefined)
                      : setSelectedTaskId(t.id)}
                    aria-pressed={isSelected}
                    aria-label={`Review document: ${docName} — ${patientName}, ${group.items.length} clinical findings`}
                    className={`w-full p-4 text-left transition-colors flex flex-col gap-1.5 ${
                      isSelected
                        ? 'bg-blue-50/70 border-l-4 border-l-[#146EF5]'
                        : 'bg-white hover:bg-[#F5FAFF]'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <PriorityBadge priority={group.priority} />
                      <StatusBadge status={group.status} />
                    </div>

                    <div className="font-sans text-xs font-bold text-[#071A3D] truncate mt-0.5">
                      {docName}
                    </div>

                    <div className="flex items-center justify-between gap-2 text-[11px] text-[#52627A]">
                      <span className="truncate">{patientName}</span>
                      <span className="shrink-0 font-mono">{group.items.length} finding{group.items.length === 1 ? '' : 's'}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>}

        {/* Queue preview: the main page stays a simple two-panel document browser. */}
        {!detailOnly && (
          <div className={`min-w-0 flex-1 bg-white ${selectedQueueDocument ? 'flex' : 'hidden md:flex'} flex-col`}>
            {selectedQueueDocument ? (
              <>
                <div className="border-b border-[#DCE7F3] bg-[#F5FAFF] px-5 py-4 sm:px-6">
                  <button
                    type="button"
                    onClick={() => setSelectedTaskId(null)}
                    className="mb-3 inline-flex items-center gap-1 text-xs font-semibold text-[#146EF5] md:hidden"
                  >
                    <ArrowLeft size={14} /> Back to documents
                  </button>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-[#071A3D]">
                        <FileText size={15} className="shrink-0 text-[#146EF5]" />
                        Document preview
                      </div>
                      <h2 className="mt-2 truncate text-base font-bold text-[#071A3D]">
                        {selectedQueueDocument.activeTask.document?.file_name || 'Untitled document'}
                      </h2>
                      <p className="mt-1 text-xs text-[#52627A]">
                        {selectedQueueDocument.activeTask.document?.document_type || 'Clinical document'}
                        {' · '}{selectedQueueDocument.activeTask.patient?.display_name || 'Patient unavailable'}
                      </p>
                    </div>
                    <StatusBadge status={selectedQueueDocument.status} />
                  </div>
                </div>
                <div className="flex flex-1 flex-col items-center justify-center p-6 text-center sm:p-10">
                  <FileText size={42} className="text-[#146EF5]" aria-hidden="true" />
                  <h3 className="mt-4 text-sm font-semibold text-[#071A3D]">Ready for review</h3>
                  <p className="mt-2 max-w-md text-xs leading-relaxed text-[#52627A]">
                    This document has {selectedQueueDocument.items.length} clinical finding{selectedQueueDocument.items.length === 1 ? '' : 's'}.
                    Open the full review page to inspect the source, AI extraction, and human decision panels.
                  </p>
                  {selectedQueueDocument.items.length > 0 && (
                    <div className="mt-4 flex max-w-md flex-wrap justify-center gap-1.5">
                      {selectedQueueDocument.items.map((item) => (
                        <span key={item.id} className="rounded-md border border-[#DCE7F3] bg-[#EAF5FF] px-2 py-0.5 text-xs font-medium text-[#071A3D]">
                          {item.entity?.normalized_value || item.entity?.raw_text || 'Clinical finding'}
                        </span>
                      ))}
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => onNavigate?.('review-document', undefined, selectedQueueDocument.activeTask.id, validFromStatus || statusFilter || undefined)}
                    className="mt-5 rounded-md bg-[#146EF5] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#0f5dcc]"
                  >
                    Open full review
                  </button>
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center p-8 text-center">
                <div>
                  <FileText size={36} className="mx-auto text-[#9BB4D2]" aria-hidden="true" />
                  <h3 className="mt-3 text-sm font-semibold text-[#071A3D]">Select a document</h3>
                  <p className="mt-1 text-xs text-[#52627A]">Choose a document from the list to preview it here.</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Right Detail Workspace (full review page only) */}
        <div className={`min-w-0 flex-1 flex-col overflow-visible bg-white md:overflow-hidden ${
          !detailOnly
            ? 'hidden'
            : !loading && queueDocuments.length === 0
            ? 'hidden'
            : selectedTaskId
              ? 'flex'
              : 'hidden md:flex'
        }`}>
          {detailLoading ? (
            <div className="flex-1 flex items-center justify-center p-8 text-[#52627A] text-xs font-mono">
              <RefreshCw size={18} className="animate-spin mr-2" /> Loading review task details...
            </div>
          ) : detailTask ? (
            <div className="min-w-0 flex-1 flex flex-col overflow-visible md:flex-row md:overflow-hidden">
              {/* Mobile Back Button */}
              <div className="md:hidden px-4 py-2 bg-[#F5FAFF] border-b border-[#DCE7F3]">
                <button
                  onClick={() => detailOnly ? onNavigate?.('review') : setSelectedTaskId(null)}
                  className="flex items-center gap-1 text-xs text-[#146EF5] font-semibold"
                >
                  <ArrowLeft size={14} /> Back to Queue
                </button>
                {detailOnly && (
                  <nav aria-label="Review sections" className="mt-3 grid grid-cols-3 gap-1 rounded-lg bg-white p-1 border border-[#DCE7F3]">
                    {([['source', 'Source'], ['extraction', 'Extraction'], ['decision', 'Decision']] as const).map(([panel, label]) => (
                      <button
                        key={panel}
                        type="button"
                        onClick={() => setMobilePanel(panel)}
                        aria-current={mobilePanel === panel ? 'page' : undefined}
                        className={`min-h-10 rounded-md px-2 text-[11px] font-semibold ${mobilePanel === panel ? 'bg-[#146EF5] text-white' : 'text-[#52627A]'}`}
                      >
                        {label}
                      </button>
                    ))}
                  </nav>
                )}
              </div>

              {/* Panel 1: Source Document & Provenance (35% width on desktop) */}
              <div className={`${detailOnly && mobilePanel !== 'source' ? 'hidden md:flex' : 'flex'} w-full shrink-0 md:min-h-0 md:w-[38%] md:shrink border-b md:border-b-0 md:border-r border-[#DCE7F3] flex-col bg-[#F5FAFF] overflow-visible md:overflow-hidden`}>
                <div className="px-4 py-3 bg-white border-b border-[#DCE7F3] flex items-center justify-between">
                  <div>
                    <div className="font-sans text-xs font-bold text-[#071A3D] flex items-center gap-1.5">
                      <FileText size={14} className="text-[#146EF5]" /> SOURCE DOCUMENT
                    </div>
                    <div className="font-mono text-[10px] text-[#52627A]">
                      {detailTask.document?.file_name} · {detailTask.document?.document_type}
                    </div>
                  </div>
                  {detailTask.patient && (
                    <div className="text-right">
                      <div className="font-sans text-xs font-semibold text-[#071A3D]">
                        {detailTask.patient.display_name}
                      </div>
                      <div className="font-mono text-[10px] text-[#52627A]">MRN: {detailTask.patient.mrn}</div>
                    </div>
                  )}
                </div>

                <div className="flex-none p-4 space-y-3 md:min-h-0 md:flex-1 md:overflow-y-auto">
                  {/* Validation Reason Card */}
                  <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-lg">
                    <div className="flex items-center gap-1.5 text-amber-800 text-[11px] font-semibold font-mono uppercase">
                      <ShieldAlert size={14} /> Validation Flag
                    </div>
                    <p className="text-xs text-amber-900 mt-1 leading-relaxed">
                      {detailTask.reason}
                    </p>
                    {detailTask.validation?.message && (
                      <div className="text-[11px] text-amber-700 mt-1 italic">
                        Rule note: {detailTask.validation.message}
                      </div>
                    )}
                    {!!detailTask.validation_results?.length && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {detailTask.validation_results.map((validation, index) => (
                          <span key={`${validation.rule_code}-${index}`} className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] text-amber-900">
                            {validation.rule_code || 'VALIDATION'}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Document Raw OCR Text Excerpt */}
                  <div>
                    <div className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider mb-1.5 flex items-center justify-between">
                      <span>OCR Document Text</span>
                      {detailTask.evidence && (
                        <span>Page {detailTask.evidence.page_number}</span>
                      )}
                    </div>
                    {renderSourceDocumentExcerpt()}
                  </div>
                </div>
              </div>

              {/* Panel 2: AI Extraction & Entity Details (34% width on desktop) */}
              <div className={`${detailOnly && mobilePanel !== 'extraction' ? 'hidden md:flex' : 'flex'} w-full shrink-0 md:min-h-0 md:w-[34%] md:shrink border-b md:border-b-0 md:border-r border-[#DCE7F3] flex-col bg-white overflow-visible md:overflow-hidden`}>
                <div className="px-4 py-3 bg-[#F5FAFF] border-b border-[#DCE7F3]">
                  <div className="font-sans text-xs font-bold text-[#071A3D] flex items-center gap-1.5">
                    <Sparkles size={14} className="text-[#146EF5]" /> AI EXTRACTION DETAILS
                  </div>
                  <div className="font-mono text-[10px] text-[#146EF5]">Model: Cognate Clinical NLP v1</div>
                </div>

                <div className="flex-none p-4 space-y-4 md:min-h-0 md:flex-1 md:overflow-y-auto">
                  {detailTask.entity ? (
                    <>
                      <div className="p-3 bg-[#F5FAFF] border border-[#DCE7F3] rounded-lg">
                        <div className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider mb-1">
                          Entity Type: {detailTask.entity.type}
                        </div>
                        <div className="font-sans text-sm font-semibold text-[#071A3D]">
                          {detailTask.entity.raw_text}
                        </div>
                        {detailTask.entity.type === 'medication' && (detailTask.entity.details?.dose || detailTask.entity.details?.frequency || detailTask.entity.details?.route) && (
                          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
                            {detailTask.entity.details?.dose && (
                              <div>
                                <div className="font-mono text-[9px] uppercase tracking-wider text-[#52627A]">Dose</div>
                                <div className="text-xs font-semibold text-[#071A3D]">{String(detailTask.entity.details.dose)}</div>
                              </div>
                            )}
                            {detailTask.entity.details?.frequency && (
                              <div>
                                <div className="font-mono text-[9px] uppercase tracking-wider text-[#52627A]">Frequency</div>
                                <div className="text-xs font-semibold text-[#071A3D]">{String(detailTask.entity.details.frequency)}</div>
                              </div>
                            )}
                            {detailTask.entity.details?.route && (
                              <div>
                                <div className="font-mono text-[9px] uppercase tracking-wider text-[#52627A]">Route</div>
                                <div className="text-xs font-semibold text-[#071A3D]">{String(detailTask.entity.details.route)}</div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Normalized Term */}
                      <div className="p-3 bg-white border border-[#DCE7F3] rounded-lg">
                        <div className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider mb-1">
                          Normalized Term (SNOMED/ICD-10)
                        </div>
                        {correctionMode ? (
                          <div className="mt-2 space-y-2">
                            <input
                              type="text"
                              value={correctedValueInput}
                              onChange={(e) => setCorrectedValueInput(e.target.value)}
                              disabled={!canReview}
                              className="w-full px-2.5 py-1.5 text-xs font-sans border border-[#DCE7F3] rounded outline-none focus:ring-1 focus:ring-[#146EF5]"
                              placeholder="Enter clinician corrected value..."
                            />
                            {/* Live Correction Diff View */}
                            <div className="p-2.5 rounded bg-[#F8FAFC] border border-[#E2E8F0] space-y-1 text-xs" data-testid="correction-diff-view">
                              <div className="text-[10px] font-semibold text-[#64748B] uppercase tracking-wider">
                                Correction Diff
                              </div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-[11px] font-medium text-rose-700 bg-rose-50 px-2 py-0.5 rounded line-through border border-rose-200">
                                  {detailTask.entity.raw_text || detailTask.entity.normalized_value}
                                </span>
                                <span className="text-slate-400 font-bold">→</span>
                                <span className="text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                                  {correctedValueInput.trim() || '(empty)'}
                                </span>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={handleCorrectSubmit}
                                disabled={!canReview || submitting || !correctedValueInput.trim()}
                                className="px-3 py-1 bg-[#146EF5] text-white text-xs font-medium rounded hover:bg-[#146EF5] disabled:opacity-50"
                              >
                                Save Correction
                              </button>
                              <button
                                onClick={() => setCorrectionMode(false)}
                                className="px-2 py-1 text-xs text-[#52627A] hover:underline"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center justify-between">
                            <div className="font-sans text-xs text-[#071A3D] font-medium">
                              {detailTask.entity.normalized_value || detailTask.entity.raw_text}
                            </div>
                            <button
                              onClick={() => setCorrectionMode(true)}
                              disabled={!canReview}
                              title={canReview ? undefined : 'Review decisions require the reviewer or admin role.'}
                              className="flex items-center gap-1 text-[11px] text-[#146EF5] font-medium hover:underline"
                            >
                              <Edit3 size={12} /> Correct
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Confidence Level */}
                      <div className="p-3 bg-[#EAF5FF]/50 border border-[#DCE7F3] rounded-lg">
                        <div className="font-mono text-[10px] text-[#071A3D] uppercase tracking-wider mb-1.5">
                          Model confidence (uncalibrated)
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-mono font-bold text-[#071A3D]">
                            {detailTask.entity.confidence == null ? 'not available' : `${Math.round(detailTask.entity.confidence * 100)}%`}
                          </span>
                          <span className={`text-[11px] font-semibold ${detailTask.entity.confidence != null && reviewPolicy && detailTask.entity.confidence >= reviewPolicy.confidence_threshold ? 'text-emerald-700' : 'text-amber-700'}`}>
                            {detailTask.entity.confidence == null ? 'Confidence not available' : reviewPolicy && detailTask.entity.confidence >= reviewPolicy.confidence_threshold ? 'At or above review threshold' : 'Review threshold flag'}
                          </span>
                        </div>
                        <div className="w-full bg-[#DCE7F3] h-1.5 rounded-full mt-2 overflow-hidden">
                          <div
                            className={`h-full ${detailTask.entity.confidence != null && reviewPolicy && detailTask.entity.confidence >= reviewPolicy.confidence_threshold ? 'bg-emerald-500' : 'bg-amber-500'}`}
                            style={{ width: `${detailTask.entity.confidence == null ? 0 : Math.round(detailTask.entity.confidence * 100)}%` }}
                          />
                        </div>
                      </div>
                      {detailTask.entity.original_ai_value && (
                        <div className="text-[11px] text-[#52627A]">Original AI value: {detailTask.entity.original_ai_value}</div>
                      )}

                      <div className="flex flex-wrap gap-1.5">
                        <span className="px-2 py-0.5 rounded bg-[#EAF5FF] text-[#071A3D] text-[10px] font-semibold">{detailTask.entity.assertion}</span>
                        {detailTask.entity.section && <span className="px-2 py-0.5 rounded bg-[#F5FAFF] text-[#52627A] text-[10px]">{detailTask.entity.section === 'ALLERGIES' ? 'ALLERGY · NOT AN ACTIVE MEDICATION' : detailTask.entity.section}</span>}
                        {detailTask.entity.details?.evidence_unverified && <span className="px-2 py-0.5 rounded bg-red-50 text-red-700 text-[10px] font-semibold">Evidence unverified · review required</span>}
                      </div>

                      {/* Evidence Span details */}
                      {detailTask.evidence && (
                        <div className="p-3 bg-[#F5FAFF] border border-[#DCE7F3] rounded-lg">
                          <div className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider mb-1">
                            Exact Evidence Span
                          </div>
                          <p className="font-mono text-xs text-[#071A3D] italic">
                            "{detailTask.evidence.text}"
                          </p>
                          <div className="text-[10px] font-mono text-[#52627A] mt-1.5">
                            Offset: {detailTask.evidence.start_offset} - {detailTask.evidence.end_offset}
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-xs text-[#52627A] italic">No entity record attached to this review task.</div>
                  )}
                </div>
              </div>

              {/* Panel 3: Human Review Decisions & Action Panel */}
              <div className={`${detailOnly && mobilePanel !== 'decision' ? 'hidden md:flex' : 'flex'} w-full shrink-0 bg-white flex-col md:min-h-0 md:flex-1 md:shrink md:overflow-hidden`}>
                <div className="px-4 py-3 bg-[#F5FAFF] border-b border-[#DCE7F3]">
                  <div className="font-sans text-xs font-bold text-[#071A3D]">HUMAN DECISION</div>
                  <div className="font-mono text-[10px] text-[#52627A]">Select clinician audit outcome</div>
                </div>

                <div className="flex-none p-4 space-y-4 md:min-h-0 md:flex-1 md:overflow-y-auto">
                  {!canReview && (
                    <div role="status" className="rounded-lg border border-[#DCE7F3] bg-[#F5FAFF] p-3 text-xs text-[#52627A]">
                      Read-only task view. Review decisions require the reviewer or admin role.
                    </div>
                  )}
                  {/* Optional Comment Input */}
                  <div>
                    <label className="block text-xs font-medium text-[#52627A] mb-1">Review Notes / Audit Comment (Optional)</label>
                    <textarea
                      value={commentInput}
                      onChange={(e) => setCommentInput(e.target.value)}
                      disabled={!canReview}
                      placeholder="Add clinical audit notes..."
                      className="w-full p-2.5 border border-[#DCE7F3] rounded-md text-xs outline-none focus:border-[#146EF5]"
                      rows={3}
                    />
                  </div>

                  {/* Clinical Safety Gates: Overrides & Conflicts */}
                  {detailTask && (hasMedOrLabFlag || hasConflict) && (
                    <div className="p-3 rounded-lg border border-[#DCE7F3] bg-[#F5FAFF] space-y-2.5">
                      <div className="font-sans text-xs font-semibold text-[#071A3D] flex items-center gap-1.5">
                        <ShieldAlert size={14} className="text-amber-600" />
                        <span>Clinical Override & Safety Acknowledgment</span>
                      </div>
                      {hasConflict && (
                        <label className="flex items-start gap-2 cursor-pointer text-xs text-[#071A3D]">
                          <input
                            type="checkbox"
                            checked={conflictAcknowledged}
                            onChange={(e) => setConflictAcknowledged(e.target.checked)}
                            className="mt-0.5 rounded border-[#DCE7F3] text-[#146EF5] focus:ring-[#146EF5]"
                          />
                          <span>I have reviewed and acknowledge the conflicting clinical assertions or doses.</span>
                        </label>
                      )}
                      {hasMedOrLabFlag && (
                        <div>
                          <label htmlFor="override-justification" className="block text-xs font-medium text-[#52627A] mb-1">
                            Override Justification (Required) *
                          </label>
                          <textarea
                            id="override-justification"
                            value={justificationInput}
                            onChange={(e) => setJustificationInput(e.target.value)}
                            disabled={!canReview}
                            placeholder="State clinical reason for overriding medication or lab validation flag..."
                            className="w-full p-2.5 border border-[#DCE7F3] rounded-md text-xs outline-none focus:border-[#146EF5]"
                            rows={2}
                          />
                        </div>
                      )}
                    </div>
                  )}

                  {/* Visible reason when approval is disabled */}
                  {approvalDisabledReason && (
                    <div role="alert" className="p-2.5 rounded-lg border border-amber-300 bg-amber-50 text-amber-900 text-xs flex items-center gap-2">
                      <AlertTriangle size={14} className="text-amber-600 shrink-0" />
                      <span>{approvalDisabledReason}</span>
                    </div>
                  )}

                  {/* Decision Buttons */}
                  <div className="space-y-2 pt-2" role="group" aria-label="Review decision actions">
                    <button
                      onClick={handleApproveCleanItems}
                      disabled={!canReview || submitting || Boolean(batchApprovalDisabledReason)}
                      title={batchApprovalDisabledReason || 'Batch approve only findings with high confidence, no flags, and a linked patient'}
                      className="w-full rounded-lg border border-[#146EF5] bg-white px-4 py-2.5 text-xs font-medium text-[#146EF5] hover:bg-[#EAF5FF] disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Approve clean items in this document
                    </button>
                    <button
                      onClick={handleApprove}
                      disabled={!canReview || submitting || !!approvalDisabledReason}
                      aria-busy={submitting}
                      title={approvalDisabledReason || undefined}
                      className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-lg bg-emerald-600 text-white font-medium text-xs hover:bg-emerald-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <CheckCircle2 size={16} aria-hidden="true" /> Approve Extraction (A)
                    </button>

                    <button
                      onClick={() => setShowRejectModal(true)}
                      disabled={!canReview || submitting}
                      aria-busy={submitting}
                      className="review-reject-button w-full flex items-center justify-center gap-2 py-3 px-4 rounded-lg bg-[#E11D48] text-white font-medium text-xs hover:bg-[#BE123C] transition-colors disabled:opacity-50"
                    >
                      <XCircle size={16} aria-hidden="true" /> Reject / Flag Error (R)
                    </button>

                    <button
                      onClick={() => setCorrectionMode(true)}
                      disabled={!canReview || submitting}
                      aria-busy={submitting}
                      className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-[#EAF5FF] text-[#071A3D] border border-[#DCE7F3] font-medium text-xs hover:bg-[#EAF5FF] transition-colors"
                    >
                      <Edit3 size={15} aria-hidden="true" /> Correct Clinical Value
                    </button>

                    <button
                      onClick={handleSkip}
                      disabled={submitting}
                      aria-busy={submitting}
                      className="w-full py-2.5 px-4 rounded-lg bg-[#F5FAFF] text-[#52627A] border border-[#DCE7F3] font-medium text-xs hover:bg-[#EAF5FF] transition-colors"
                    >
                      Skip → Next Item (N)
                    </button>
                  </div>

                  {/* Current Status Audit Info */}
                  {detailTask.decision && (
                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-1">
                      <div className="font-semibold text-[#071A3D]">Previous Decision Record:</div>
                      <div className="font-mono text-[11px] text-[#52627A]">Decision: {detailTask.decision}</div>
                      {detailTask.completed_at && (
                        <div className="font-mono text-[10px] text-[#52627A]">Timestamp: {new Date(detailTask.completed_at).toLocaleString()}</div>
                      )}
                      {detailTask.comment && (
                        <div className="text-slate-700 italic">"{detailTask.comment}"</div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center p-8 text-center text-[#52627A]">
              <div>
                <ChevronRight size={32} className="mx-auto mb-2 text-[#DCE7F3]" />
                <div className="font-sans text-sm font-semibold text-[#071A3D]">Select a review task</div>
                <div className="text-xs text-[#52627A] mt-1">
                  Choose an item from the queue list to inspect source OCR text and validate extraction.
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Reject Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h3 className="font-sans text-base font-bold text-[#071A3D]">Confirm Rejection</h3>
            <p className="text-xs text-[#52627A]">
              Please specify the reason for rejecting this AI clinical entity. The rejection will be recorded in the PostgreSQL audit log.
            </p>

            <textarea
              value={rejectReasonInput}
              onChange={(e) => setRejectReasonInput(e.target.value)}
              placeholder="E.g. Incorrect terminology mapping, false positive symptom..."
              className="w-full p-2.5 border border-[#DCE7F3] rounded-md text-xs outline-none focus:border-rose-500"
              rows={3}
            />

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowRejectModal(false)}
                className="px-4 py-2 text-xs font-medium text-[#52627A] hover:bg-[#EAF5FF] rounded-md"
              >
                Cancel
              </button>
              <button
                onClick={handleRejectConfirm}
                disabled={submitting}
                className="px-4 py-2 text-xs font-medium text-white bg-rose-600 hover:bg-rose-700 rounded-md"
              >
                {submitting ? 'Submitting...' : 'Confirm Rejection'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
