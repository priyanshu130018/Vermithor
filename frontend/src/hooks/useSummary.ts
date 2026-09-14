import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchSummariesForIncident, generateIncidentSummary } from '../api/summaries';

export function useSummary(incidentKey?: string) {
  return useQuery({
    queryKey: ['summary', incidentKey],
    queryFn: async () => {
      if (!incidentKey) return null;
      const res = await fetchSummariesForIncident(incidentKey);
      return res.items[0] || null;
    },
    enabled: Boolean(incidentKey),
    staleTime: 15000,
    retry: 1,
  });
}

export function useGenerateSummary(incidentKey: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (regenerate: boolean = false) => generateIncidentSummary(incidentKey, regenerate),
    onSuccess: (data) => {
      queryClient.setQueryData(['summary', incidentKey], data);
      queryClient.invalidateQueries({ queryKey: ['summary', incidentKey] });
    },
  });
}
