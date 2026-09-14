export type AnomalySeverity = 'CRITICAL' | 'WARNING' | 'NORMAL';

export interface AnomalyObservation {
  id: string;
  observation_id: string;
  service: string;
  metric_name: string;
  metric_value: number;
  environment?: string;
  timestamp: string;
  is_anomaly: boolean;
  anomaly_score?: number | null;
  severity: AnomalySeverity;
  detector_type?: string | null;
  created_at: string;
}

export interface AnomalyListResponse {
  items: AnomalyObservation[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
