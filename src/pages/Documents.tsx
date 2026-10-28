import React, { useEffect, useRef, useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Upload, FileText, Search, Filter, Play, RefreshCw, Eye, ClipboardCheck } from 'lucide-react';
import { StatusBadge } from '../components/shared/StatusBadge';
import { deriveDocumentLifecycleStatus, type LifecycleStatus } from '../domain/documentLifecycle';
import {
  fetchDocuments,
  fetchPatients,
  uploadDocument,
  linkDocumentPatient,
  processDocument,
  retryDocumentProcessing,
  reprocessDocument,
  fetchProcessingJob,
  fetchReviewQueue,
  searchPatientsWithoutUrlQuery,
  type DocumentItem,
  type Patient,
  type ProcessingJobResponse,
  safeApiErrorMessage,
} from '../services/api';
import { MAX_UPLOAD_BYTES, validateUploadFile } from '../utils/uploadValidation';

export interface DocumentsPageProps {
  onNavigate: (view: string, documentId?: string, reviewTaskId?: string) => void;
}

export function DocumentsPage({ onNavigate }: DocumentsPageProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const queryParams = new URLSearchParams(window.location.search);
  const [statusFilter, setStatusFilter] = useState<LifecycleStatus | undefined>(() => {
    const value = queryParams.get('status') as LifecycleStatus | null;
    return value && ['uploaded', 'processing', 'failed', 'extracted', 'in_review', 'approved', 'rejected'].includes(value) ? value : undefined;
  });
  const [page, setPage] = useState(() => Math.max(1, Number(queryParams.get('page') || 1)));
  const [pageSize, setPageSize] = useState(() => Math.min(100, Math.max(10, Number(queryParams.get('page_size') || 25))));
  const [sort, setSort] = useState(() => queryParams.get('sort') || 'updated_desc');
  const [unlinkedPatient, setUnlinkedPatient] = useState(() => queryParams.get('unlinked_patient') === 'true');
  const [total, setTotal] = useState(0);

  // Upload modal state
  const [showModal, setShowModal] = useState(false);
  const [selectedPatientId, setSelectedPatientId] = useState('');
  const [patientSearch, setPatientSearch] = useState('');
  const [patientSearchError, setPatientSearchError] = useState<string | null>(null);
  const [documentType, setDocumentType] = useState('discharge_summary');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dropActive, setDropActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Processing state
  const [processingDocId, setProcessingDocId] = useState<string | null>(null);
  const [processingError, setProcessingError] = useState<string | null>(null);
  const [processingSnapshot, setProcessingSnapshot] = useState<ProcessingJobResponse | null>(null);
  const pollTimer = useRef<number | null>(null);
  const [patientLinkSelections, setPatientLinkSelections] = useState<Record<string, string>>({});
  const [linkingDocumentId, setLinkingDocumentId] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const docsResp = await fetchDocuments(page, pageSize, statusFilter, search, unlinkedPatient, sort);
      setDocuments(docsResp.items);
      setTotal(docsResp.total);
    } catch (_err) {
      setError('Unable to load documents. Please try refreshing the page.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 300);
    return () => window.clearTimeout(timer);
  }, [statusFilter, search, page, pageSize, unlinkedPatient, sort]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(async () => {
      setPatientSearchError(null);
      try {
        if (patientSearch.trim().length >= 3) {
          const results = await searchPatientsWithoutUrlQuery(patientSearch.trim());
          if (active) {
            setPatients(results.map((item) => ({
              id: item.id, first_name: item.display_label, last_name: null, mrn: null,
              gender: null, dob: null, external_patient_id: null,
            })));
          }
        } else {
          const result = await fetchPatients(1, 100);
          if (active) setPatients(result.items);
        }
      } catch (err) {
        if (active) setPatientSearchError(safeApiErrorMessage(err, 'Unable to search patients.'));
      }
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [patientSearch]);

  useEffect(() => () => {
    if (pollTimer.current !== null) window.clearInterval(pollTimer.current);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (statusFilter) params.set('status', statusFilter);
    params.set('page', String(page));
    params.set('page_size', String(pageSize));
    params.set('sort', sort);
    if (unlinkedPatient) params.set('unlinked_patient', 'true');
    window.history.replaceState(null, '', `${window.location.pathname}?${params}`);
  }, [statusFilter, page, pageSize, sort, unlinkedPatient]);

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setUploadError('Please select a file to upload');
      return;
    }

    const fileError = await validateUploadFile(selectedFile);
    if (fileError) {
      setUploadError(fileError);
      return;
    }

    setUploading(true);
    setUploadError(null);

    const formData = new FormData();
    if (selectedPatientId) formData.append('patient_id', selectedPatientId);
    formData.append('document_type', documentType);
    formData.append('file', selectedFile);

    try {
      const uploadedDocument = await uploadDocument(formData);
      setShowModal(false);
      setSelectedFile(null);
      await loadData();
      void handleProcessDocument(uploadedDocument.id);
    } catch (err: any) {
      setUploadError(safeApiErrorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  const handleProcessDocument = async (docId: string, retry = false, reprocess = false) => {
    setProcessingDocId(docId);
    setProcessingError(null);
    try {
      const processResp = reprocess
        ? await reprocessDocument(docId)
        : retry
          ? await retryDocumentProcessing(docId)
          : await processDocument(docId);
      const jobId = processResp.job_id;
      setDocuments((items) => items.map((item) => item.id === docId
        ? { ...item, status: processResp.status }
        : item));

      if (pollTimer.current !== null) window.clearInterval(pollTimer.current);
      let terminal = false;
      const poll = async () => {
        try {
          const job = await fetchProcessingJob(jobId);
          setProcessingSnapshot(job);
          if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
            terminal = true;
            if (pollTimer.current !== null) window.clearInterval(pollTimer.current);
            pollTimer.current = null;
            setProcessingDocId(null);
            if (job.status === 'failed') {
              setDocuments((items) => items.map((item) => item.id === docId ? { ...item, status: 'failed' } : item));
            } else if (job.status === 'completed') {
              const refreshed = await fetchDocuments(page, pageSize, statusFilter, search, unlinkedPatient, sort);
              setDocuments(refreshed.items);
              setTotal(refreshed.total);
            } else {
              setProcessingError('Processing was cancelled by the backend.');
            }
          }
        } catch (err) {
          terminal = true;
          if (pollTimer.current !== null) window.clearInterval(pollTimer.current);
          pollTimer.current = null;
          setProcessingDocId(null);
          setProcessingError(safeApiErrorMessage(err));
        }
      };
      await poll();
      if (!terminal) pollTimer.current = window.setInterval(() => void poll(), 1000);
    } catch (err) {
      setProcessingError(safeApiErrorMessage(err));
      setProcessingDocId(null);
    }
  };

  const chooseUploadFile = async (file?: File) => {
    setSelectedFile(file || null);
    setUploadError(null);
    if (!file) return;
    const validationMessage = await validateUploadFile(file);
    if (validationMessage) setUploadError(validationMessage);
  };

  const linkPatientToDocument = async (documentId: string) => {
    const patientId = patientLinkSelections[documentId];
    if (!patientId) return;
    setLinkingDocumentId(documentId);
    setError(null);
    try {
      await linkDocumentPatient(documentId, patientId);
      await loadData();
    } catch (err) {
      setError(safeApiErrorMessage(err, 'Unable to link this patient.'));
    } finally {
      setLinkingDocumentId(null);
    }
  };

  // Review is a document-level workflow, but the review API addresses its
  // individual tasks. Resolve the first active task so the reviewer lands on
  // the selected document rather than the first item in the global queue.
  const openReview = async (item: DocumentItem) => {
    try {
      const queue = await fetchReviewQueue(1, 100, 'all', 'all', undefined, item.id);
      const task = (queue.items || []).find((candidate) =>
        candidate.status === 'pending' || candidate.status === 'in_review',
      ) || queue.items?.[0];
      onNavigate('review', undefined, task?.id);
    } catch (err) {
      setError(safeApiErrorMessage(err, 'Unable to open the review workflow.'));
    }
  };

  const filtered = documents;

  return (
    <AppLayout activeView="documents" onNavigate={onNavigate}>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-[#071A3D]">Clinical Documents</h1>
            <p className="text-xs text-[#52627A] mt-0.5">
              Manage, upload, and inspect processed clinical documentation from PostgreSQL
            </p>
          </div>
          <Button icon={<Upload size={14} />} onClick={() => setShowModal(true)}>
            Upload Document
          </Button>
        </div>

        {/* Upload Modal */}
        {showModal && (
          <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 space-y-4 slide-in border border-[#DCE7F3]">
              <div className="flex justify-between items-center border-b pb-3 border-[#DCE7F3]">
                <h3 className="font-bold text-base text-[#071A3D]">Upload Clinical Document</h3>
                <button
                  onClick={() => setShowModal(false)}
                  className="text-xs font-mono text-[#52627A] hover:text-[#071A3D]"
                >
                  ✕
                </button>
              </div>

              {uploadError && (
                <div className="p-3 bg-[#fee2e2] text-[#b91c1c] text-xs rounded border border-[#fecaca]">
                  {uploadError}
                </div>
              )}

              <form onSubmit={handleUploadSubmit} className="space-y-4">
                <div>
                  <label htmlFor="patient-search" className="block text-xs font-mono uppercase text-[#52627A] mb-1">
                    Find a patient (optional)
                  </label>
                  <input
                    id="patient-search"
                    type="search"
                    value={patientSearch}
                    onChange={(e) => setPatientSearch(e.target.value)}
                    placeholder="Search existing patients"
                    className="mb-2 w-full text-xs p-2.5 rounded border border-[#DCE7F3] bg-white text-[#071A3D] outline-none"
                    autoComplete="off"
                  />
                  <select
                    aria-label="Patient link (optional)"
                    value={selectedPatientId}
                    onChange={(e) => setSelectedPatientId(e.target.value)}
                    className="w-full text-xs p-2.5 rounded border border-[#DCE7F3] bg-[#EAF5FF] text-[#071A3D] outline-none"
                  >
                    <option value="">No patient linked — link later before approval</option>
                    {patients.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.first_name && p.last_name
                          ? `${p.first_name} ${p.last_name}`
                          : `Patient ${p.mrn || p.id.slice(0, 8)}`}{' '}
                        ({p.mrn ? `MRN: ${p.mrn}` : `ID: ${p.id.slice(0, 6)}`})
                      </option>
                    ))}
                  </select>
                  {patientSearchError && <p role="alert" className="mt-1 text-xs text-red-700">{patientSearchError}</p>}
                  {!selectedPatientId && <p className="mt-1 text-[11px] text-amber-800">Approval remains blocked until a patient is linked.</p>}
                </div>

                <div>
                  <label className="block text-xs font-mono uppercase text-[#52627A] mb-1">
                    Document Type *
                  </label>
                  <select
                    value={documentType}
                    onChange={(e) => setDocumentType(e.target.value)}
                    className="w-full text-xs p-2.5 rounded border border-[#DCE7F3] bg-[#EAF5FF] text-[#071A3D] outline-none"
                    required
                  >
                    <option value="discharge_summary">Discharge Summary</option>
                    <option value="radiology_report">Radiology Report</option>
                    <option value="consultation_report">Consultation Report</option>
                    <option value="progress_note">Progress Note</option>
                    <option value="emergency_note">Emergency Note</option>
                    <option value="lab_report">Lab Report</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="upload-file" className="block text-xs font-mono uppercase text-[#52627A] mb-1">Document file (PDF / PNG / JPG / TIFF / TXT) *</label>
                  <div
                    onDragOver={(e) => { e.preventDefault(); setDropActive(true); }}
                    onDragLeave={() => setDropActive(false)}
                    onDrop={(e) => { e.preventDefault(); setDropActive(false); void chooseUploadFile(e.dataTransfer.files?.[0]); }}
                    className={`rounded-lg border-2 border-dashed p-4 text-center ${dropActive ? 'border-blue-600 bg-blue-50' : 'border-[#DCE7F3] bg-white'}`}
                  >
                    <p className="mb-2 text-xs text-[#52627A]">Drop one document here or choose a file. Maximum size: {Math.floor(MAX_UPLOAD_BYTES / (1024 * 1024))} MiB.</p>
                  <input
                    id="upload-file"
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg,.tiff,.txt"
                    onChange={(e) => void chooseUploadFile(e.target.files?.[0])}
                    className="w-full text-xs p-2 border border-[#DCE7F3] rounded bg-white"
                    required
                  />
                    {selectedFile && <p className="mt-2 truncate text-xs text-[#071A3D]">{selectedFile.name} · {Math.ceil(selectedFile.size / 1024)} KiB</p>}
                  </div>
                  <p className="mt-1 text-[11px] text-[#52627A]">Files are checked by signature and size here and again by the server. OCR quality score is not available from the backend.</p>
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-[#DCE7F3]">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setShowModal(false)}
                    disabled={uploading}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" disabled={uploading}>
                    {uploading ? 'Uploading...' : 'Upload File'}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Search & Filter Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-3 rounded-md border border-[#DCE7F3]">
          <div className="relative flex-1 w-full">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#52627A]" />
            <input
              type="text"
              placeholder="Search name, MRN, document, or case ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-[#EAF5FF] border border-[#DCE7F3] rounded-md text-[#071A3D] outline-none"
            />
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <select
              value={statusFilter || ''}
              onChange={(e) => { setPage(1); setStatusFilter((e.target.value || undefined) as LifecycleStatus | undefined); }}
              className="text-xs p-1.5 rounded border border-[#DCE7F3] bg-[#EAF5FF] text-[#52627A]"
            >
              <option value="">All Statuses</option>
              <option value="uploaded">Uploaded</option>
              <option value="processing">Processing</option>
              <option value="failed">Failed</option>
              <option value="extracted">Extracted (no review required)</option>
              <option value="in_review">In review</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
            <label className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-[#52627A]">
              <input type="checkbox" checked={unlinkedPatient} onChange={(e) => { setPage(1); setUnlinkedPatient(e.target.checked); }} />
              Unlinked patient
            </label>
            <select
              aria-label="Sort documents"
              value={sort}
              onChange={(e) => { setPage(1); setSort(e.target.value); }}
              className="text-xs p-1.5 rounded border border-[#DCE7F3] bg-[#EAF5FF] text-[#52627A]"
            >
              <option value="updated_desc">Newest</option>
              <option value="name_asc">Name</option>
              <option value="status_asc">Status</option>
            </select>
          </div>
        </div>

        {error && (
          <div role="alert" className="flex items-center justify-between gap-3 p-3 rounded-lg border border-[#FECACA] bg-[#FEF2F2] text-xs text-[#B91C1C]">
            <span>{error}</span>
            <button type="button" onClick={loadData} className="shrink-0 font-medium text-[#146EF5] hover:underline">
              Retry
            </button>
          </div>
        )}

        {processingError && (
          <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-[#FECACA] bg-[#FEF2F2] p-3 text-xs text-[#B91C1C]">
            <span>{processingError}</span>
            <button type="button" onClick={() => setProcessingError(null)} className="shrink-0 font-medium text-[#146EF5] hover:underline">
              Dismiss
            </button>
          </div>
        )}

        {processingSnapshot && (
          <section aria-label="Processing status" className="rounded-lg border border-[#DCE7F3] bg-white p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-[#071A3D]">Processing status</h2>
                <p className="mt-1 text-xs text-[#52627A]">Overall status: {processingSnapshot.status === 'completed'
                  ? (documents.find((item) => item.id === processingSnapshot.document_id)?.review_status === 'pending' ? 'Ready for review' : 'Completed')
                  : processingSnapshot.status}</p>
              </div>
              {processingSnapshot.status === 'failed' && (
                <Button size="sm" variant="outline" onClick={() => void handleProcessDocument(processingSnapshot.document_id, true)}>
                  Retry processing
                </Button>
              )}
            </div>
            {processingSnapshot.steps.length ? (
              <ol className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {processingSnapshot.steps.map((step) => (
                  <li key={step.id} className="rounded border border-[#EAF5FF] bg-[#F5FAFF] p-2 text-xs">
                    <span className="font-medium text-[#071A3D]">{{
                      provider_initialization: 'Provider setup', upload_validation: 'Uploaded file validation',
                      ocr: 'Reading text', text_normalization: 'Text normalization',
                      clinical_extraction: 'Extracting entities', entity_normalization: 'Entity normalization',
                      evidence_linking: 'Evidence linking', validation: 'Safety checks', review_routing: 'Review routing',
                    }[step.step_name] || step.step_name.replace(/_/g, ' ')}</span>
                    <span className="ml-2 text-[#52627A]">{step.status.replace(/_/g, ' ')}</span>
                  </li>
                ))}
              </ol>
            ) : <p className="mt-3 text-xs text-[#52627A]">Pipeline steps have not been reported yet. Overall status: {processingSnapshot.status}.</p>}
            <p className="mt-2 text-[11px] text-[#52627A]">Section-finding is not reported as a separate backend stage; no stage progress is inferred. OCR quality score: not available.</p>
            {processingSnapshot.status === 'failed' && <p role="alert" className="mt-2 text-xs text-red-800">{processingSnapshot.error_message || processingSnapshot.error_code || 'Processing failed; a reason was not returned.'}</p>}
          </section>
        )}

        {/* Document Table */}
        <Card className="p-0 overflow-hidden">
          {loading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 bg-[#F5FAFF] animate-pulse rounded" />
              ))}
            </div>
          ) : (
            <div className="w-full min-w-0 overflow-x-auto">
            <table className="w-full min-w-190 text-left border-collapse text-xs">
              <thead>
                <tr className="bg-[#EAF5FF] border-b border-[#DCE7F3] text-[#52627A] font-mono uppercase text-[10px] tracking-wider">
                  <th className="py-3 px-4">Case ID / Date</th>
                  <th className="py-3 px-4">Patient Name</th>
                  <th className="py-3 px-4">Doc Type</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Model confidence (uncalibrated)</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#DCE7F3]">
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-[#52627A]">
                      No documents found in PostgreSQL database.
                    </td>
                  </tr>
                ) : (
                  filtered.map((item) => (
                    <tr key={item.id} className="hover:bg-[#EAF5FF] transition-colors">
                      <td className="py-3 px-4">
                        <div className="font-semibold text-[#071A3D]">{item.case_id}</div>
                        {item.file_name && (
                          <div className="text-[11px] text-[#146EF5] font-mono truncate max-w-48" title={item.file_name}>
                            {item.file_name}
                          </div>
                        )}
                        <div className="text-[10px] text-[#52627A] font-mono">
                          {item.last_updated ? item.last_updated.split('T')[0] : '—'}
                        </div>
                      </td>
                      <td className="py-3 px-4 font-medium text-[#071A3D]">
                        {item.patient_id === null || (!item.patient_id && !item.patient_name && !item.mrn)
                          ? 'No patient linked'
                          : item.patient_name || item.mrn || 'Patient name not available'}
                        <div className="text-[10px] text-[#52627A] font-mono">
                          {item.patient_id === null || (!item.patient_id && !item.patient_name && !item.mrn)
                            ? <div className="space-y-1.5">
                              <div>Approval blocked until patient is linked.</div>
                              <div className="flex items-center gap-1">
                                <select
                                  aria-label={`Patient to link for ${item.case_id}`}
                                  value={patientLinkSelections[item.id] || ''}
                                  onChange={(event) => setPatientLinkSelections((current) => ({ ...current, [item.id]: event.target.value }))}
                                  className="max-w-36 rounded border border-[#DCE7F3] bg-white px-1 py-1 text-[10px]"
                                >
                                  <option value="">Select existing patient</option>
                                  {patients.map((patient) => <option key={patient.id} value={patient.id}>{patient.first_name || patient.last_name ? [patient.first_name, patient.last_name].filter(Boolean).join(' ') : patient.mrn || patient.id.slice(0, 8)}</option>)}
                                </select>
                                <Button type="button" size="sm" variant="outline" disabled={!patientLinkSelections[item.id] || linkingDocumentId === item.id} onClick={() => void linkPatientToDocument(item.id)}>
                                  {linkingDocumentId === item.id ? 'Linking…' : 'Link patient'}
                                </Button>
                              </div>
                            </div>
                            : item.mrn ? `MRN: ${item.mrn}` : 'Patient identifier not available'}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-[#52627A] capitalize">
                        {item.doc_type ? item.doc_type.replace('_', ' ') : '—'}
                      </td>
                      <td className="py-3 px-4">
                        <StatusBadge
                          status={processingDocId === item.id
                            ? 'processing'
                            : item.lifecycle_status || deriveDocumentLifecycleStatus(item.status, item.review_status)}
                        />
                      </td>
                      <td className="py-3 px-4">
                        <span className="font-mono text-[11px] font-semibold text-[#071A3D] uppercase">
                          {item.confidence ? item.confidence.replace('_', ' ') : '—'}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right space-x-2">
                        {item.status !== 'completed' && (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={processingDocId === item.id}
                            onClick={() => handleProcessDocument(item.id, item.status === 'failed')}
                            icon={<Play size={12} />}
                          >
                            {processingDocId === item.id ? 'Extracting...' : 'Extract'}
                          </Button>
                        )}
                        {item.status === 'completed' && (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={processingDocId === item.id}
                            onClick={() => {
                              if (window.confirm('Re-extract this document? Previous extraction results and review decisions will be replaced.')) {
                                void handleProcessDocument(item.id, false, true);
                              }
                            }}
                            icon={<RefreshCw size={12} />}
                          >
                            {processingDocId === item.id ? 'Re-extracting...' : 'Re-extract'}
                          </Button>
                        )}
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => onNavigate('clinical', item.id)}
                          icon={<Eye size={12} />}
                        >
                          Inspect
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={item.status !== 'completed'}
                          title={item.status !== 'completed' ? 'Review becomes available after extraction finishes.' : 'Open this document in the human review workflow.'}
                          onClick={() => void openReview(item)}
                          icon={<ClipboardCheck size={12} />}
                        >
                          Review
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            </div>
          )}
        </Card>
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-[#52627A]">
          <span>{total === 0 ? 'No documents' : `Showing ${(page - 1) * pageSize + 1}-${Math.min(page * pageSize, total)} of ${total}`}</span>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1">Rows
              <select value={pageSize} onChange={(e) => { setPage(1); setPageSize(Number(e.target.value)); }} className="rounded border border-[#DCE7F3] bg-white px-1.5 py-1">
                <option value={10}>10</option><option value={25}>25</option><option value={50}>50</option>
              </select>
            </label>
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</Button>
            <Button size="sm" variant="outline" disabled={page * pageSize >= total} onClick={() => setPage((value) => value + 1)}>Next</Button>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
