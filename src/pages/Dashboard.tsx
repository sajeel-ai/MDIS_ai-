import React from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Dashboard as DashboardView } from '../views/Dashboard';

export interface DashboardPageProps {
  onNavigate: (view: string) => void;
}

export function DashboardPage({ onNavigate }: DashboardPageProps) {
  return (
    <AppLayout activeView="dashboard" onNavigate={onNavigate}>
      <DashboardView onNavigate={onNavigate} />
    </AppLayout>
  );
}
