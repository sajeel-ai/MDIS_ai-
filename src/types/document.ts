export type DocumentStatus = 'processed' | 'needs_review' | 'failed' | 'processing' | 'queued';

export type DocumentType =
  | 'Lab Report'
  | 'Prescription'
  | 'Discharge Summary'
  | 'Clinical Note'
  | 'Radiology Report'
  | 'Pathology Report';

export interface Evidence {
  pageNumber: number;
  section: string;
  exactQuote: string;
  boundingBox?: { x: number; y: number; width: number; height: number };
  confidenceScore: number;
}

export interface DocumentItem {
  id: string;
  title: string;
  patientId: string;
  patientName: string;
  type: DocumentType;
  status: DocumentStatus;
  uploadDate: string;
  processedDate?: string;
  confidenceScore: number;
  entityCount: number;
  flaggedCount: number;
  fileSize: string;
  mimeType: string;
}
