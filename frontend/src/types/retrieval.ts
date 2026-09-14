export interface Runbook {
  id: string;
  runbook_key: string;
  title: string;
  description?: string | null;
  content: string;
  service?: string | null;
  environment?: string | null;
  category?: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface RunbookListResponse {
  items: Runbook[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ContextItem {
  source_type: 'LOG' | 'INCIDENT' | 'RCA' | 'RUNBOOK' | 'DEPLOYMENT';
  source_id: string;
  title: string;
  content: string;
  service?: string;
  environment?: string;
  final_score: number;
  semantic_score: number;
  metadata_score: number;
  recency_score: number;
  source_weight: number;
  citation: string;
  timestamp?: string;
}

export interface RAGContextResponse {
  incident_key?: string;
  query?: string;
  total_results: number;
  total_characters: number;
  context_text: string;
  context: ContextItem[];
  warnings: string[];
}
