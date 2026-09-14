import { anomalyApi } from './client';
import { AnomalyListResponse } from '../types/anomaly';

export async function fetchAnomalies(params?: {
  page?: number;
  page_size?: number;
  service?: string;
  is_anomaly?: boolean;
}): Promise<AnomalyListResponse> {
  const response = await anomalyApi.get<AnomalyListResponse>('/api/v1/observations', { params });
  return response.data;
}
