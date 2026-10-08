import { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  FileCheck2,
  ShieldCheck,
} from 'lucide-react';
import {
  fetchAIOpsHealth,
  fetchAIOpsJobs,
  fetchAIOpsMetrics,
  fetchAuditEvents,
  type AIOpsHealth,
  type AIOpsJob,
  type AIOpsMetrics,
  type AuditEvent,
  safeApiErrorMessage,
} from '../services/api';

function PageShell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto bg-[#F5FAFF]">
      <div className="border-b border-[#DCE7F3] bg-white px-6 py-5 page-header-edge page-header-edge-inset">
        <h1 className="text-xl font-bold text-[#071A3D]">{title}</h1>
        <p className="mt-1 text-xs text-[#52627A]">{subtitle}</p>
      </div>
      <div className="p-6">{children}</div>
    </div>
  );
}

function RequestError({ message }: { message: string }) {
  return <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">{message}</div>;
}

export function AnalyticsView() {
  const [metrics, setMetrics] = useState<AIOpsMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAIOpsMetrics().then(setMetrics).catch((err) => setError(safeApiErrorMessage(err, "Access restricted (admin/operator only)")));
  }, []);

  return (
    <PageShell title="Analytics" subtitle="Extraction performance and processing metrics from PostgreSQL">
      {error && <RequestError message={error} />}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ['Total jobs', metrics?.total_jobs ?? '—'],
          ['Completed', metrics?.completed_jobs ?? '—'],
          ['Failed', metrics?.failed_jobs ?? '—'],
          ['Model confidence (uncalibrated)', metrics?.avg_confidence == null ? 'Not measured' : `${Math.round(metrics.avg_confidence * 100)}%`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-[#DCE7F3] bg-white p-5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-[#52627A]">{label}</div>
            <div className="mt-3 text-2xl font-bold text-[#071A3D]">{value}</div>
          </div>
        ))}
      </div>
    </PageShell>
  );
}

export function PipelineView() {
  const [health, setHealth] = useState<AIOpsHealth | null>(null);
  const [jobs, setJobs] = useState<AIOpsJob[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchAIOpsHealth(), fetchAIOpsJobs(20)])
      .then(([healthResponse, jobsResponse]) => {
        setHealth(healthResponse);
        setJobs(jobsResponse.jobs);
      })
      .catch((err) => setError(safeApiErrorMessage(err, "Access restricted (admin/operator only)")));
  }, []);

  return (
    <PageShell title="Data Pipeline" subtitle="Live processing jobs and pipeline health from PostgreSQL">
      {error && <RequestError message={error} />}
      <div className="mb-5 grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-[#DCE7F3] bg-white p-5"><Activity className="text-blue-600" size={18} /><div className="mt-3 text-xs text-[#52627A]">Pipeline status</div><div className="mt-1 font-semibold text-[#071A3D]">{health?.status ?? 'Loading...'}</div></div>
        <div className="rounded-lg border border-[#DCE7F3] bg-white p-5"><Database className="text-[#146EF5]" size={18} /><div className="mt-3 text-xs text-[#52627A]">Pipeline version</div><div className="mt-1 font-semibold text-[#071A3D]">{health?.pipeline ?? 'Loading...'}</div></div>
        <div className="rounded-lg border border-[#DCE7F3] bg-white p-5"><Clock3 className="text-amber-600" size={18} /><div className="mt-3 text-xs text-[#52627A]">Active jobs</div><div className="mt-1 font-semibold text-[#071A3D]">{health?.active_jobs ?? '—'}</div></div>
      </div>
      <div className="rounded-lg border border-[#DCE7F3] bg-white">
        <div className="border-b border-[#DCE7F3] p-4 text-sm font-semibold text-[#071A3D]">Recent processing jobs</div>
        {jobs.length === 0 ? <div className="p-5 text-xs text-[#52627A]">No processing jobs recorded.</div> : jobs.map((job) => <div key={job.job_id} className="flex items-center justify-between border-b border-[#DCE7F3] p-4 last:border-0"><div><div className="text-xs font-semibold text-[#071A3D]">{job.doc_type}</div><div className="mt-1 text-[10px] font-mono text-[#52627A]">{job.job_id}</div></div><span className="text-[10px] font-mono uppercase text-[#52627A]">{job.status}</span></div>)}
      </div>
    </PageShell>
  );
}

export function AuditView() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAuditEvents().then((response) => setEvents(response.items)).catch((err) => setError(safeApiErrorMessage(err, "Access restricted (admin/operator only)")));
  }, []);

  return (
    <PageShell title="Audit & Compliance" subtitle="Append-only clinical workflow events recorded by the backend">
      {error && <RequestError message={error} />}
      <div className="rounded-lg border border-[#DCE7F3] bg-white">
        {events.length === 0 ? <div className="p-5 text-xs text-[#52627A]">No audit events recorded yet.</div> : events.map((event) => <div key={event.id} className="flex gap-3 border-b border-[#DCE7F3] p-4 last:border-0"><ShieldCheck size={16} className="mt-0.5 text-emerald-600" /><div className="min-w-0 flex-1"><div className="text-xs font-semibold text-[#071A3D]">{event.action}</div><div className="mt-1 text-[11px] text-[#52627A]">{event.user} · {event.resource_type ?? 'system'}</div></div><time className="text-[10px] font-mono text-[#52627A]">{new Date(event.created_at).toLocaleString()}</time></div>)}
      </div>
    </PageShell>
  );
}
