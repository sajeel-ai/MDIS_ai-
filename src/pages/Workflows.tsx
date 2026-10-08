import React, { useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Plus, Play, GitBranch, ArrowRight, CheckCircle2, Info } from 'lucide-react';

export interface WorkflowsPageProps {
  onNavigate: (view: string) => void;
}

const WORKFLOW_NODES = [
  { id: 'n1', title: 'Document Input', sub: 'PDF / Image Ingestion', type: 'Trigger', color: 'border-blue-500 bg-blue-50' },
  { id: 'n2', title: 'OCR Processing', sub: 'Tesseract / Vision Engine', type: 'OCR', color: 'border-[#146EF5] bg-[#EAF5FF]' },
  { id: 'n3', title: 'Clinical NLP Extraction', sub: 'SNOMED / ICD-10 Normalization', type: 'AI Extraction', color: 'border-[#16C7E8] bg-[#EAF5FF]' },
  { id: 'n4', title: 'Model confidence (uncalibrated)', sub: 'Configured review threshold: 85%', type: 'Validation Gate', color: 'border-amber-500 bg-amber-50' },
  { id: 'n5', title: 'FHIR-shaped export', sub: 'JSON document export', type: 'Export', color: 'border-green-500 bg-green-50' },
];

export function WorkflowsPage({ onNavigate }: WorkflowsPageProps) {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  // Banner state for "not yet configured" actions
  const [infoBanner, setInfoBanner] = useState<string | null>(null);

  const showInfo = (msg: string) => {
    setInfoBanner(msg);
    // Auto-dismiss after 5 s
    setTimeout(() => setInfoBanner(null), 5000);
  };

  const handleTestPipeline = () => {
    showInfo(
      'Pipeline execution is not configured in this environment. ' +
      'Contact your system administrator to enable workflow testing.'
    );
  };

  const handleNewWorkflow = () => {
    showInfo(
      'Workflow creation is not available yet. ' +
      'This feature will be enabled in a future release.'
    );
  };

  return (
    <AppLayout activeView="workflows" onNavigate={onNavigate}>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-[#071A3D]">Clinical Workflows &amp; Automation</h1>
            <p className="text-xs text-[#52627A] mt-0.5">
              Visual pipeline automation canvas for ingestion, extraction, and FHIR export
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              icon={<Play size={14} aria-hidden="true" />}
              onClick={handleTestPipeline}
              aria-label="Test pipeline (not yet configured)"
            >
              Test Pipeline
            </Button>
            <Button
              icon={<Plus size={14} aria-hidden="true" />}
              onClick={handleNewWorkflow}
              aria-label="Create new workflow (not yet available)"
            >
              New Workflow
            </Button>
          </div>
        </div>

        {/* Info banner — shown when a non-functional action is triggered */}
        {infoBanner && (
          <div
            role="status"
            aria-live="polite"
            className="flex items-start gap-3 p-4 rounded-lg bg-[#EAF5FF] border border-[#DCE7F3] text-xs text-[#146EF5]"
          >
            <Info size={16} className="flex-shrink-0 mt-0.5 text-[#146EF5]" aria-hidden="true" />
            <span>{infoBanner}</span>
          </div>
        )}

        {/* Canvas Area */}
        <Card className="p-6 bg-[#EAF5FF] min-h-[420px] flex flex-col justify-between">
          <div className="flex items-center justify-between mb-4 border-b border-[#DCE7F3] pb-3 bg-white p-3 rounded-md">
            <div className="flex items-center gap-2">
              <GitBranch size={16} className="text-[#146EF5]" aria-hidden="true" />
              <span className="text-sm font-semibold text-[#071A3D]">
                Discharge Summary Extraction Pipeline (v2.1)
              </span>
            </div>
            <Badge variant="success">Active</Badge>
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
                    className={`w-full lg:w-48 p-4 rounded-lg border-2 bg-white shadow-xs ${node.color} flex flex-col justify-between relative group transition-all text-left ${
                      isSelected
                        ? 'shadow-md ring-2 ring-[#146EF5] ring-offset-1'
                        : 'hover:shadow-md'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-mono text-[#52627A] uppercase">{node.type}</span>
                      <CheckCircle2 size={14} className="text-green-600" aria-hidden="true" />
                    </div>
                    <h4 className="text-xs font-bold text-[#071A3D] font-sans">{node.title}</h4>
                    <p className="text-[10px] text-[#52627A] mt-1">{node.sub}</p>
                    {isSelected && (
                      <p className="text-[10px] text-[#146EF5] mt-2 font-medium border-t border-blue-100 pt-2">
                        Node configuration coming soon
                      </p>
                    )}
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

          <div className="flex items-center justify-between pt-4 border-t border-[#DCE7F3] text-xs text-[#52627A]">
            <span>Select any node to view its configuration details</span>
            <span className="font-mono text-[10px]">Canvas Scale: 100%</span>
          </div>
        </Card>
      </div>
    </AppLayout>
  );
}
