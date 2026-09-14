import { summaryApi } from './client';
import { IncidentSummary, SummaryListResponse } from '../types/summary';

export async function fetchSummaryByKey(summaryKey: string): Promise<IncidentSummary> {
  const response = await summaryApi.get<IncidentSummary>(`/api/v1/summaries/${summaryKey}`);
  return response.data;
}

export async function fetchSummariesForIncident(incidentKey: string): Promise<SummaryListResponse> {
  const response = await summaryApi.get<SummaryListResponse>('/api/v1/summaries', {
    params: { incident_key: incidentKey },
  });
  return response.data;
}

export async function generateIncidentSummary(
  incidentKey: string,
  regenerate: boolean = false
): Promise<IncidentSummary> {
  const response = await summaryApi.post<IncidentSummary>(
    `/api/v1/summaries/incident/${incidentKey}`,
    null,
    {
      params: { regenerate },
    }
  );
  return response.data;
}
