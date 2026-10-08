import { useEffect, useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { ActivitySquare, CheckCircle2, Database, Server, XCircle } from 'lucide-react';
import { ApiError, fetchAIOpsHealth, fetchFHIRMetadata, safeApiErrorMessage, type AIOpsHealth, type FHIRMetadataCheck } from '../services/api';

export interface IntegrationsPageProps {
  onNavigate: (view: string) => void;
}

export function IntegrationsPage({ onNavigate }: IntegrationsPageProps) {
  const [health, setHealth] = useState<AIOpsHealth | null>(null);
  const [fhir, setFHIR] = useState<FHIRMetadataCheck | null>(null);
  const [healthAccessRestricted, setHealthAccessRestricted] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [fhirError, setFHIRError] = useState<string | null>(null);
  const [fhirRestricted, setFhirRestricted] = useState(false);
  const restrictedLabel = 'Access restricted (admin/operator only)';

  useEffect(() => {
    fetchAIOpsHealth().then((result) => {
      setHealth(result);
      setHealthAccessRestricted(false);
      setHealthError(null);
    }).catch((err: unknown) => {
      if (err instanceof ApiError && err.status === 403) {
        setHealthAccessRestricted(true);
        return;
      }
      setHealthError(safeApiErrorMessage(err, restrictedLabel));
    });
    fetchFHIRMetadata().then(setFHIR).catch((err: unknown) => {
      setFhirRestricted(err instanceof ApiError && err.status === 403);
      setFHIRError(safeApiErrorMessage(err, restrictedLabel));
    });
  }, []);

  const connections = [
    { name: 'Cognate API', detail: 'FastAPI service', icon: Server, status: health ? 'Connected' : healthAccessRestricted ? restrictedLabel : 'Unavailable' },
    { name: 'PostgreSQL', detail: 'Clinical records and audit data', icon: Database, status: health ? 'Connected' : healthAccessRestricted ? restrictedLabel : 'Unavailable' },
    { name: 'Clinical processing pipeline', detail: health?.pipeline ?? (healthAccessRestricted ? 'Admin/operator access required' : 'Not available'), icon: ActivitySquare, status: health?.status ?? (healthAccessRestricted ? restrictedLabel : 'Unavailable') },
    { name: 'FHIR R4 export (base-resource validated)', detail: fhir?.reachable ? `${fhir.server_name || 'FHIR server'} · FHIR ${fhir.fhir_version || fhir.resource?.fhirVersion || ''}` : 'Test server metadata check', icon: Database, status: fhir?.reachable ? 'Connected' : fhirRestricted ? restrictedLabel : fhir?.reason ? `Unavailable (${fhir.reason})` : fhirError || fhir?.configured ? 'Unavailable' : 'Not configured' },
  ];

  return (
    <AppLayout activeView="integrations" onNavigate={onNavigate}>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-bold text-[#071A3D]">System Connections</h1>
          <p className="mt-0.5 text-xs text-[#52627A]">Live connection status for this Cognate installation</p>
        </div>
        {healthError && <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">{healthError}</div>}
        {fhirError && <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">FHIR metadata check failed: {fhirError}</div>}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {connections.map((connection) => {
            const Icon = connection.icon;
            const isConnected = connection.status === 'Connected' || connection.status === 'healthy';
            return (
              <div key={connection.name} className="rounded-lg border border-[#DCE7F3] bg-white p-5">
                <div className="flex items-start justify-between">
                  <div className="rounded-md border border-[#DCE7F3] bg-[#EAF5FF] p-2.5"><Icon size={20} className="text-blue-600" /></div>
                  {isConnected ? <CheckCircle2 size={18} className="text-emerald-600" /> : <XCircle size={18} className="text-rose-600" />}
                </div>
                <h2 className="mt-4 text-sm font-semibold text-[#071A3D]">{connection.name}</h2>
                <p className="mt-1 text-xs text-[#52627A]">{connection.detail}</p>
                <div className={`mt-4 text-[10px] font-mono uppercase ${isConnected ? 'text-emerald-700' : 'text-rose-700'}`}>{connection.status}</div>
              </div>
            );
          })}
        </div>
      </div>
    </AppLayout>
  );
}
