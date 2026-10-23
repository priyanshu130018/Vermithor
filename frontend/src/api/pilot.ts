import { apiClient } from './client';

export type IntegrationType = 'PROMETHEUS' | 'JAEGER' | 'OPENTELEMETRY' | 'REPLAY_MODE';
export type IntegrationStatus = 'NOT_CONFIGURED' | 'CONFIGURED_UNVERIFIED' | 'VERIFIED' | 'DEGRADED' | 'REVOKED';
export type TelemetryProvenance = 'LIVE_CUSTOMER_TELEMETRY' | 'SANITIZED_REPLAY_FIXTURE' | 'MOCKED_FIXTURE' | 'NOT_VERIFIED';

export type OnboardingStep =
  | 'CONFIRM_IDENTITY'
  | 'REVIEW_POLICY'
  | 'SELECT_TELEMETRY'
  | 'VALIDATE_CONFIG'
  | 'CONNECTIVITY_CHECK'
  | 'SAMPLE_INVESTIGATION'
  | 'RECORD_FEEDBACK'
  | 'VIEW_READINESS';

export interface IntegrationResponse {
  id: string;
  org_id: string;
  integration_type: IntegrationType;
  name: string;
  endpoint_url?: string;
  status: IntegrationStatus;
  is_verified: boolean;
  verified_at?: string;
  last_checked_at?: string;
  last_error?: string;
  approved_by?: string;
  approved_at?: string;
  auth_type: string;
  auth_credentials_masked?: string;
  telemetry_provenance: TelemetryProvenance;
  created_at: string;
  updated_at: string;
}

export interface IntegrationVerifyResponse {
  id: string;
  integration_type: IntegrationType;
  name: string;
  status: IntegrationStatus;
  reachable: boolean;
  is_verified: boolean;
  telemetry_provenance: TelemetryProvenance;
  probe_latency_ms?: number;
  message: string;
  active_targets_count?: number;
  error?: string;
}

export interface GovernancePolicyResponse {
  id: string;
  org_id: string;
  onboarding_completed: boolean;
  current_onboarding_step: number;
  completed_steps: string[];
  collection_enabled: boolean;
  investigations_paused: boolean;
  allow_external_llm: boolean;
  redact_sensitive_fields: boolean;
  retention_days: number;
  acknowledged_read_only: boolean;
  acknowledged_by?: string;
  acknowledged_at?: string;
  updated_at: string;
}

export interface PilotReadinessResponse {
  org_id: string;
  onboarding_completed: boolean;
  current_step: number;
  completed_steps: string[];
  integrations: IntegrationResponse[];
  last_telemetry_check?: {
    integration_type: string;
    name: string;
    timestamp?: string;
    status: string;
    telemetry_provenance: string;
  };
  latest_investigation?: {
    investigation_key: string;
    incident_key: string;
    status: string;
    target_service: string;
    leading_hypothesis?: string;
    confidence: number;
    latency_ms?: number;
    is_fallback: boolean;
    telemetry_provenance: string;
  };
  evidence_completeness: {
    total_evidence_items: number;
    citation_validity_rate: number;
    evidence_support_rate: number;
  };
  abstentions_and_unresolved: {
    abstentions_count: number;
    unresolved_feedback_count: number;
    total_feedback_count: number;
  };
  operator_feedback_history: Array<{
    id: string;
    investigation_key: string;
    incident_key: string;
    feedback_status: string;
    operator_id: string;
    confirmed_root_cause?: string;
    created_at: string;
  }>;
  rate_limit_and_resilience: {
    rate_limit_enabled: boolean;
    redis_healthy: boolean;
    degraded_mode_partitioned: boolean;
  };
  provenance_breakdown: {
    live_production_incidents_count: number;
    sanitized_postmortem_replays_count: number;
    mocked_cases_count: number;
    live_telemetry_verified: boolean;
  };
  governance_policy: {
    collection_enabled: boolean;
    investigations_paused: boolean;
    allow_external_llm: boolean;
    redact_sensitive_fields: boolean;
    retention_days: number;
    acknowledged_read_only: boolean;
  };
  blockers: string[];
  readiness_verdict: string;
  readiness_summary: string;
}

export interface PilotAuditLogResponse {
  id: string;
  org_id: string;
  actor_sub: string;
  actor_role?: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  details_json?: Record<string, any>;
  created_at: string;
}

export interface DataPurgeResponse {
  status: string;
  org_id: string;
  incident_key?: string;
  deleted_investigations_count: number;
  deleted_feedback_count: number;
  deleted_repairs_count: number;
  deleted_observations_count: number;
  deleted_events_count: number;
  cache_keys_purged: number;
  queued_tasks_revoked: number;
  purged_at: string;
  message: string;
}

// --- API Client Methods ---

export async function fetchPilotReadiness(): Promise<PilotReadinessResponse> {
  const res = await apiClient.get<PilotReadinessResponse>('/api/v1/agent/pilot/readiness');
  return res.data;
}

export async function fetchOnboardingStatus(): Promise<GovernancePolicyResponse> {
  const res = await apiClient.get<GovernancePolicyResponse>('/api/v1/agent/pilot/status');
  return res.data;
}

export async function submitOnboardingStep(
  step: OnboardingStep,
  notes?: string,
  acknowledgedReadOnly?: boolean
): Promise<GovernancePolicyResponse> {
  const res = await apiClient.post<GovernancePolicyResponse>('/api/v1/agent/pilot/onboarding/step', {
    step,
    notes,
    acknowledged_read_only: acknowledgedReadOnly,
  });
  return res.data;
}

export async function fetchIntegrations(): Promise<IntegrationResponse[]> {
  const res = await apiClient.get<IntegrationResponse[]>('/api/v1/agent/pilot/integrations');
  return res.data;
}

export async function configureIntegration(payload: {
  integration_type: IntegrationType;
  name: string;
  endpoint_url?: string;
  auth_type: string;
  auth_credential?: string;
  allow_internal_hosts?: boolean;
}): Promise<IntegrationResponse> {
  const res = await apiClient.post<IntegrationResponse>('/api/v1/agent/pilot/integrations/configure', payload);
  return res.data;
}

export async function verifyIntegration(id: string): Promise<IntegrationVerifyResponse> {
  const res = await apiClient.post<IntegrationVerifyResponse>(`/api/v1/agent/pilot/integrations/${id}/verify`);
  return res.data;
}

export async function disconnectIntegration(id: string): Promise<IntegrationResponse> {
  const res = await apiClient.post<IntegrationResponse>(`/api/v1/agent/pilot/integrations/${id}/disconnect`);
  return res.data;
}

export async function updateGovernancePolicy(payload: {
  collection_enabled?: boolean;
  investigations_paused?: boolean;
  allow_external_llm?: boolean;
  redact_sensitive_fields?: boolean;
  retention_days?: number;
}): Promise<GovernancePolicyResponse> {
  const res = await apiClient.post<GovernancePolicyResponse>('/api/v1/agent/pilot/governance/policy', payload);
  return res.data;
}

export async function purgeOrganizationData(payload: {
  confirm_organization_id: string;
  incident_key?: string;
  purge_all_pilot_data?: boolean;
}): Promise<DataPurgeResponse> {
  const res = await apiClient.post<DataPurgeResponse>('/api/v1/agent/pilot/governance/purge', payload);
  return res.data;
}

export async function fetchPilotAuditLogs(limit: number = 50): Promise<PilotAuditLogResponse[]> {
  const res = await apiClient.get<PilotAuditLogResponse[]>(`/api/v1/agent/pilot/audit-log?limit=${limit}`);
  return res.data;
}
