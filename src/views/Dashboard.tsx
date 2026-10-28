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
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDashboard()
      .then((d) => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch((e) => { if (!cancelled) { setData(null); setError(safeApiErrorMessage(e, "Dashboard data is unavailable.")); setLoading(false); } });
    return () => { cancelled = true; };
  }, [reloadVersion]);

  const metrics = data?.metrics;
  const queueSummary = data?.review_queue_summary;
  const quality = data?.extraction_quality ?? [];
  const recentCases: RecentCaseItem[] = data?.recent_cases ?? [];

  const lastUpdated = metrics?.last_updated_at
    ? new Date(metrics.last_updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : 'not available';

  return (
    <div className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto" style={{ background: '#F5FAFF' }}>
      {/* Header */}
      <div className="px-4 sm:px-8 py-4 sm:py-5 border-b bg-white border-[#DCE7F3] page-header-edge page-header-edge-inset page-header-edge-pad-4 page-header-edge-pad-sm-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="font-sans text-lg sm:text-xl font-bold text-[#071A3D]">Clinical Intelligence Dashboard</h1>
            <p className="text-[#52627A] text-xs font-mono mt-0.5">
              {loading ? 'Loading dashboard data…' : error ? 'Dashboard data is unavailable' : `Last updated: ${lastUpdated}`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onNavigate('documents')}
              aria-label="Upload document"
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-[#146EF5] text-white hover:bg-[#146EF5] transition-colors"
            >
              Upload document
            </button>
          </div>
        </div>
      </div>

      <div className="p-4 sm:p-6 space-y-6">
        {error && (
          <div role="alert" className="flex items-center justify-between gap-3 rounded-lg p-3 bg-amber-50 border border-amber-200 text-xs text-amber-800">
            <span>{error}</span>
            <button onClick={() => setReloadVersion((version) => version + 1)} className="shrink-0 underline">Retry</button>
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
                value={metrics ? metrics.total_documents.toLocaleString() : 'not available'}
              />
              <MetricCard
                label="Processed"
                value={metrics ? metrics.processed.toLocaleString() : 'not available'}
                sub={metrics?.success_rate != null ? `${(metrics.success_rate * 100).toFixed(1)}% of total documents completed` : 'Completion rate not available'}
                color="#071A3D"
              />
              <MetricCard
                label="Awaiting Review"
                value={metrics ? metrics.pending_review.toLocaleString() : 'not available'}
                color="#071A3D"
              />
              <MetricCard
                label="Failed"
                value={metrics ? metrics.failed.toLocaleString() : 'not available'}
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
                  return (
                    <div key={r.entity_type}>
                      <div className="flex justify-between mb-1">
                        <span className="text-xs text-[#52627A] capitalize">{r.entity_type}</span>
                      </div>
                      {pctVal === null ? <span className="text-xs text-[#52627A]">not available</span> : <MiniBar pct={pctVal} color="#146EF5" />}
                    </div>
                  );
                })
              ) : (
                <p className="text-xs text-[#52627A]">No model confidence values are available.</p>
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
                  { label: 'Awaiting review', count: queueSummary?.awaiting_review, color: '#071A3D', dot: '#146EF5' },
                  { label: 'Critical flags', count: queueSummary?.critical_flags, color: '#7F1D1D', dot: '#dc2626' },
                  { label: 'Low confidence', count: queueSummary?.low_confidence, color: '#92400E', dot: '#d97706' },
                  { label: 'Approved', count: queueSummary?.approved, color: '#166534', dot: '#16a34a' },
                  { label: 'Failed', count: queueSummary?.failed, color: '#7F1D1D', dot: '#dc2626' },
                ].map((r) => (
                  <button
                    key={r.label}
                    onClick={() => onNavigate(r.label === 'Failed' ? 'documents' : 'review')}
                    disabled={r.count === undefined || r.count === null}
                    className="w-full flex items-center justify-between px-3 py-2.5 rounded-md border border-[#DCE7F3] bg-white transition-colors hover:bg-[#EAF5FF]"
                  >
                    <span className="flex items-center gap-2 text-xs font-medium text-[#52627A]"><span className="w-2 h-2 rounded-full" style={{ background: r.dot }} />{r.label}</span>
                    <span className="font-sans text-base font-bold" style={{ color: r.color }}>{r.count ?? 'not available'}</span>
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
                        {c.patient_name || c.mrn || 'not available'}
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
