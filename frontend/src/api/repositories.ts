import { apiClient } from './client';

export interface RepoConnectRequest {
  repo_identifier: string;
  installation_id?: string;
  read_only?: boolean;
}

export interface RepoConnectResponse {
  id: string;
  org_id: string;
  repo_identifier: string;
  installation_id?: string;
  read_only: boolean;
  status: string;
  connected_by?: string;
  connected_at: string;
  revoked_at?: string;
  latest_commit_sha?: string;
  permissions: Record<string, string>;
  audit_notice: string;
}

export interface RepoVerifyResponse {
  repo_identifier: string;
  status: string;
  reachable: boolean;
  read_only: boolean;
  rate_limit_remaining?: number;
  latest_commit_sha?: string;
  message: string;
}

export interface RepoDisconnectResponse {
  id: string;
  repo_identifier: string;
  status: string;
  revoked_at: string;
  message: string;
}

export interface RepositorySummaryResponse {
  id: string;
  org_id: string;
  repo_identifier: string;
  installation_id?: string;
  read_only: boolean;
  status: string;
  connected_by?: string;
  connected_at: string;
  revoked_at?: string;
}

export async function fetchConnectedRepositories(): Promise<RepositorySummaryResponse[]> {
  const resp = await apiClient.get<RepositorySummaryResponse[]>('/api/v1/agent/repositories');
  return resp.data || [];
}

export async function connectRepository(payload: RepoConnectRequest): Promise<RepoConnectResponse> {
  const resp = await apiClient.post<RepoConnectResponse>('/api/v1/agent/repositories/connect', {
    ...payload,
    read_only: true, // Strictly enforce read-only pilot mode
  });
  return resp.data;
}

export async function disconnectRepository(repoId: string): Promise<RepoDisconnectResponse> {
  const resp = await apiClient.post<RepoDisconnectResponse>(
    `/api/v1/agent/repositories/${encodeURIComponent(repoId)}/disconnect`
  );
  return resp.data;
}

export async function verifyRepository(repoId: string): Promise<RepoVerifyResponse> {
  const resp = await apiClient.get<RepoVerifyResponse>(
    `/api/v1/agent/repositories/${encodeURIComponent(repoId)}/verify`
  );
  return resp.data;
}
