export type WorkflowStatus = 'active' | 'draft' | 'paused';
export type NodeType = 'trigger' | 'ocr' | 'extraction' | 'validation' | 'api_output' | 'review_gate';

export interface WorkflowNode {
  id: string;
  type: NodeType;
  label: string;
  description: string;
  config?: Record<string, string | number | boolean>;
  position: { x: number; y: number };
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
}

export interface WorkflowItem {
  id: string;
  name: string;
  description: string;
  status: WorkflowStatus;
  triggerType: string;
  processedToday: number;
  accuracyRate: number;
  lastRun: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}
