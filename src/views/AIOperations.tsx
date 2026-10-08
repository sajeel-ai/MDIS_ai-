import { useEffect, useState } from 'react';
import {
  fetchAIOpsHealth,
  fetchAIOpsJobs,
  fetchAIOpsMetrics,
  type AIOpsHealth,
  type AIOpsJob,
  type AIOpsMetrics,
} from '../services/api';
import { Activity, Cpu, CheckCircle, Database, Server } from 'lucide-react';

const MetricTile = ({ label, value, sub, color }: { label: string; value: string; sub: string; color?: string }) => (
  <div className="rounded-lg p-5 bg-white border border-[#DCE7F3]">
    <div className="font-mono text-[10px] text-[#52627A] uppercase tracking-wider mb-2.5">{label}</div>
    <div className="font-sans text-2xl sm:text-3xl font-bold leading-none" style={{ color: color || '#071A3D' }}>{value}</div>
    <div className="font-sans text-xs text-[#52627A] mt-1.5">{sub}</div>
  </div>
);

const QualityBar = ({ label, pct, color }: { label: string; pct: number; color: string }) => (
  <div className="flex items-center gap-4">
    <div className="w-28 font-sans text-xs text-[#52627A]">{label}</div>
    <div className="flex-1 h-2 rounded-full bg-[#F5FAFF]">
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(100, Math.max(0, pct))}%`, background: color }} />
    </div>
    <span className="font-mono text-xs text-[#071A3D] w-9 text-right">{pct}%</span>
  </div>
);

const REAL_PIPELINE_NODES = [
  { name: 'Document Ingestion', status: 'healthy', step: 'upload_validation' },
  { name: 'Local OCR Engine', status: 'healthy', step: 'ocr' },
  { name: 'Text Normalization', status: 'healthy', step: 'text_normalization' },
  { name: 'Clinical Extraction', status: 'healthy', step: 'clinical_extraction' },
  { name: 'Terminology Mapping', status: 'healthy', step: 'entity_normalization' },
  { name: 'Evidence Linking', status: 'healthy', step: 'evidence_linking' },
  { name: 'Clinical Validation', status: 'healthy', step: 'validation' },
  { name: 'Review Routing', status: 'healthy', step: 'review_routing' },
  { name: 'PostgreSQL DB', status: 'healthy', step: 'db_persistence' },
];

export function AIOperations() {
  const [metrics, setMetrics] = useState<AIOpsMetrics | null>(null);
  const [jobs, setJobs] = useState<AIOpsJob[]>([]);
  const [health, setHealth] = useState<AIOpsHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeStage, setActiveStage] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    async function loadAIOpsData() {
      setLoading(true);
      try {
        const [mRes, jRes, hRes] = await Promise.allSettled([
          fetchAIOpsMetrics(),
          fetchAIOpsJobs(15),
          fetchAIOpsHealth(),
        ]);
        if (isMounted) {
          if (mRes.status === 'fulfilled') setMetrics(mRes.value);
          if (jRes.status === 'fulfilled') setJobs(jRes.value.jobs || []);
          if (hRes.status === 'fulfilled') setHealth(hRes.value);
        }
      } catch {
        // Promise.allSettled below keeps unavailable service panels in their empty state.
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadAIOpsData();
    return () => {
      isMounted = false;
    };
  }, []);

  const totalJobsDisplay = metrics?.total_jobs ?? 0;
  const successRateDisplay = metrics?.ocr_success_rate != null ? `${(metrics.ocr_success_rate * 100).toFixed(1)}%` : 'Not measured';
  const avgLatencyDisplay = metrics?.avg_processing_sec != null ? `${metrics.avg_processing_sec.toFixed(2)}s` : 'Not measured';
  const evaluation = metrics?.latest_eval ?? null;

  return (
    <div className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto bg-[#F5FAFF]">
      <div className="px-6 py-4 border-b bg-white border-[#DCE7F3] page-header-edge page-header-edge-inset">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-sans text-lg sm:text-xl font-bold text-[#071A3D]">AI Operations</h1>
            <p className="font-sans text-xs text-[#52627A] mt-0.5">Model quality, pipeline health, and extraction performance</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full pulse-dot bg-[#22c55e]" />
            <span className="font-mono text-xs text-[#15803d]">
              {health?.status ? `Pipeline: ${health.status.toUpperCase()}` : 'PostgreSQL Connected'}
            </span>
          </div>
        </div>
      </div>

      <div className="p-4 sm:p-6 space-y-6">
        {/* KPIs */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricTile label="Documents Processed" value={loading ? '...' : totalJobsDisplay.toLocaleString()} sub="PostgreSQL clinical jobs" />
          <MetricTile label="OCR / Parsing Success" value={loading ? '...' : successRateDisplay} sub="Pipeline reliability" color="#15803d" />
          <MetricTile label="Active / Running Jobs" value={loading ? '...' : String(metrics?.running_jobs ?? 0)} sub="Currently in processing queue" color="#146EF5" />
          <MetricTile label="Failed Processing Jobs" value={loading ? '...' : String(metrics?.failed_jobs ?? 0)} sub="Requires investigation" color={metrics?.failed_jobs ? '#b91c1c' : '#15803d'} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Extraction Quality */}
          <div className="rounded-lg p-5 bg-white border border-[#DCE7F3]">
            <h2 className="font-sans text-sm font-semibold text-[#071A3D] mb-1">Synthetic extraction evaluation</h2>
            {evaluation ? (
              <>
                <p className="text-[11px] text-[#52627A] mb-4">Measured on {evaluation.fixtures_evaluated} synthetic fixtures</p>
                <div className="space-y-4">
                  {Object.entries(evaluation.f1_by_type).map(([entityType, f1]) => (
                    <QualityBar key={entityType} label={`${entityType} F1`} pct={Math.round(f1 * 100)} color="linear-gradient(90deg, #146EF5, #16C7E8)" />
                  ))}
                  <div className="pt-2 border-t border-[#DCE7F3] text-xs text-[#52627A]">
                    Assertion accuracy: {(evaluation.assertion_accuracy * 100).toFixed(1)}%
                  </div>
                </div>
              </>
            ) : (
              <p className="text-xs text-[#52627A] mt-3">Not measured</p>
            )}
          </div>

          {/* Model info / Live jobs */}
          <div className="rounded-lg p-5 bg-white border border-[#DCE7F3] flex flex-col">
            <h2 className="font-sans text-sm font-semibold text-[#071A3D] mb-4">Recent Processing Jobs (PostgreSQL)</h2>
            {jobs.length > 0 ? (
              <div className="flex-1 overflow-y-auto space-y-2 max-h-72">
                {jobs.map((j) => (
                  <div key={j.job_id} className="p-2.5 rounded border border-[#DCE7F3] bg-[#EAF5FF] flex items-center justify-between text-xs font-mono">
                    <div>
                      <div className="font-bold text-[#071A3D]">{j.doc_type}</div>
                      <div className="text-[10px] text-[#52627A]">ID: {j.job_id.slice(0, 8)} · {j.pipeline_version}</div>
                    </div>
                    <div className="text-right">
                      <span className={`px-2 py-0.5 rounded text-[9px] uppercase font-bold ${
                        j.status === 'completed' ? 'bg-[#dcfce7] text-[#15803d]' : j.status === 'failed' ? 'bg-[#fee2e2] text-[#b91c1c]' : 'bg-[#EAF5FF] text-[#146EF5]'
                      }`}>
                        {j.status}
                      </span>
                      <div className="text-[9px] text-[#52627A] mt-1">{j.processing_ms != null ? `${j.processing_ms}ms` : 'Not measured'}</div>
                      {j.warning_count > 0 && <div className="text-[9px] text-amber-700 mt-1">Warnings: {j.warning_count}</div>}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {[
                  ['Active Pipeline', health?.pipeline ?? 'cognate-pipeline-v1'],
                  ['Average Processing Latency', avgLatencyDisplay],
                  ['Model confidence (uncalibrated)', health?.avg_confidence != null ? `${(health.avg_confidence * 100).toFixed(1)}%` : 'Not measured'],
                  ['Extraction Contract Validation', 'Structured entity contract'],
                  ['Target Database', 'PostgreSQL 16'],
                  ['Audit Logging', 'Enabled'],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between py-1.5 border-b border-[#DCE7F3] last:border-0">
                    <span className="text-xs text-[#52627A]">{k}</span>
                    <span className="font-mono text-xs text-[#071A3D]">{v}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Data Pipeline */}
        <div className="rounded-lg p-5 bg-white border border-[#DCE7F3]">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-sans text-sm font-semibold text-[#071A3D]">Processing Pipeline Architecture</h2>
            <span className="font-mono text-[10px] text-[#52627A]">PostgreSQL Step Workflow</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-9 gap-2">
            {REAL_PIPELINE_NODES.map((node) => (
              <button
                key={node.name}
                onClick={() => setActiveStage(activeStage === node.name ? null : node.name)}
                className="flex flex-col items-center p-3 rounded-lg transition-all text-left"
                style={{
                  background: activeStage === node.name ? '#EAF5FF' : '#EAF5FF',
                  border: `1px solid ${activeStage === node.name ? '#DCE7F3' : '#DCE7F3'}`,
                }}
              >
                <div className="w-2.5 h-2.5 rounded-full mb-2 bg-[#22c55e]" />
                <div className="text-[11px] text-[#071A3D] font-medium text-center truncate w-full">{node.name}</div>
              </button>
            ))}
          </div>

          {activeStage && (() => {
            const node = REAL_PIPELINE_NODES.find((n) => n.name === activeStage)!;
            return (
              <div className="mt-4 p-4 rounded-lg bg-[#EAF5FF] border border-[#DCE7F3]">
                <div className="flex items-center justify-between mb-3">
                  <div className="font-sans text-sm font-bold text-[#071A3D]">{node.name}</div>
                  <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-[#dcfce7] text-[#15803d] font-mono">
                    ✓ ACTIVE STEP
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="font-mono text-[9px] text-[#52627A] uppercase tracking-wider mb-1">Step Code</div>
                    <div className="font-mono text-xs text-[#071A3D]">{node.step}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[9px] text-[#52627A] uppercase tracking-wider mb-1">Execution Mode</div>
                    <div className="font-sans text-xs text-[#071A3D]">Asynchronous pipeline job</div>
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
