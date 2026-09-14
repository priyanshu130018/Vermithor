export interface CorrelationSignal {
  signal_id: string;
  source_type: 'EVENT' | 'ANOMALY' | 'LOG' | 'DEPLOYMENT';
  service: string;
  environment?: string;
  timestamp: string;
  trace_id?: string;
  message?: string;
}

export interface CorrelationGroup {
  id: string;
  group_key: string;
  environment: string;
  services: string[];
  signals: CorrelationSignal[];
  primary_service?: string;
  aggregate_score: number;
  incident_key?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CorrelationListResponse {
  items: CorrelationGroup[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
