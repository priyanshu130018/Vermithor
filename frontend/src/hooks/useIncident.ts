import { useQuery } from '@tanstack/react-query';
import { fetchIncidentByKey } from '../api/incidents';

export function useIncident(incidentKey?: string) {
  return useQuery({
    queryKey: ['incident', incidentKey],
    queryFn: () => {
      if (!incidentKey) throw new Error('Incident key is required');
      return fetchIncidentByKey(incidentKey);
    },
    enabled: Boolean(incidentKey),
    refetchInterval: 15000,
    staleTime: 5000,
  });
}
