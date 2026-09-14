import { rcaApi } from './client';
import { RCAAnalysis, RCAListResponse } from '../types/rca';

export async function fetchRCAReports(params?: {
  page?: number;
  page_size?: number;
  group_key?: string;
}): Promise<RCAListResponse> {
  const response = await rcaApi.get<RCAListResponse>('/api/v1/rca', { params });
  return response.data;
}

export async function fetchRCAByKey(analysisKey: string): Promise<RCAAnalysis> {
  const response = await rcaApi.get<RCAAnalysis>(`/api/v1/rca/${analysisKey}`);
  return response.data;
}
