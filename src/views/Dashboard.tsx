import { useEffect, useState } from 'react';
import {
  fetchDashboard,
  type DashboardResponse,
  type RecentCaseItem,
  safeApiErrorMessage,
} from '../services/api';

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const ConfidencePill = ({ level }: { level: string }) => {
  const map: Record<string, { bg: string; text: string; dot: string }> = {
    high: { bg: '#dcfce7', text: '#15803d', dot: '#22c55e' },
    medium: { bg: '#fef3c7', text: '#b45309', dot: '#d97706' },
    low: { bg: '#fef3c7', text: '#b45309', dot: '#d97706' },
    not_available: { bg: '#EAF5FF', text: '#52627A', dot: '#52627A' },
  };
  const s = map[level] || map.not_available;
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium" style={{ background: s.bg, color: s.text, fontFamily: 'Inter, sans-serif' }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.dot }} />
      {level.charAt(0).toUpperCase() + level.slice(1).replace('_', ' ')}
    </span>
  );
};

const StatusPill = ({ status }: { status: string }) => {
  const label = status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  const map: Record<string, { bg: string; text: string }> = {
    Completed: { bg: '#dcfce7', text: '#15803d' },
    Processing: { bg: '#EAF5FF', text: '#146EF5' },
    Failed: { bg: '#fee2e2', text: '#b91c1c' },
    'Needs Review': { bg: '#fef3c7', text: '#b45309' },
    'In Review': { bg: '#fef3c7', text: '#b45309' },
    Validating: { bg: '#EAF5FF', text: '#071A3D' },
  };
  const s = map[label] || { bg: '#EAF5FF', text: '#52627A' };
  return <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: s.bg, color: s.text, fontFamily: 'Inter, sans-serif' }}>{label}</span>;
};

const MetricCard = ({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) => (
  <div className="rounded-lg p-5" style={{ background: '#fff', border: '1px solid #DCE7F3' }}>
    <div style={{ color: '#52627A', fontSize: 11, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 10 }}>{label}</div>
    <div style={{ fontFamily: 'DM Sans, sans-serif', fontSize: 28, fontWeight: 700, color: color || '#071A3D', lineHeight: 1 }}>{value}</div>
    {sub && <div style={{ color: '#52627A', fontSize: 12, fontFamily: 'Inter, sans-serif', marginTop: 6 }}>{sub}</div>}
  </div>
);

const MiniBar = ({ pct, color }: { pct: number; color: string }) => (
  <div className="flex items-center gap-3">
    <div className="flex-1 h-1.5 rounded-full" style={{ background: '#F5FAFF' }}>
      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color.includes('linear-gradient') ? color : 'linear-gradient(90deg, #146EF5, #16C7E8)' }} />
    </div>
    <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#52627A', minWidth: 32, textAlign: 'right' }}>{pct}%</span>
  </div>
);

const Skeleton = ({ className }: { className?: string }) => (
  <div className={`animate-pulse bg-[#EAF5FF] rounded ${className}`} />
);

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function Dashboard({ onNavigate }: { onNavigate: (v: string, params?: Record<string, string>) => void }) {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionBanner, setActionBanner] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDashboard()
      .then((d) => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch((e) => { if (!cancelled) { setError(safeApiErrorMessage(e, "Access restricted (admin/operator only)")); setLoading(false); } });
    return () => { cancelled = true; };
  }, []);

  const showBanner = (msg: string) => {
    setActionBanner(msg);
    setTimeout(() => setActionBanner(null), 5000);
  };

  const handleExport = () => showBanner('Data export is not configured in this environment. Contact your system administrator.');
  const handleNewExtraction = () => showBanner('Manual extraction queuing is not available yet. Documents are processed automatically on upload.');

  const metrics = data?.metrics;
  const queueSummary = data?.review_queue_summary;
  const quality = data?.extraction_quality ?? [];
  const recentCases: RecentCaseItem[] = data?.recent_cases ?? [];

  const pct = (n: number | null, total: number) =>
    total > 0 && n !== null ? Math.round((n / total) * 100) : 0;

  const qualityColors: Record<string, string> = {
    diagnoses: 'linear-gradient(90deg, #146EF5, #16C7E8)',
    medications: 'linear-gradient(90deg, #146EF5, #16C7E8)',
    symptoms: 'linear-gradient(90deg, #146EF5, #16C7E8)',
    procedures: 'linear-gradient(90deg, #146EF5, #16C7E8)',
    temporal: 'linear-gradient(90deg, #146EF5, #16C7E8)'
  };

  const lastUpdated = metrics?.last_updated_at
    ? new Date(metrics.last_updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '—';

  return (
    <div className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto" style={{ background: '#F5FAFF' }}>
      {/* Header */}
      <div className="px-4 sm:px-8 py-4 sm:py-5 border-b bg-white border-[#DCE7F3] page-header-edge page-header-edge-inset page-header-edge-pad-4 page-header-edge-pad-sm-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="font-sans text-lg sm:text-xl font-bold text-[#071A3D]">Clinical Intelligence Dashboard</h1>
            <p className="text-[#52627A] text-xs font-mono mt-0.5">
              {loading ? 'Loading…' : error ? '⚠ Backend offline — showing cached data' : `Last updated: ${lastUpdated}`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleExport}
              aria-label="Export data (not yet configured)"
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-[#F5FAFF] text-[#52627A] hover:bg-[#DCE7F3] transition-colors"
            >
              Export
            </button>
            <button
              onClick={handleNewExtraction}
              aria-label="Queue new extraction (not yet available)"
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-[#146EF5] text-white hover:bg-[#146EF5] transition-colors"
            >
              New Extraction
            </button>
          </div>
        </div>
      </div>

      <div className="p-4 sm:p-6 space-y-6">
        {/* Action banner */}
        {actionBanner && (
          <div
            role="status"
            aria-live="polite"
            className="flex items-start gap-3 p-4 rounded-lg bg-[#EAF5FF] border border-[#DCE7F3] text-xs text-[#146EF5]"
          >
            <span aria-hidden="true">ℹ</span>
            {actionBanner}
          </div>
        )}

        {error && (
          <div className="rounded-lg p-3 bg-amber-50 border border-amber-200 text-xs text-amber-800 font-mono">
            ⚠ Backend unreachable: {error}. Displaying empty state.
          </div>
        )}

        {/* KPI row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {loading ? (
            <>
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}
            </>
          ) : (
            <>
              <MetricCard
                label="Total Documents"
                value={metrics ? metrics.total_documents.toLocaleString() : '—'}
                sub={metrics ? `${pct(metrics.processed, metrics.total_documents)}% success rate` : undefined}
              />
              <MetricCard
                label="Processed"
                value={metrics ? metrics.processed.toLocaleString() : '—'}
                sub={metrics?.success_rate != null ? `${(metrics.success_rate * 100).toFixed(1)}% success rate` : undefined}
                color="#071A3D"
              />
              <MetricCard
                label="Pending Review"
                value={metrics ? metrics.pending_review.toLocaleString() : '—'}
                color="#071A3D"
              />
              <MetricCard
                label="Failed"
                value={metrics ? metrics.failed.toLocaleString() : '—'}
                sub={metrics && metrics.total_documents > 0 ? `${pct(metrics.failed, metrics.total_documents)}% failure rate` : undefined}
                color="#071A3D"
              />
            </>
          )}
        </div>

        {/* Middle row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* AI Quality */}
          <div className="rounded-lg p-5 bg-white border border-[#DCE7F3]">
            <h2 className="font-sans text-sm font-semibold text-[#071A3D] mb-4">Model confidence (uncalibrated)</h2>
            <div className="space-y-4">
              {loading ? (
                [0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-4" />)
              ) : quality.length > 0 ? (
                quality.map((r) => {
                  const pctVal = r.model_confidence_uncalibrated !== null ? Math.round(r.model_confidence_uncalibrated * 100) : null;
                  const color = qualityColors[r.entity_type] || '#52627A';
                  return (
                    <div key={r.entity_type}>
                      <div className="flex justify-between mb-1">
                        <span className="text-xs text-[#52627A] capitalize">{r.entity_type}</span>
                      </div>
                      {pctVal === null ? <span className="text-xs text-[#52627A]">Not measured</span> : <MiniBar pct={pctVal} color={color} />}
                    </div>
                  );
                })
              ) : (
                // Fallback static display when no AI entities exist yet
                [
                  { label: 'Diagnoses', pct: 0, color: '#146EF5' },
                  { label: 'Medications', pct: 0, color: '#146EF5' },
                  { label: 'Symptoms', pct: 0, color: '#146EF5' },
                  { label: 'Procedures', pct: 0, color: '#146EF5' },
                  { label: 'Temporal', pct: 0, color: '#146EF5' },
                ].map((r) => (
                  <div key={r.label}>
                    <div className="flex justify-between mb-1">
                      <span className="text-xs text-[#52627A]">{r.label}</span>
                      <span className="text-xs text-[#52627A]">No data</span>
                    </div>
                    <MiniBar pct={r.pct} color={r.color} />
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Review breakdown */}
          <div className="rounded-lg p-5 bg-white border border-[#DCE7F3]">
            <h2 className="font-sans text-sm font-semibold text-[#071A3D] mb-4">Review Queue</h2>
            <div className="space-y-3">
              {loading ? (
                [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)
              ) : (
                [
                  { label: 'High Priority', count: queueSummary?.high_priority ?? 0, color: '#071A3D', dot: '#d97706' },
                  { label: 'Medium Priority', count: queueSummary?.medium_priority ?? 0, color: '#071A3D', dot: '#146EF5' },
                  { label: 'Standard', count: queueSummary?.standard ?? 0, color: '#071A3D', dot: '#146EF5' },
                  { label: 'AI Conflicts', count: queueSummary?.ai_conflicts ?? 0, color: '#071A3D', dot: '#071A3D' },
                ].map((r) => (
                  <button
                    key={r.label}
                    onClick={() => onNavigate('review')}
                    className="w-full flex items-center justify-between px-3 py-2.5 rounded-md border border-[#DCE7F3] bg-white transition-colors hover:bg-[#EAF5FF]"
                  >
                    <span className="flex items-center gap-2 text-xs font-medium text-[#52627A]"><span className="w-2 h-2 rounded-full" style={{ background: r.dot }} />{r.label}</span>
                    <span className="font-sans text-base font-bold" style={{ color: r.color }}>{r.count}</span>
                  </button>
                ))
              )}
            </div>
            <button
              onClick={() => onNavigate('review')}
              className="w-full mt-4 py-2 rounded-md text-xs font-medium bg-[#146EF5] text-white"
            >
              Open Review Center →
            </button>
          </div>
        </div>

        {/* Recent Cases */}
        <div className="rounded-lg bg-white border border-[#DCE7F3] overflow-hidden">
          <div className="px-5 py-4 border-b border-[#DCE7F3] flex items-center justify-between">
            <h2 className="font-sans text-sm font-semibold text-[#071A3D]">Recent Clinical Cases</h2>
            <button onClick={() => onNavigate('clinical')} className="text-xs font-medium text-[#146EF5]">View all →</button>
          </div>
          <div className="w-full overflow-x-auto min-w-0">
            <table className="w-full min-w-[640px] text-left border-collapse">
              <thead>
                <tr style={{ borderBottom: '1px solid #F5FAFF' }}>
                  {['Case ID', 'Patient', 'Document', 'Status', 'Model confidence (uncalibrated)', 'Review', 'Action'].map((h) => (
                    <th key={h} className="px-5 py-3 text-left" style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#52627A', letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 500 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  [0, 1, 2, 3, 4].map((i) => (
                    <tr key={i}>
                      {[0, 1, 2, 3, 4, 5, 6].map((j) => (
                        <td key={j} className="px-5 py-3.5">
                          <Skeleton className="h-4 w-full" />
                        </td>
                      ))}
                    </tr>
                  ))
                ) : recentCases.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-5 py-8 text-center text-sm text-[#52627A]">
                      No documents found. Process a document to see cases here.
                    </td>
                  </tr>
                ) : (
                  recentCases.map((c) => (
                    <tr key={c.id} className="border-b last:border-0 hover:bg-blue-50 transition-colors" style={{ borderColor: '#F5FAFF', cursor: 'pointer' }}>
                      <td className="px-5 py-3.5">
                        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#146EF5', fontWeight: 500 }}>{c.id}</span>
                      </td>
                      <td className="px-5 py-3.5" style={{ fontFamily: 'Inter, sans-serif', fontSize: 13, color: '#071A3D' }}>
                        {c.patient_name || c.mrn || '—'}
                      </td>
                      <td className="px-5 py-3.5" style={{ fontFamily: 'Inter, sans-serif', fontSize: 13, color: '#52627A' }}>{c.doc_type}</td>
                      <td className="px-5 py-3.5"><StatusPill status={c.status} /></td>
                      <td className="px-5 py-3.5"><ConfidencePill level={c.confidence} /></td>
                      <td className="px-5 py-3.5" style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: '#52627A' }}>{c.review_status}</td>
                      <td className="px-5 py-3.5">
                        <button
                          onClick={() => onNavigate('clinical')}
                          className="px-3 py-1 rounded text-xs font-medium"
                          style={{ background: '#EAF5FF', color: '#146EF5', fontFamily: 'Inter, sans-serif' }}
                        >
                          Open
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
