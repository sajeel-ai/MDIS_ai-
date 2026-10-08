import React from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { ClinicalWorkspace as ClinicalWorkspaceView } from '../views/ClinicalWorkspace';

export interface ClinicalWorkspacePageProps {
  onNavigate: (view: string) => void;
  documentId?: string | null;
}

export function ClinicalWorkspacePage({ onNavigate, documentId }: ClinicalWorkspacePageProps) {
  return (
    <AppLayout activeView="clinical" onNavigate={onNavigate}>
      <div className="flex h-full min-h-0 flex-col overflow-hidden">
        <ClinicalWorkspaceView documentId={documentId} onNavigate={onNavigate} />
      </div>
    </AppLayout>
  );
}
