export interface RCACandidate {
  candidate_name: string;
  category: string;
  score: number;
  evidence_signals: string[];
  rationale: string;
}

export interface CausalChainNode {
  step: number;
  service: string;
  event_type: string;
  description: string;
  timestamp?: string;
}

export interface RCAAnalysis {
  id: string;
  analysis_key: string;
  group_key: string;
  status: 'PENDING' | 'ANALYZING' | 'COMPLETED' | 'FAILED';
  analysis_version: string;
  primary_root_cause: string;
  primary_confidence: number;
  candidates: RCACandidate[];
  causal_chain: CausalChainNode[];
  summary: string;
  created_at: string;
  updated_at: string;
}

export interface RCAListResponse {
  items: RCAAnalysis[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
