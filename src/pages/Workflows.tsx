import React, { useEffect, useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { GitBranch, ArrowRight } from 'lucide-react';
import { fetchAIOpsHealth, fetchAIOpsMetrics, fetchDocuments, fetchFHIRMetadata, fetchReviewPolicy } from '../services/api';

export interface WorkflowsPageProps {
  onNavigate: (view: string) => void;
}

const WORKFLOW_NODES = [
  { id: 'n1', title: 'Document Input', sub: 'Uploaded documents', type: 'Documents', color: 'bg-white' },
  { id: 'n2', title: 'OCR Processing', sub: 'Live pipeline health', type: 'OCR', color: 'bg-white' },
  { id: 'n3', title: 'Clinical Extraction', sub: 'Live extraction metrics', type: 'Extraction', color: 'bg-white' },
  { id: 'n4', title: 'Review Policy', sub: 'Live review thresholds', type: 'Review', color: 'bg-white' },
  { id: 'n5', title: 'FHIR Export', sub: 'FHIR connection metadata', type: 'FHIR', color: 'bg-white' },
];

export function WorkflowsPage({ onNavigate }: WorkflowsPageProps) {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [nodeDetails, setNodeDetails] = useState<string[]>([]);
  const [nodeLoading, setNodeLoading] = useState(false);
  useEffect(() => {
    if (!selectedNode) {
      setNodeDetails([]);
      return;
    }
    let active = true;
    setNodeLoading(true);
    setNodeDetails([]);
    const loadNodeDetails = async () => {
      try {
        let details: string[];
        if (selectedNode === 'n1') {
          const documents = await fetchDocuments(1, 1);
          details = [`${documents.total} document${documents.total === 1 ? '' : 's'} available`];
        } else if (selectedNode === 'n2') {
          const health = await fetchAIOpsHealth();
          details = [`Pipeline: ${health.pipeline}`, `Status: ${health.status}`, `Active jobs: ${health.active_jobs}`];
        } else if (selectedNode === 'n3') {
          const metrics = await fetchAIOpsMetrics();
          details = [`Total jobs: ${metrics.total_jobs}`, `Completed: ${metrics.completed_jobs}`, `OCR success: ${metrics.ocr_success_rate == null ? 'Not measured' : `${Math.round(metrics.ocr_success_rate * 100)}%`}`];
        } else if (selectedNode === 'n4') {
          const policy = await fetchReviewPolicy();
          details = [`Policy: ${policy.policy}`, `Review threshold: ${Math.round(policy.confidence_threshold * 100)}%`, `High priority threshold: ${Math.round(policy.high_priority_threshold * 100)}%`];
        } else {
          const fhir = await fetchFHIRMetadata();
          details = fhir.reachable
            ? [`Status: Connected`, `Server: ${fhir.server_name || 'not available'}`, `FHIR version: ${fhir.fhir_version || 'not available'}`]
            : [`Status: ${fhir.status === 'not_configured' ? 'Not configured' : 'Unavailable'}`, fhir.reason ? `Reason: ${fhir.reason}` : 'Configure the FHIR test server to connect'];
        }
        if (active) setNodeDetails(details);
      } catch {
        if (active) setNodeDetails(['Unable to load configuration from the backend.']);
      } finally {
        if (active) setNodeLoading(false);
      }
    };
    void loadNodeDetails();
    return () => {
      active = false;
    };
  }, [selectedNode]);

  return (
    <AppLayout activeView="workflows" onNavigate={onNavigate}>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-[#071A3D]">Clinical Workflows &amp; Automation</h1>
            <p className="text-xs text-[#52627A] mt-0.5">
              Read-only links to backend configuration and status. Workflow editing and manual execution are unavailable.
            </p>
          </div>
        </div>

        {/* Canvas Area */}
        <Card className="p-6 bg-[#EAF5FF] min-h-[420px] flex flex-col justify-between">
          <div className="flex items-center justify-between mb-4 border-b border-[#DCE7F3] pb-3 bg-white p-3 rounded-md">
            <div className="flex items-center gap-2">
              <GitBranch size={16} className="text-[#146EF5]" aria-hidden="true" />
                <span className="text-sm font-semibold text-[#071A3D]">
                Backend configuration and status checks
              </span>
            </div>
            <Badge variant="neutral">Read only</Badge>
          </div>

          {/* Connected Flow Canvas */}
          <div className="flex flex-col lg:flex-row items-center justify-between gap-4 py-8 px-4 overflow-x-auto">
            {WORKFLOW_NODES.map((node, index) => {
              const isSelected = selectedNode === node.id;
              return (
                <React.Fragment key={node.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedNode(isSelected ? null : node.id)}
                    aria-pressed={isSelected}
                    aria-label={`${node.title} — ${node.type}`}
                    className={`w-full lg:w-48 p-4 rounded-lg border border-transparent bg-white shadow-[0_8px_24px_rgba(7,26,61,0.10)] ${node.color} flex flex-col justify-between relative group text-left transition-all duration-300 ease-out hover:-translate-y-1 hover:shadow-[0_14px_30px_rgba(7,26,61,0.16)] ${
                      isSelected
                        ? 'shadow-md ring-2 ring-[#146EF5] ring-offset-1'
                        : ''
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-mono text-[#52627A] uppercase">{node.type}</span>
                    </div>
                    <h4 className="text-xs font-bold text-[#071A3D] font-sans">{node.title}</h4>
                    <p className="text-[10px] text-[#52627A] mt-1">{node.sub}</p>
                  </button>
                  {index < WORKFLOW_NODES.length - 1 && (
                    <div className="hidden lg:flex items-center text-[#52627A]" aria-hidden="true">
                      <ArrowRight size={18} />
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>

          {selectedNode && (
            <div className="mx-4 mb-4 rounded-lg bg-white p-4 shadow-[0_8px_24px_rgba(7,26,61,0.08)]" role="status" aria-live="polite">
              <div className="text-[10px] font-mono uppercase tracking-wider text-[#52627A]">Backend configuration</div>
              {nodeLoading ? (
                <div className="mt-2 text-xs text-[#52627A]">Loading live configuration…</div>
              ) : (
                <ul className="mt-2 grid gap-1 text-xs text-[#071A3D] sm:grid-cols-3">
                  {nodeDetails.map((detail) => <li key={detail}>{detail}</li>)}
                </ul>
              )}
            </div>
          )}

          <div className="flex items-center justify-between pt-4 border-t border-[#DCE7F3] text-xs text-[#52627A]">
            <span>Select any node to view its configuration details</span>
            <span className="font-mono text-[10px]">Read-only status view</span>
          </div>
        </Card>
      </div>
    </AppLayout>
  );
}
