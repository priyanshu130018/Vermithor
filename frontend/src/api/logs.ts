import { logApi } from './client';
import { LogSearchResponse } from '../types/log';

export async function searchLogs(params: {
  query: string;
  top_k?: number;
  service?: string;
  environment?: string;
  severity?: string;
}): Promise<LogSearchResponse> {
  const response = await logApi.post<LogSearchResponse>('/api/v1/logs/search', params);
  return response.data;
}
