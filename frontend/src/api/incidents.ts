import { incidentApi } from './client';
import { Incident, IncidentListResponse, IncidentStatus, IncidentSeverity } from '../types/incident';

export interface IncidentFilterParams {
  page?: number;
  page_size?: number;
  service?: string;
  environment?: string;
  severity?: IncidentSeverity;
  status?: IncidentStatus;
}

export async function fetchIncidents(params?: IncidentFilterParams): Promise<IncidentListResponse> {
  const response = await incidentApi.get<IncidentListResponse>('/api/v1/incidents', { params });
  return response.data;
}

export async function fetchIncidentByKey(incidentKey: string): Promise<Incident> {
  const response = await incidentApi.get<Incident>(`/api/v1/incidents/${incidentKey}`);
  return response.data;
}

export async function updateIncidentStatus(incidentKey: string, status: IncidentStatus): Promise<Incident> {
  const response = await incidentApi.put<Incident>(`/api/v1/incidents/${incidentKey}/status`, { status });
  return response.data;
}
