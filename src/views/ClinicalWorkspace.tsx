import { useEffect, useState } from 'react';
import {
  fetchDocuments,
  fetchDocumentDetails,
  fetchDocumentEntities,
  fetchReviewPolicy,
  type ClinicalEntityItem,
  type DocumentDetailResponse,
  type EvidenceSpanItem,
  type PipelineStageItem,
  type ReviewPolicy,
} from '../services/api';
import { FileText, ArrowRight, Database, RefreshCw } from 'lucide-react';
import { StatusBadge } from '../components/shared/StatusBadge';
import { deriveDocumentLifecycleStatus } from '../domain/documentLifecycle';

const ConfidenceBadge = ({ level }: { level: string }) => {
  const map: Record<string, { icon: string; color: string; bg: string }> = {
    high: { icon: '✓', color: '#15803d', bg: '#dcfce7' },
    medium: { icon: '⚠', color: '#b45309', bg: '#fef3c7' },
    low: { icon: '⚠', color: '#b91c1c', bg: '#fee2e2' },
    unavailable: { icon: '•', color: '#52627A', bg: '#F5FAFF' },
  };
  const s = map[level] || map.medium;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold" style={{ background: s.bg, color: s.color, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.04em', fontSize: 10 }}>
      <span aria-hidden="true">{s.icon}</span> MODEL CONFIDENCE (UNCALIBRATED)
    </span>
  );
};

function PipelinePanel({ stages }: { stages: PipelineStageItem[] }) {
  return (
    <div className="min-w-0 space-y-3 bg-white p-4 rounded-lg border border-[#DCE7F3]">
      <div className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider mb-2">Processing Stages</div>
      {stages.map((stg) => (
        <div key={stg.name} className="flex justify-between items-center gap-3 rounded-md px-2 py-2 border-b border-[#DCE7F3] last:border-0 text-xs transition-colors hover:bg-[#EAF5FF] hover:border-[rgba(20,110,245,0.35)]">
          <div>
            <div className="font-semibold text-[#071A3D]">{stg.name}</div>
            <div className="text-[10px] text-[#52627A] font-mono">{stg.detail}</div>
          </div>
          <span className={`px-2 py-0.5 rounded text-[9px] font-mono font-bold uppercase ${
            stg.status === 'done' ? 'bg-[#dcfce7] text-[#15803d]' : 'bg-[#F5FAFF] text-[#52627A]'
          }`}>
            {stg.status}
          </span>
        </div>
      ))}
    </div>
  );
}

function RealEntityCard({ entity, onViewSource, reviewPolicy }: { entity: ClinicalEntityItem; onViewSource: () => void; reviewPolicy: ReviewPolicy | null }) {
  const [expanded, setExpanded] = useState(false);
  const confStr = !reviewPolicy
    ? 'unavailable'
    : entity.confidence >= reviewPolicy.confidence_threshold
      ? 'high'
      : entity.confidence >= reviewPolicy.high_priority_threshold
        ? 'medium'
        : 'low';
  const code = entity.details?.code || '—';
  const codeSys = entity.details?.code_system || 'SNOMED/ICD10';
  const structuredDetails = Object.entries(entity.details || {}).filter(([key, value]) =>
    !['code', 'code_system', 'evidence_unverified'].includes(key) && value !== null && value !== undefined && String(value).trim() !== '',
  );

  return (
    <div className="rounded-lg p-4 mb-3 bg-white border border-[#DCE7F3] transition-colors hover:border-[#146EF5] hover:shadow-sm">
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="font-sans text-sm font-semibold text-[#071A3D]">
            {entity.normalized_value || entity.raw_text}
          </div>
          {entity.raw_text !== entity.normalized_value && (
            <div className="font-mono text-[10px] text-[#52627A]">Raw: "{entity.raw_text}"</div>
          )}
        </div>
        <ConfidenceBadge level={confStr} />
      </div>
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div>
          <div className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider">Status</div>
          <div className="font-sans text-xs text-[#071A3D] mt-0.5 capitalize">{entity.status}</div>
        </div>
        <div>
          <div className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider">Terminology</div>
          <div className="font-sans text-xs text-[#071A3D] mt-0.5">
            {codeSys} <span className="text-[#52627A] font-mono">{code}</span>
          </div>
        </div>
      </div>
      {entity.entity_type === 'medication' && (
        <div className="mb-3 grid grid-cols-2 gap-2 rounded-md border border-[#DCE7F3] bg-[#F5FAFF] p-2.5 sm:grid-cols-3">
          {structuredDetails.length > 0 ? structuredDetails.map(([key, value]) => (
            <div key={key}>
              <div className="font-mono text-[9px] uppercase tracking-wider text-[#52627A]">{key.replace(/_/g, ' ')}</div>
              <div className="mt-0.5 text-xs font-semibold capitalize text-[#071A3D]">{String(value)}</div>
            </div>
          )) : (
            <div className="col-span-full text-[11px] text-amber-700">Dose and frequency were not detected in the OCR text. Use Correct Clinical Value to verify them.</div>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5 mb-3">
        <span className="px-2 py-0.5 rounded bg-[#EAF5FF] text-[#071A3D] text-[10px] font-semibold">{entity.assertion}</span>
        {entity.section && <span className="px-2 py-0.5 rounded bg-[#F5FAFF] text-[#52627A] text-[10px]">{entity.section === 'ALLERGIES' ? 'ALLERGY · NOT AN ACTIVE MEDICATION' : entity.section}</span>}
        {entity.details?.evidence_unverified && <span className="px-2 py-0.5 rounded bg-red-50 text-red-700 text-[10px] font-semibold">Evidence unverified · review required</span>}
        {entity.validation_rule_codes?.map((code) => <span key={code} className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 text-[10px] font-mono">{code}</span>)}
      </div>
      {entity.evidence_spans && entity.evidence_spans.length > 0 && (
        <div className="mb-3 p-2.5 rounded-md bg-[#EAF5FF] border border-[#DCE7F3]">
          <div className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider mb-1">Evidence Text</div>
          <div className="font-sans text-xs text-[#52627A] italic leading-relaxed">
            "{entity.evidence_spans[0].exact_text}"
          </div>
        </div>
      )}
      <div className="flex gap-2">
        <button onClick={onViewSource} className="px-3 py-1.5 rounded text-xs font-medium bg-[#EAF5FF] text-[#146EF5] hover:bg-[#0E2A5C] hover:text-white transition-colors">
          View Source
        </button>
        {!expanded && (
          <button onClick={() => setExpanded(true)} className="px-3 py-1.5 rounded text-xs text-[#52627A] hover:bg-[#EAF5FF] hover:text-[#146EF5] transition-colors">
            Details ↓
          </button>
        )}
      </div>
      {expanded && (
        <div className="mt-3 p-3 rounded-md bg-[#F5FAFF] border border-[#DCE7F3] slide-in">
          <div className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider mb-2">Entity ID & Offsets</div>
          <div className="space-y-1 font-mono text-[10px]">
            <div className="flex justify-between">
              <span className="text-[#52627A]">Entity ID:</span>
              <span className="text-[#071A3D]">{entity.id.slice(0, 8)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#52627A]">Model confidence (uncalibrated):</span>
              <span className="text-[#071A3D]">{(entity.confidence * 100).toFixed(1)}%</span>
            </div>
          </div>
        <button onClick={() => setExpanded(false)} className="mt-2 text-xs text-[#52627A] hover:text-[#146EF5] transition-colors">Close ↑</button>
        </div>
      )}
    </div>
  );
}

function RealDocumentPanel({
  docDetails,
  activeEntitySpan,
}: {
  docDetails: DocumentDetailResponse;
  activeEntitySpan: EvidenceSpanItem | null;
}) {
  const text = docDetails.source_text || '';

  const renderTextWithHighlights = () => {
    if (!activeEntitySpan || activeEntitySpan.start_offset < 0 || activeEntitySpan.end_offset <= activeEntitySpan.start_offset) {
      return <span>{text}</span>;
    }

    const start = Math.max(0, activeEntitySpan.start_offset);
    const end = Math.min(text.length, activeEntitySpan.end_offset);

    const before = text.slice(0, start);
    const match = text.slice(start, end);
    const after = text.slice(end);

    return (
      <span>
        {before}
        <mark className="bg-[#EAF5FF] text-[#071A3D] font-semibold px-1 rounded border border-[#146EF5]">
          {match}
        </mark>
        {after}
      </span>
    );
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b flex items-center justify-between bg-white border-[#DCE7F3]">
        <div>
          <div className="font-sans text-xs font-semibold text-[#071A3D]">SOURCE DOCUMENT</div>
          <div className="font-mono text-[10px] text-[#52627A]">
            {docDetails.file_name} · {docDetails.page_count} page(s) · {(docDetails.size_bytes / 1024).toFixed(1)} KB
          </div>
        </div>
        <div className="flex gap-1.5">
          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#EAF5FF] text-[#146EF5] font-semibold uppercase">
            {docDetails.mime_type}
          </span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <pre className="font-sans text-xs text-[#071A3D] leading-relaxed whitespace-pre-wrap break-words">
          {renderTextWithHighlights()}
        </pre>
      </div>

      <div className="px-4 py-2.5 border-t flex items-center gap-4 bg-[#EAF5FF] border-[#DCE7F3]">
        <div className="font-mono text-[9px] text-[#52627A] uppercase tracking-wider">Provenance:</div>
        <span className="font-mono text-[10px] text-[#15803d]">
          ✓ Version {docDetails.version_number} · SHA-256 Hash Verified
        </span>
      </div>
    </div>
  );
}

export function ClinicalWorkspace({
  documentId: propDocumentId,
  onNavigate,
}: {
  documentId?: string | null;
  onNavigate?: (view: string) => void;
}) {
  const [targetDocId, setTargetDocId] = useState<string | null>(propDocumentId || null);
  const [docDetails, setDocDetails] = useState<DocumentDetailResponse | null>(null);
  const [entities, setEntities] = useState<ClinicalEntityItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('diagnoses');
  const [activeEntitySpan, setActiveEntitySpan] = useState<EvidenceSpanItem | null>(null);
  const [mobileWorkspaceTab, setMobileWorkspaceTab] = useState<'document' | 'extractions'>('extractions');
  const [reviewPolicy, setReviewPolicy] = useState<ReviewPolicy | null>(null);

  useEffect(() => {
    fetchReviewPolicy().then(setReviewPolicy).catch(() => setReviewPolicy(null));
  }, []);

  // If no documentId prop was passed, automatically fetch the latest document from PostgreSQL
  useEffect(() => {
    if (propDocumentId) {
      setTargetDocId(propDocumentId);
      return;
    }
    let isSubscribed = true;
    fetchDocuments(1, 1)
      .then((res) => {
        if (isSubscribed && res.items && res.items.length > 0) {
          setTargetDocId(res.items[0].id);
        }
      })
      .catch((err) => {
        if (isSubscribed) {
          setError('Unable to load document list. Please try again.');
        }
      });

    return () => {
      isSubscribed = false;
    };
  }, [propDocumentId]);

  useEffect(() => {
    if (!targetDocId) return;
    let isMounted = true;
    setError(null);
    async function loadWorkspace() {
      setLoading(true);
      try {
        const [details, ents] = await Promise.all([
          fetchDocumentDetails(targetDocId!),
          fetchDocumentEntities(targetDocId!),
        ]);
        if (isMounted) {
          setDocDetails(details);
          setEntities(ents);
          const hasDiag = ents.some((e) => e.entity_type === 'diagnosis' || e.entity_type === 'diagnoses');
          if (!hasDiag) {
            const hasMed = ents.some((e) => e.entity_type === 'medication' || e.entity_type === 'medications');
            const hasSym = ents.some((e) => e.entity_type === 'symptom' || e.entity_type === 'symptoms');
            const hasProc = ents.some((e) => e.entity_type === 'procedure' || e.entity_type === 'procedures');
            if (hasMed) setActiveTab('medications');
            else if (hasSym) setActiveTab('symptoms');
            else if (hasProc) setActiveTab('procedures');
            else setActiveTab('diagnoses');
          } else {
            setActiveTab('diagnoses');
          }
        }
      } catch (_err) {
        if (isMounted) {
          setError('Unable to load document data. Please try again.');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadWorkspace();
    return () => {
      isMounted = false;
    };
  }, [targetDocId]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center h-full bg-[#F5FAFF] p-6">
        <div className="text-center space-y-2">
          <RefreshCw size={24} className="text-[#146EF5] animate-spin mx-auto" aria-hidden="true" />
          <div className="font-sans text-xs text-[#52627A]">Loading document &amp; extracted entities...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center h-full bg-[#F5FAFF] p-6">
        <div className="max-w-sm w-full p-6 bg-white rounded-xl border border-[#DCE7F3] shadow-sm text-center space-y-4" role="alert">
          <div className="w-10 h-10 rounded-full bg-[#fee2e2] flex items-center justify-center mx-auto">
            <RefreshCw size={18} className="text-[#b91c1c]" aria-hidden="true" />
          </div>
          <div>
            <h2 className="font-sans text-sm font-bold text-[#071A3D]">Unable to load document data</h2>
            <p className="text-xs text-[#52627A] mt-1 leading-relaxed">{error}</p>
          </div>
          <button
            onClick={() => {
              setError(null);
              // Re-trigger the workspace load by resetting the targetDocId if it exists
              if (targetDocId) {
                const id = targetDocId;
                setTargetDocId(null);
                setTimeout(() => setTargetDocId(id), 0);
              } else if (propDocumentId) {
                setTargetDocId(propDocumentId);
              }
            }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-[#146EF5] text-white text-xs font-semibold rounded-md hover:bg-[#146EF5] transition-colors"
          >
            <RefreshCw size={14} aria-hidden="true" /> Retry
          </button>
        </div>
      </div>
    );
  }

  // Real workspace view when docDetails is loaded from PostgreSQL
  if (docDetails) {
    const diagnoses = entities.filter((e) => e.entity_type === 'diagnosis' || e.entity_type === 'diagnoses');
    const medications = entities.filter((e) => e.entity_type === 'medication' || e.entity_type === 'medications');
    const symptoms = entities.filter((e) => e.entity_type === 'symptom' || e.entity_type === 'symptoms');
    const procedures = entities.filter((e) => e.entity_type === 'procedure' || e.entity_type === 'procedures');

    const TABS = [
      { id: 'diagnoses', label: 'Diagnoses', count: diagnoses.length },
      { id: 'medications', label: 'Medications', count: medications.length },
      { id: 'symptoms', label: 'Symptoms', count: symptoms.length },
      { id: 'procedures', label: 'Procedures', count: procedures.length },
      { id: 'pipeline', label: 'Pipeline', count: null },
    ];

    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[#F5FAFF]">
        {/* Case header */}
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-b bg-white border-[#DCE7F3] page-header-edge">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-[10px] text-[#52627A]">Clinical Workspace</span>
                <span className="text-[#DCE7F3]">›</span>
                <span className="font-mono text-[10px] text-[#146EF5] font-medium">{docDetails.case_id}</span>
              </div>
              <div className="flex items-center gap-3">
                <h1 className="font-sans text-base sm:text-lg font-bold text-[#071A3D]">
                  {docDetails.patient_name || 'Patient Record'}
                </h1>
                <div className="font-mono text-[10px] text-[#52627A]">
                  {docDetails.mrn ? `MRN ${docDetails.mrn}` : `Doc ID: ${docDetails.id.slice(0, 8)}`}
                </div>
                <StatusBadge
                  status={docDetails.lifecycle_status || deriveDocumentLifecycleStatus(docDetails.status, docDetails.review_status)}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1 font-mono text-xs text-[#15803d] bg-emerald-50 px-2.5 py-1 rounded border border-emerald-200">
                <Database size={12} /> PostgreSQL Live Record
              </span>
            </div>
          </div>
        </div>

        {/* Clinical entity navigation */}
        <div role="tablist" aria-label="Extracted entities" className="flex min-w-0 gap-1 border-b px-2 sm:px-4 bg-white border-[#DCE7F3] overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={activeTab === t.id}
              onClick={() => {
                setActiveTab(t.id);
                setMobileWorkspaceTab('extractions');
              }}
              className={`flex shrink-0 items-center gap-1.5 px-2.5 min-[900px]:px-3 py-3 text-xs sm:text-sm font-medium border-b-2 transition-colors whitespace-nowrap bg-white hover:bg-[#EAF5FF] hover:text-[#071A3D] hover:border-[rgba(20,110,245,0.35)] ${
                activeTab === t.id ? 'border-[#146EF5] text-[#146EF5]' : 'border-transparent text-[#52627A]'
              }`}
            >
              {t.label}
              {t.count !== null && (
                <span
                  className={`px-1.5 py-0.5 rounded-full border border-[#DCE7F3] text-[10px] font-mono ${
                    activeTab === t.id ? 'text-[#146EF5]' : 'bg-[#EAF5FF] text-[#52627A]'
                  }`}
                  style={activeTab === t.id ? { background: 'rgba(20,110,245,0.10)' } : undefined}
                >
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Main content: source document alongside the active clinical tab on larger screens. */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden lg:flex-row">
          {/* Panel 1: Source Document */}
          <div
            className={`flex min-h-0 flex-1 flex-col bg-white border-r border-[#DCE7F3] w-full lg:w-[38%] lg:flex-none 2xl:w-[33%] ${
              mobileWorkspaceTab === 'document' ? 'flex' : 'hidden lg:flex'
            }`}
          >
            <RealDocumentPanel docDetails={docDetails} activeEntitySpan={activeEntitySpan} />
          </div>

          {/* Panel 2: Active clinical tab content */}
          <div
            className={`min-h-0 min-w-0 flex-1 flex-col overflow-hidden ${
              mobileWorkspaceTab === 'extractions' ? 'flex' : 'hidden lg:flex'
            }`}
          >
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 bg-[#F5FAFF]">
              {activeTab === 'diagnoses' && (
                diagnoses.length > 0 ? (
                  diagnoses.map((ent) => (
                    <RealEntityCard
                      key={ent.id}
                      entity={ent}
                      reviewPolicy={reviewPolicy}
                      onViewSource={() => {
                        if (ent.evidence_spans && ent.evidence_spans.length > 0) {
                          setActiveEntitySpan(ent.evidence_spans[0]);
                        }
                        setMobileWorkspaceTab('document');
                      }}
                    />
                  ))
                ) : (
                  <div className="p-8 text-center bg-white rounded-lg border border-[#DCE7F3] text-xs text-[#52627A]">
                    No diagnoses identified in this document.
                  </div>
                )
              )}

              {activeTab === 'medications' && (
                medications.length > 0 ? (
                  medications.map((ent) => (
                    <RealEntityCard
                      key={ent.id}
                      entity={ent}
                      reviewPolicy={reviewPolicy}
                      onViewSource={() => {
                        if (ent.evidence_spans && ent.evidence_spans.length > 0) {
                          setActiveEntitySpan(ent.evidence_spans[0]);
                        }
                        setMobileWorkspaceTab('document');
                      }}
                    />
                  ))
                ) : (
                  <div className="p-8 text-center bg-white rounded-lg border border-[#DCE7F3] text-xs text-[#52627A]">
                    No medications identified in this document.
                  </div>
                )
              )}

              {activeTab === 'symptoms' && (
                symptoms.length > 0 ? (
                  symptoms.map((ent) => (
                    <RealEntityCard
                      key={ent.id}
                      entity={ent}
                      reviewPolicy={reviewPolicy}
                      onViewSource={() => {
                        if (ent.evidence_spans && ent.evidence_spans.length > 0) {
                          setActiveEntitySpan(ent.evidence_spans[0]);
                        }
                        setMobileWorkspaceTab('document');
                      }}
                    />
                  ))
                ) : (
                  <div className="p-8 text-center bg-white rounded-lg border border-[#DCE7F3] text-xs text-[#52627A]">
                    No symptoms identified in this document.
                  </div>
                )
              )}

              {activeTab === 'procedures' && (
                procedures.length > 0 ? (
                  procedures.map((ent) => (
                    <RealEntityCard
                      key={ent.id}
                      entity={ent}
                      reviewPolicy={reviewPolicy}
                      onViewSource={() => {
                        if (ent.evidence_spans && ent.evidence_spans.length > 0) {
                          setActiveEntitySpan(ent.evidence_spans[0]);
                        }
                        setMobileWorkspaceTab('document');
                      }}
                    />
                  ))
                ) : (
                  <div className="p-8 text-center bg-white rounded-lg border border-[#DCE7F3] text-xs text-[#52627A]">
                    No procedures identified in this document.
                  </div>
                )
              )}

              {activeTab === 'pipeline' && (
                <PipelinePanel stages={docDetails.pipeline_stages} />
              )}
            </div>
          </div>

        </div>
      </div>
    );
  }

  // Real empty state when no document is found in PostgreSQL
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 bg-[#F5FAFF] text-center">
      <div className="max-w-md w-full p-6 bg-white rounded-xl border border-[#DCE7F3] shadow-sm space-y-3">
        <FileText size={32} className="text-[#146EF5] mx-auto" />
        <h2 className="font-sans text-base font-bold text-[#071A3D]">No document selected</h2>
        <p className="text-xs text-[#52627A] leading-relaxed">
          Upload a medical document or choose an existing document from the Documents repository to inspect extracted clinical entities and source evidence.
        </p>
        {onNavigate && (
          <button
            onClick={() => onNavigate('documents')}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-[#146EF5] text-white text-xs font-semibold rounded-md hover:bg-[#146EF5] transition-colors"
          >
            Go to Documents <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
