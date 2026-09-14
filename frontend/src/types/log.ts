export interface LogRecord {
  id: string;
  source_event_id?: string | null;
  service: string;
  environment?: string;
  severity: string;
  raw_message: string;
  normalized_message: string;
  template: string;
  domain_category: string;
  timestamp: string;
  created_at: string;
}

export interface LogSearchResultItem {
  id: string;
  service: string;
  environment?: string;
  severity: string;
  normalized_message: string;
  template: string;
  domain_category: string;
  timestamp: string;
  similarity_score: number;
}

export interface LogSearchResponse {
  query: string;
  total_matches: number;
  matches: LogSearchResultItem[];
}
