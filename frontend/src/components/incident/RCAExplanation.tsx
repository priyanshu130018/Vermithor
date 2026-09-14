import React from 'react';
import { GitCommit, ArrowRight, ShieldCheck, Layers } from 'lucide-react';
import { Card } from '../common/Card';
import { RCAAnalysis } from '../../types/rca';
import { formatPercentage } from '../../lib/formatters';
import { ConfidenceBar } from '../common/ConfidenceBar';

interface RCAExplanationProps {
  rca?: RCAAnalysis | null;
  isLoading: boolean;
}

export const RCAExplanation: React.FC<RCAExplanationProps> = ({ rca, isLoading }) => {
  if (isLoading) {
    return (
      <Card className="mb-6" title="Root Cause Analysis (RCA)">
        <div className="py-6 text-center text-xs font-mono text-slate-500">
          Computing directed causal graph and candidate ranking...
        </div>
      </Card>
    );
  }

  const sampleRCA: Partial<RCAAnalysis> = {
    primary_root_cause: 'PostgreSQL Connection Pool Exhaustion',
    primary_confidence: 0.89,
    candidates: [
      {
        candidate_name: 'PostgreSQL Connection Pool Exhaustion',
        category: 'DATABASE',
        score: 0.89,
        evidence_signals: ['evt-db-01', 'anom-101'],
        rationale: 'Active connections remained saturated at 100% immediately following deployment.',
      },
      {
        candidate_name: 'Recent Deployment Config Regression',
        category: 'DEPLOYMENT',
        score: 0.72,
        evidence_signals: ['dep-001'],
        rationale: 'Deployment v2.1.0 preceded latency spike by 2 minutes.',
      },
      {
        candidate_name: 'Downstream Booking API Overload',
        category: 'APPLICATION',
        score: 0.35,
        evidence_signals: ['anom-102', 'alt-500'],
        rationale: 'Symptom of upstream database failure rather than root cause.',
      },
    ],
    causal_chain: [
      { step: 1, service: 'deployment', event_type: 'DEPLOYMENT', description: 'Deployment v2.1.0 rolled out' },
      { step: 2, service: 'postgres-db', event_type: 'METRIC_ANOMALY', description: 'Database query latency spike' },
      { step: 3, service: 'postgres-db', event_type: 'LOG_ERROR', description: 'Connection pool exhausted' },
      { step: 4, service: 'booking-api', event_type: 'APPLICATION_ERROR', description: 'HTTP 500 error cascade' },
    ],
  };

  const data = rca || sampleRCA;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
      {/* Ranked Candidate Causes */}
      <Card
        title={
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-2 text-slate-200 font-mono text-xs font-semibold">
              <Layers className="w-4 h-4 text-sky-400" />
              <span>RANKED ROOT CAUSE CANDIDATES</span>
            </div>
            {data.primary_confidence !== undefined && (
              <span className="text-[11px] font-mono text-emerald-400">
                Top: {formatPercentage(data.primary_confidence)}
              </span>
            )}
          </div>
        }
      >
        <div className="space-y-3">
          {data.candidates?.map((cand, idx) => (
            <div
              key={idx}
              className={`p-3 rounded border ${
                idx === 0
                  ? 'bg-sky-950/20 border-sky-500/40 shadow-[0_0_8px_rgba(56,189,248,0.1)]'
                  : 'bg-surface-elevated/40 border-border'
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-slate-400">#{idx + 1}</span>
                  <span className="font-mono text-xs font-semibold text-slate-200">{cand.candidate_name}</span>
                </div>
                <span className="font-mono text-xs font-bold text-sky-400">
                  {formatPercentage(cand.score)}
                </span>
              </div>
              <div className="mb-2">
                <ConfidenceBar confidence={cand.score} showText={false} />
              </div>
              <p className="text-[11px] text-slate-400 leading-normal font-sans">
                {cand.rationale}
              </p>
            </div>
          ))}
        </div>
      </Card>

      {/* Causal Chain Graph */}
      <Card
        title={
          <div className="flex items-center gap-2 text-slate-200 font-mono text-xs font-semibold">
            <GitCommit className="w-4 h-4 text-sky-400" />
            <span>DIRECTED CAUSAL CHAIN</span>
          </div>
        }
      >
        <div className="space-y-3">
          {data.causal_chain?.map((node, idx) => (
            <div key={idx} className="flex items-center gap-3">
              <div className="w-6 h-6 rounded-full bg-surface-elevated border border-sky-500/40 flex items-center justify-center font-mono text-[11px] font-bold text-sky-400 shrink-0">
                {node.step}
              </div>
              <div className="flex-1 p-2.5 bg-surface-elevated/50 border border-border rounded flex items-center justify-between">
                <div>
                  <span className="font-mono text-xs font-semibold text-slate-200">
                    {node.description}
                  </span>
                  <div className="font-mono text-[10px] text-slate-400 mt-0.5">
                    Service: <strong className="text-slate-300">{node.service}</strong> | Type: {node.event_type}
                  </div>
                </div>
                {idx < (data.causal_chain?.length || 0) - 1 && (
                  <ArrowRight className="w-4 h-4 text-slate-500 shrink-0 ml-2" />
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};
