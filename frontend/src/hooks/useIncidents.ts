import { useQuery } from '@tanstack/react-query';
import { fetchIncidents, IncidentFilterParams } from '../api/incidents';

export function useIncidents(params?: IncidentFilterParams) {
  return useQuery({
    queryKey: ['incidents', params],
    queryFn: () => fetchIncidents(params),
    refetchInterval: 15000, // 15s auto-refresh for live incident tracking
    staleTime: 5000,
  });
}
