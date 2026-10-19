import { apiClient } from './client';

export interface TestExecutionResult {
  status: string;
  total_tests: number;
  passed: number;
  failed: number;
  skipped: number;
  commands_run: string[];
  stdout: string;
  stderr: string;
  duration_ms: number;
  error_message?: string;
  environment_isolated: boolean;
}

export interface RepairReport {
  incident_key: string;
  investigation_key: string;
  suspected_defect: string;
  evidence_citations: string[];
  inspected_files: string[];
  proposed_patch?: string;
  patch_hash?: string;
  expected_behavior: string;
  potential_regressions: string[];
  security_implications: string[];
  tests_required: string[];
  remaining_uncertainty: string;
  validation_result?: TestExecutionResult;
  pull_request_url?: string;
  pull_request_number?: number;
  requires_human_approval: boolean;
  model_provider: string;
  model_name?: string;
  is_fallback: boolean;
}

export interface RepairResponse {
  id: string;
  repair_key: string;
  investigation_key: string;
  incident_key: string;
  status: string;
  repository_url?: string;
  base_commit?: string;
  target_branch: string;
  repair_branch?: string;
  suspected_defect?: string;
  evidence_citations?: string[];
  inspected_files?: string[];
  proposed_patch?: string;
  patch_hash?: string;
  files_changed?: string[];
  test_commands?: string[];
  test_results?: TestExecutionResult;
  validation_status: string;
  pull_request_url?: string;
  pull_request_number?: number;
  requires_human_approval: boolean;
  approval_status: string;
  approved_by?: string;
  approval_notes?: string;
  approved_at?: string;
  model_provider: string;
  model_name?: string;
  is_fallback: boolean;
  iteration_count: number;
  error_message?: string;
  report_json?: RepairReport;
  created_at: string;
  updated_at: string;
}

export interface TriggerRepairRequest {
  investigation_key: string;
  repository_url?: string;
  target_branch?: string;
  custom_test_command?: string;
  auto_create_pr?: boolean;
}

export interface ApprovalRequest {
  action: 'APPROVE' | 'REJECT';
  notes?: string;
  reviewer?: string;
  expected_patch_hash?: string;
}

export async function fetchRepairsForIncident(incidentKey: string): Promise<RepairResponse[]> {
  const resp = await apiClient.get<{ items: RepairResponse[]; total: number }>(
    `/api/v1/agent/repairs?incident_key=${encodeURIComponent(incidentKey)}`
  );
  return resp.data.items || [];
}

export async function triggerCodeRepair(payload: TriggerRepairRequest): Promise<RepairResponse> {
  const resp = await apiClient.post<RepairResponse>('/api/v1/agent/repairs', payload);
  return resp.data;
}

export async function submitRepairApproval(
  repairId: string,
  approval: ApprovalRequest
): Promise<RepairResponse> {
  const resp = await apiClient.post<RepairResponse>(
    `/api/v1/agent/repairs/${encodeURIComponent(repairId)}/approve`,
    approval
  );
  return resp.data;
}
