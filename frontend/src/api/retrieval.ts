import { retrievalApi } from './client';
import { RAGContextResponse, Runbook, RunbookListResponse } from '../types/retrieval';

export async function fetchRAGContext(params: {
  incident_key: string;
  query?: string;
  top_k?: number;
}): Promise<RAGContextResponse> {
  const response = await retrievalApi.post<RAGContextResponse>('/api/v1/rag/context', params);
  return response.data;
}

export async function fetchRunbooks(params?: {
  page?: number;
  page_size?: number;
  service?: string;
  category?: string;
}): Promise<RunbookListResponse> {
  const response = await retrievalApi.get<RunbookListResponse>('/api/v1/runbooks', { params });
  return response.data;
}

export async function searchRunbooks(query: string, top_k: number = 10): Promise<Runbook[]> {
  const response = await retrievalApi.post<Runbook[]>('/api/v1/runbooks/search', {
    query,
    top_k,
  });
  return response.data;
}

export async function createRunbook(runbook: {
  title: string;
  description?: string;
  content: string;
  service?: string;
  environment?: string;
  category?: string;
  tags?: string[];
}): Promise<Runbook> {
  const response = await retrievalApi.post<Runbook>('/api/v1/runbooks', runbook);
  return response.data;
}

export async function deleteRunbook(runbookKey: string): Promise<void> {
  await retrievalApi.delete(`/api/v1/runbooks/${runbookKey}`);
}
