import { useQuery } from '@tanstack/react-query';
import { fetchRAGContext, fetchRunbooks } from '../api/retrieval';

export function useRAGContext(incidentKey?: string) {
  return useQuery({
    queryKey: ['rag-context', incidentKey],
    queryFn: () => {
      if (!incidentKey) throw new Error('Incident key required');
      return fetchRAGContext({ incident_key: incidentKey, top_k: 10 });
    },
    enabled: Boolean(incidentKey),
    staleTime: 10000,
    retry: 1,
  });
}

export function useRunbooks(params?: { service?: string; category?: string }) {
  return useQuery({
    queryKey: ['runbooks', params],
    queryFn: () => fetchRunbooks(params),
    staleTime: 30000,
  });
}
