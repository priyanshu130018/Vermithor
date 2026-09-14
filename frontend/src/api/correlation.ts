import { correlationApi } from './client';
import { CorrelationGroup, CorrelationListResponse } from '../types/correlation';

export async function fetchCorrelationGroups(params?: {
  page?: number;
  page_size?: number;
  environment?: string;
}): Promise<CorrelationListResponse> {
  const response = await correlationApi.get<CorrelationListResponse>('/api/v1/correlations', { params });
  return response.data;
}

export async function fetchCorrelationGroupByKey(groupKey: string): Promise<CorrelationGroup> {
  const response = await correlationApi.get<CorrelationGroup>(`/api/v1/correlations/${groupKey}`);
  return response.data;
}
