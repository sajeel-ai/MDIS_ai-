import React, { useEffect, useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Upload, FileText, Search, Filter, Play, CheckCircle2, AlertCircle } from 'lucide-react';
import {
  fetchDocuments,
  fetchPatients,
  uploadDocument,
  processDocument,
  retryDocumentProcessing,
  fetchProcessingJob,
  type DocumentItem,
  type Patient,
  safeApiErrorMessage,
} from '../services/api';

export interface DocumentsPageProps {
  onNavigate: (view: string, documentId?: string) => void;
}

export function DocumentsPage({ onNavigate }: DocumentsPageProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  // Upload modal state
  const [showModal, setShowModal] = useState(false);
  const [selectedPatientId, setSelectedPatientId] = useState('');
  const [documentType, setDocumentType] = useState('discharge_summary');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Processing state
  const [processingDocId, setProcessingDocId] = useState<string | null>(null);
  const [processingError, setProcessingError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [docsResp, patsResp] = await Promise.all([
        fetchDocuments(1, 50, statusFilter, search),
        fetchPatients(1, 100),
      ]);
      setDocuments(docsResp.items);
      setPatients(patsResp.items);
      if (patsResp.items.length > 0 && !selectedPatientId) {
        setSelectedPatientId(patsResp.items[0].id);
      }
    } catch (_err) {
      setError('Unable to load documents. Please try refreshing the page.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPatientId) {
      setUploadError('Please select a patient');
      return;
    }
    if (!selectedFile) {
      setUploadError('Please select a file to upload');
      return;
    }

    setUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append('patient_id', selectedPatientId);
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

  const handleProcessDocument = async (docId: string, retry = false) => {
    setProcessingDocId(docId);
    setProcessingError(null);
    try {
      const processResp = retry
        ? await retryDocumentProcessing(docId)
        : await processDocument(docId);
      const jobId = processResp.job_id;
      setDocuments((items) => items.map((item) => item.id === docId
        ? { ...item, status: processResp.status }
        : item));

      // Poll without replacing the document table with the page-level loading state.
      const interval = window.setInterval(async () => {
        try {
          const job = await fetchProcessingJob(jobId);
          if (job.status === 'completed' || job.status === 'failed') {
            clearInterval(interval);
            setProcessingDocId(null);
            setDocuments((items) => items.map((item) => item.id === docId
              ? { ...item, status: job.status }
              : item));
          }
        } catch (err) {
          clearInterval(interval);
          setProcessingDocId(null);
          setProcessingError(safeApiErrorMessage(err));
        }
      }, 1000);
    } catch (err) {
      setProcessingError(safeApiErrorMessage(err));
      setProcessingDocId(null);
    }
  };

  const filtered = documents.filter(
    (c) =>
      (c.patient_name || '').toLowerCase().includes(search.toLowerCase()) ||
      (c.doc_type || '').toLowerCase().includes(search.toLowerCase()) ||
      (c.case_id || '').toLowerCase().includes(search.toLowerCase()) ||
      (c.id || '').toLowerCase().includes(search.toLowerCase())
  );

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
                  <label className="block text-xs font-mono uppercase text-[#52627A] mb-1">
                    Select Patient *
                  </label>
                  <select
                    value={selectedPatientId}
                    onChange={(e) => setSelectedPatientId(e.target.value)}
                    className="w-full text-xs p-2.5 rounded border border-[#DCE7F3] bg-[#EAF5FF] text-[#071A3D] outline-none"
                    required
                  >
                    {patients.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.first_name && p.last_name
                          ? `${p.first_name} ${p.last_name}`
                          : `Patient ${p.mrn || p.id.slice(0, 8)}`}{' '}
                        ({p.mrn ? `MRN: ${p.mrn}` : `ID: ${p.id.slice(0, 6)}`})
                      </option>
                    ))}
                  </select>
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
                  <label className="block text-xs font-mono uppercase text-[#52627A] mb-1">
                    Document File (PDF / Image / Text) *
                  </label>
                  <input
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg,.tiff,.txt"
                    onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                    className="w-full text-xs p-2 border border-[#DCE7F3] rounded bg-white"
                    required
                  />
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
              placeholder="Filter by document type, patient name, or case ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-[#EAF5FF] border border-[#DCE7F3] rounded-md text-[#071A3D] outline-none"
            />
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <select
              value={statusFilter || ''}
              onChange={(e) => setStatusFilter(e.target.value || undefined)}
              className="text-xs p-1.5 rounded border border-[#DCE7F3] bg-[#EAF5FF] text-[#52627A]"
            >
              <option value="">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
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
                        {item.patient_name || 'MIMIC / Synthetic Patient'}
                        <div className="text-[10px] text-[#52627A] font-mono">
                          {item.mrn ? `MRN: ${item.mrn}` : `ID: ${item.id.slice(0, 6)}`}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-[#52627A] capitalize">
                        {item.doc_type ? item.doc_type.replace('_', ' ') : '—'}
                      </td>
                      <td className="py-3 px-4">
                        <Badge
                          variant={
                            item.status === 'completed'
                              ? 'success'
                              : item.status === 'processing'
                              ? 'warning'
                              : item.status === 'failed'
                              ? 'error'
                              : 'ai'
                          }
                        >
                          {processingDocId === item.id ? 'Processing...' : item.status}
                        </Badge>
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
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => onNavigate('clinical', item.id)}
                        >
                          Inspect Case
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
      </div>
    </AppLayout>
  );
}
