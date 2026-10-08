import React from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { ReviewCenter as ReviewCenterView } from '../views/ReviewCenter';

export interface ReviewCenterPageProps {
  onNavigate: (view: string, documentId?: string, reviewTaskId?: string) => void;
  reviewTaskId?: string | null;
}

export function ReviewCenterPage({ onNavigate, reviewTaskId }: ReviewCenterPageProps) {
  return (
    <AppLayout activeView="review" onNavigate={onNavigate}>
      <ReviewCenterView onNavigate={onNavigate} initialTaskId={reviewTaskId} />
    </AppLayout>
  );
}
