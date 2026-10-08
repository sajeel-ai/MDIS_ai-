export type PipelineStage = 'upload' | 'ocr' | 'nlp_extraction' | 'validation' | 'export';

export interface ProcessingEvent {
  id: string;
  timestamp: string;
  documentId: string;
  documentTitle: string;
  stage: PipelineStage;
  status: 'success' | 'running' | 'failed';
  durationMs: number;
  message?: string;
  errorCode?: string;
}

export interface AIEvaluationMetric {
  metricName: string;
  value: number;
  unit: string;
  datasetContext: string;
  modelVersion: string;
  measurementPeriod: string;
  trend: 'up' | 'down' | 'neutral';
  trendValue?: string;
}

export interface SystemTelemetry {
  activeJobsCount: number;
  averageLatencyMs: number;
  throughputPerMinute: number;
  lowConfidenceRate: number;
  evaluatedMetrics: AIEvaluationMetric[];
  recentEvents: ProcessingEvent[];
}
