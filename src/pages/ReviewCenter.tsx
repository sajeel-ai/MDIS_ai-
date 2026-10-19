import React from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { ReviewCenter as ReviewCenterView } from '../views/ReviewCenter';

export interface ReviewCenterPageProps {
  onNavigate: (view: string, documentId?: string, reviewTaskId?: string, fromStatus?: string | null) => void;
  reviewTaskId?: string | null;
  fromStatus?: string | null;
}

export function ReviewCenterPage({ onNavigate, reviewTaskId, fromStatus }: ReviewCenterPageProps) {
  return (
    <AppLayout activeView="review" onNavigate={onNavigate}>
      <ReviewCenterView
        onNavigate={onNavigate}
        initialTaskId={reviewTaskId}
        fromStatus={fromStatus}
      />
    </AppLayout>
  );
}
