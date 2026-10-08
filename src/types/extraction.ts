import { Evidence } from './document';

export type EntityCategory = 'diagnosis' | 'medication' | 'symptom' | 'lab_result' | 'procedure';

export type ValidationStatus = 'validated' | 'needs_review' | 'error' | 'unprocessed';

export interface ClinicalEntity {
  id: string;
  category: EntityCategory;
  name: string;
  codeSystem?: 'ICD-10' | 'RxNorm' | 'SNOMED-CT' | 'LOINC';
  codeValue?: string;
  status: ValidationStatus;
  confidence: number;
  details?: Record<string, string | number>;
  evidence: Evidence;
}

export interface DiagnosisEntity extends ClinicalEntity {
  category: 'diagnosis';
  chronicity?: 'Chronic' | 'Acute' | 'Recurrent';
  severity?: 'Mild' | 'Moderate' | 'Severe';
}

export interface MedicationEntity extends ClinicalEntity {
  category: 'medication';
  dosage?: string;
  frequency?: string;
  route?: string;
}

export interface SymptomEntity extends ClinicalEntity {
  category: 'symptom';
  duration?: string;
  location?: string;
}

export interface LabResultEntity extends ClinicalEntity {
  category: 'lab_result';
  value?: string;
  unit?: string;
  referenceRange?: string;
  isAbnormal?: boolean;
}
