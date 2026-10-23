import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchInvestigationForIncident,
  triggerInvestigation,
  InvestigationResponse,
  TriggerInvestigationRequest,
} from '../api/investigations';

export function useInvestigation(incidentKey?: string) {
  return useQuery<InvestigationResponse | null>({
    queryKey: ['investigation', incidentKey],
    queryFn: () => (incidentKey ? fetchInvestigationForIncident(incidentKey) : Promise.resolve(null)),
    enabled: Boolean(incidentKey),
    staleTime: 30000,
  });
}

export function useTriggerInvestigation(incidentKey: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (options?: { forceRefresh?: boolean; lookbackMinutes?: number }) => {
      const payload: TriggerInvestigationRequest = {
        incident_key: incidentKey,
        lookback_minutes: options?.lookbackMinutes ?? 30,
        allow_additional_queries: true,
        max_additional_queries: 2,
        force_refresh: options?.forceRefresh ?? false,
      };
      return triggerInvestigation(payload);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['investigation', incidentKey], data);
      queryClient.invalidateQueries({ queryKey: ['investigation', incidentKey] });
      queryClient.invalidateQueries({ queryKey: ['repairs', incidentKey] });
    },
  });
}
