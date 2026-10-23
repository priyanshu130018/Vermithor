import { apiClient } from './client';

export interface HypothesisEvaluation {
  hypothesis: string;
  candidate_type: string;
  original_score: number;
  calibrated_status: string;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  reasoning: string;
}

export interface DiagnosticStep {
  action: string;
  target_service: string;
  rationale: string;
  priority: string;
  requires_human_approval: boolean;
}

export interface InvestigationEvidenceItem {
  evidence_id: string;
  source_type: string;
  source_id: string;
  service: string;
  timestamp?: string;
  claim: string;
  data: Record<string, any>;
  is_verified?: boolean;
  verification_status?: string;
}

export interface InvestigationReport {
  investigation_id: string;
  incident_key: string;
  title: string;
  target_service: string;
  environment: string;
  time_window: Record<string, any>;
  observed_facts: string[];
  inferred_relationships: string[];
  leading_hypothesis: string;
  hypothesis_confidence: number;
  hypotheses_evaluated: HypothesisEvaluation[];
  alternative_explanations: string[];
  confirmed_findings: string[];
  missing_evidence: string[];
  contradictory_evidence: string[];
  uncertainty_assessment: string;
  recommended_diagnostic_steps: DiagnosticStep[];
  runbook_references: Array<Record<string, any>>;
  evidence_items: InvestigationEvidenceItem[];
  model_provider: string;
  model_name?: string;
  is_fallback: boolean;
}

export interface InvestigationResponse {
  id: string;
  investigation_key: string;
  incident_key: string;
  status: 'PENDING' | 'INVESTIGATING' | 'COMPLETED' | 'INSUFFICIENT_EVIDENCE' | 'FAILED';
  target_service: string;
  environment: string;
  leading_hypothesis?: string;
  confidence: number;
  is_fallback: boolean;
  model_provider: string;
  model_name?: string;
  report?: InvestigationReport;
  created_at: string;
  completed_at?: string;
}

export interface TriggerInvestigationRequest {
  incident_key: string;
  lookback_minutes?: number;
  allow_additional_queries?: boolean;
  max_additional_queries?: number;
  force_refresh?: boolean;
}

export async function fetchInvestigationForIncident(
  incidentKey: string
): Promise<InvestigationResponse | null> {
  try {
    const resp = await apiClient.get<InvestigationResponse>(
      `/api/v1/agent/investigations/incident/${encodeURIComponent(incidentKey)}`
    );
    return resp.data;
  } catch (err: any) {
    if (err?.response?.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function fetchInvestigationById(
  investigationId: string
): Promise<InvestigationResponse> {
  const resp = await apiClient.get<InvestigationResponse>(
    `/api/v1/agent/investigations/${encodeURIComponent(investigationId)}`
  );
  return resp.data;
}

export async function triggerInvestigation(
  payload: TriggerInvestigationRequest
): Promise<InvestigationResponse> {
  const resp = await apiClient.post<InvestigationResponse>(
    '/api/v1/agent/investigations',
    payload
  );
  return resp.data;
}

export type FeedbackStatus = 'CONFIRMED' | 'REJECTED' | 'UNRESOLVED';

export interface InvestigationFeedbackCreate {
  feedback_status: FeedbackStatus;
  confirmed_root_cause?: string;
  evidence_reference?: string;
  explanation?: string;
}

export interface InvestigationFeedbackResponse {
  id: string;
  investigation_key: string;
  incident_key: string;
  org_id: string;
  feedback_status: FeedbackStatus;
  operator_id: string;
  confirmed_root_cause?: string;
  evidence_reference?: string;
  explanation?: string;
  created_at: string;
}

export async function submitInvestigationFeedback(
  investigationKey: string,
  payload: InvestigationFeedbackCreate
): Promise<InvestigationFeedbackResponse> {
  const resp = await apiClient.post<InvestigationFeedbackResponse>(
    `/api/v1/agent/investigations/${encodeURIComponent(investigationKey)}/feedback`,
    payload
  );
  return resp.data;
}

export async function fetchInvestigationFeedback(
  investigationKey: string
): Promise<InvestigationFeedbackResponse[]> {
  const resp = await apiClient.get<InvestigationFeedbackResponse[]>(
    `/api/v1/agent/investigations/${encodeURIComponent(investigationKey)}/feedback`
  );
  return resp.data;
}

