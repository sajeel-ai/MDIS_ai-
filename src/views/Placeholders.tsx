import { ArrowRight, FileText, ListChecks, Play, Settings2 } from 'lucide-react';

export function ExtractionView({ onNavigate }: { onNavigate: (view: string) => void }) {
  const actions = [
    {
      title: 'Upload and process a document',
      description: 'Add a clinical document and start OCR and extraction.',
      label: 'Open Documents',
      view: 'documents',
      icon: FileText,
      color: 'bg-blue-50 text-blue-700 border-blue-200',
    },
    {
      title: 'Inspect extracted entities',
      description: 'Review normalized diagnoses, medications, and evidence spans.',
      label: 'Open Workspace',
      view: 'clinical',
      icon: Play,
      color: 'bg-[#EAF5FF] text-[#071A3D] border-[#DCE7F3]',
    },
    {
      title: 'Validate extraction results',
      description: 'Approve, reject, or correct entities using model confidence (uncalibrated).',
      label: 'Open Review Center',
      view: 'review',
      icon: ListChecks,
      color: 'bg-amber-50 text-amber-700 border-amber-200',
    },
    {
      title: 'Monitor the pipeline',
      description: 'View processing jobs, quality metrics, and pipeline health.',
      label: 'Open AI Operations',
      view: 'aiops',
      icon: Settings2,
      color: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    },
  ];

  return (
    <div className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto bg-[#F5FAFF]">
      <div className="border-b border-[#DCE7F3] bg-white px-6 py-5 page-header-edge page-header-edge-inset">
        <h1 className="font-sans text-xl font-bold text-[#071A3D]">AI Extraction</h1>
        <p className="mt-1 text-xs text-[#52627A]">New extractions, processing queue, and results</p>
      </div>
      <div className="mx-auto max-w-5xl p-6">
        <div className="mb-5">
          <h2 className="text-base font-semibold text-[#071A3D]">Extraction workspace</h2>
          <p className="mt-1 text-xs text-[#52627A]">Choose the next step in the clinical document workflow.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {actions.map(({ title, description, label, view, icon: Icon, color }) => (
            <div key={view} className="rounded-lg border border-[#DCE7F3] bg-white p-5">
              <div className={`mb-4 flex h-9 w-9 items-center justify-center rounded-md border ${color}`}>
                <Icon size={18} />
              </div>
              <h3 className="text-sm font-semibold text-[#071A3D]">{title}</h3>
              <p className="mt-1 min-h-10 text-xs leading-relaxed text-[#52627A]">{description}</p>
              <button
                onClick={() => onNavigate(view)}
                className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-[#146EF5] hover:text-[#146EF5]"
              >
                {label} <ArrowRight size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
