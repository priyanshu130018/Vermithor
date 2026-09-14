export interface ImpactInfo {
  services: string[];
  severity: string;
  description: string;
}

export interface SummaryTimelineItem {
  timestamp?: string;
  event: string;
  source: string;
}

export interface SummaryEvidenceItem {
  claim: string;
  source_type: string;
  source_id: string;
  support: string;
}

export interface SummaryRemediationItem {
  action: string;
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  reason: string;
}

export interface IncidentSummary {
  id: string;
  summary_key: string;
  incident_key: string;
  status: 'PENDING' | 'GENERATING' | 'COMPLETED' | 'FAILED';
  summary_version: string;
  model_provider: string;
  model_name: string;
  executive_summary?: string | null;
  what_happened?: string | null;
  probable_root_cause?: string | null;
  impact: ImpactInfo;
  timeline: SummaryTimelineItem[];
  evidence: SummaryEvidenceItem[];
  remediation: SummaryRemediationItem[];
  confidence: number;
  limitations: string[];
  is_fallback?: boolean;
  uncertainty?: string | null;
  similar_incidents?: any[];
  debug_rag_info?: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

export interface SummaryListResponse {
  items: IncidentSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
