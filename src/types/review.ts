import { ClinicalEntity } from './extraction';

export type ReviewPriority = 'high' | 'medium' | 'normal';
export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'edited';

export interface ReviewItem {
  id: string;
  documentId: string;
  documentTitle: string;
  patientName: string;
  entity: ClinicalEntity;
  priority: ReviewPriority;
  status: ReviewStatus;
  issueDescription: string;
  aiConfidence: number;
  assignedTo?: string;
  createdAt: string;
}
