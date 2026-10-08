import React from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { AIOperations as AIOperationsView } from '../views/AIOperations';

export interface AIOperationsPageProps {
  onNavigate: (view: string) => void;
}

export function AIOperationsPage({ onNavigate }: AIOperationsPageProps) {
  return (
    <AppLayout activeView="aiops" onNavigate={onNavigate}>
      <AIOperationsView />
    </AppLayout>
  );
}
