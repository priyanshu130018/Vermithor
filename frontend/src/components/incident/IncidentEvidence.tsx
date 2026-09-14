import React, { useState } from 'react';
import { Database, Filter, Tag } from 'lucide-react';
import { Card } from '../common/Card';
import { ContextItem } from '../../types/retrieval';
import { formatPercentage } from '../../lib/formatters';

interface IncidentEvidenceProps {
  evidence?: ContextItem[];
  isLoading: boolean;
}

export const IncidentEvidence: React.FC<IncidentEvidenceProps> = ({ evidence = [], isLoading }) => {
  const [selectedFilter, setSelectedFilter] = useState<string>('ALL');

  const sampleEvidence: ContextItem[] = [
    {
      source_type: 'LOG',
      source_id: 'evt-db-01',
      title: 'PostgreSQL Connection Saturation',
      content: 'FATAL: remaining connection slots are reserved for non-replication superuser connections',
      service: 'postgres-db',
      environment: 'production',
      final_score: 0.94,
      semantic_score: 0.96,
      metadata_score: 1.0,
      recency_score: 0.98,
      source_weight: 0.8,
      citation: '[LOG:evt-db-01]',
    },
    {
      source_type: 'RCA',
      source_id: 'RCA-000001',
      title: 'Root Cause Report: DB Saturation',
      content: 'Multi-signal correlation isolated connection saturation as top causal factor with 89% confidence.',
      final_score: 0.91,
      semantic_score: 0.90,
      metadata_score: 1.0,
      recency_score: 0.95,
      source_weight: 1.0,
      citation: '[RCA:RCA-000001]',
    },
    {
      source_type: 'RUNBOOK',
      source_id: 'RB-000001',
      title: 'DB Connection Pool Remediation SOP',
      content: '1. Inspect pg_stat_activity 2. Scale pgbouncer max_client_conn 3. Restart stuck workers',
      service: 'postgres-db',
      final_score: 0.88,
      semantic_score: 0.89,
      metadata_score: 1.0,
      recency_score: 0.90,
      source_weight: 0.9,
      citation: '[RUNBOOK:RB-000001]',
    },
  ];

  const items = evidence.length > 0 ? evidence : sampleEvidence;
  const filteredItems = selectedFilter === 'ALL'
    ? items
    : items.filter((item) => item.source_type.toUpperCase() === selectedFilter);

  const filters = ['ALL', 'LOG', 'RCA', 'RUNBOOK', 'INCIDENT', 'DEPLOYMENT'];

  return (
    <Card
      className="mb-6"
      title={
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 text-slate-200 font-mono text-xs font-semibold">
            <Database className="w-4 h-4 text-sky-400" />
            <span>GROUNDED OPERATIONAL EVIDENCE ({items.length} SOURCES)</span>
          </div>
          <div className="flex items-center gap-1.5 overflow-x-auto">
            {filters.map((f) => (
              <button
                key={f}
                onClick={() => setSelectedFilter(f)}
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium transition-colors ${
                  selectedFilter === f
                    ? 'bg-sky-500/20 text-sky-400 border border-sky-500/40'
                    : 'text-slate-400 hover:text-slate-200 bg-surface-elevated'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      }
    >
      {isLoading ? (
        <div className="py-8 text-center text-xs font-mono text-slate-500">Retrieving operational evidence...</div>
      ) : (
        <div className="space-y-3">
          {filteredItems.map((item, idx) => (
            <div
              key={idx}
              className="p-3 bg-surface-elevated/40 border border-border rounded-md hover:border-slate-700 transition-colors"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-sky-400 bg-sky-950/60 px-2 py-0.5 rounded border border-sky-900">
                    {item.citation || `[${item.source_type}:${item.source_id}]`}
                  </span>
                  <span className="font-mono text-xs font-semibold text-slate-200">
                    {item.title}
                  </span>
                </div>
                <div className="flex items-center gap-3 font-mono text-[11px]">
                  <span className="text-slate-400">
                    Score: <strong className="text-emerald-400">{formatPercentage(item.final_score)}</strong>
                  </span>
                  {item.service && (
                    <span className="text-slate-400">
                      Service: <strong className="text-slate-300">{item.service}</strong>
                    </span>
                  )}
                </div>
              </div>
              <p className="text-xs text-slate-300 font-mono bg-background/50 p-2 rounded border border-border/50 whitespace-pre-wrap">
                {item.content}
              </p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};
