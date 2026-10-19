import React from 'react';
import { Sparkles, AlertCircle, CheckCircle2, ShieldCheck, RefreshCw } from 'lucide-react';
import { Card } from '../common/Card';
import { IncidentSummary } from '../../types/summary';
import { formatPercentage } from '../../lib/formatters';
import { LoadingState } from '../common/LoadingState';

interface AISummaryProps {
  summary?: IncidentSummary | null;
  isLoading: boolean;
  isGenerating: boolean;
  onGenerate: (regenerate?: boolean) => void;
}

export const AISummary: React.FC<AISummaryProps> = ({
  summary,
  isLoading,
  isGenerating,
  onGenerate,
}) => {
  if (isGenerating || (isLoading && !summary)) {
    return (
      <Card className="mb-6 border-indigo-500/30 bg-indigo-950/10">
        <LoadingState
          message="Synthesizing grounded incident summary with LLM provider..."
          size="md"
        />
      </Card>
    );
  }

  if (!summary) {
    return (
      <Card
        className="mb-6 border-dashed border-indigo-500/30 bg-indigo-950/5"
        title={
          <div className="flex items-center gap-2 text-indigo-400 font-mono text-xs font-semibold">
            <Sparkles className="w-4 h-4" />
            <span>AI INCIDENT SUMMARY</span>
          </div>
        }
      >
        <div className="py-6 text-center">
          <p className="text-xs text-slate-400 max-w-md mx-auto mb-4 font-mono">
            No natural-language summary generated for this incident version yet. Click below to synthesize grounded operational context into an executive report.
          </p>
          <button
            onClick={() => onGenerate(false)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md text-xs font-mono font-medium transition-colors cursor-pointer"
          >
            <Sparkles className="w-4 h-4" />
            <span>Synthesize AI Summary</span>
          </button>
        </div>
      </Card>
    );
  }

  const isFailed = summary.status === 'FAILED';

  if (isFailed) {
    return (
      <Card className="mb-6 border-red-900/40 bg-red-950/20">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="text-xs font-semibold font-mono text-red-300">AI Summary Generation Unavailable</h4>
            <p className="text-xs text-slate-400 mt-1">
              {summary.executive_summary || 'The LLM provider timed out or returned an unverified format. Underlying telemetry and RCA graphs remain active.'}
            </p>
            <button
              onClick={() => onGenerate(true)}
              className="mt-3 inline-flex items-center gap-1.5 px-3 py-1 bg-surface-elevated hover:bg-surface-hover border border-border rounded text-xs font-mono text-slate-300 transition-colors"
            >
              <RefreshCw className="w-3 h-3" /> Retry Generation
            </button>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card
      className="mb-6 border-indigo-500/30 bg-gradient-to-b from-indigo-950/20 to-surface"
      title={
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2 text-indigo-300 font-mono text-xs font-semibold">
            <Sparkles className="w-4 h-4 text-indigo-400" />
            <span>AI INCIDENT SUMMARY (v{summary.summary_version})</span>
          </div>
          <div className="flex items-center gap-3 text-xs font-mono text-slate-400">
            <span>Model: <strong className="text-slate-300">{summary.model_name}</strong></span>
            <button
              onClick={() => onGenerate(true)}
              title="Force regenerate summary"
              className="p-1 hover:text-slate-200 text-slate-500 rounded transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Fallback Notice */}
        {summary.is_fallback && (
          <div className="flex items-center gap-2 p-2 bg-amber-500/10 border border-amber-500/30 rounded text-xs font-mono text-amber-300">
            <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>Deterministic Grounded Fallback (LLM offline / degraded mode)</span>
          </div>
        )}

        {/* Uncertainty Banner */}
        {summary.uncertainty && (
          <div className="flex items-center gap-2 p-2 bg-purple-500/10 border border-purple-500/30 rounded text-xs font-mono text-purple-300">
            <AlertCircle className="w-4 h-4 text-purple-400 shrink-0" />
            <span>{summary.uncertainty}</span>
          </div>
        )}

        {/* Executive Summary */}
        <div>
          <h4 className="text-[11px] font-mono uppercase tracking-wider text-indigo-400 font-bold mb-1">
            Executive Summary
          </h4>
          <p className="text-xs text-slate-200 leading-relaxed font-sans bg-surface-elevated/40 p-3 rounded border border-border">
            {summary.executive_summary}
          </p>
        </div>

        {/* Narrative & Progression */}
        {summary.what_happened && (
          <div>
            <h4 className="text-[11px] font-mono uppercase tracking-wider text-slate-400 font-bold mb-1">
              Incident Progression
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed font-sans bg-surface-elevated/20 p-3 rounded border border-border/60">
              {summary.what_happened}
            </p>
          </div>
        )}

        {/* RCA Grounding Notice & Confidence */}
        <div className="flex flex-wrap items-center justify-between p-2.5 bg-surface-elevated/60 rounded border border-border text-xs font-mono">
          <span className="flex items-center gap-2 text-slate-400">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            Preserved RCA Confidence: <strong className="text-emerald-400">{formatPercentage(summary.confidence)}</strong>
          </span>
          <span className="text-[11px] text-slate-500">
            Key: {summary.summary_key} {summary.is_fallback ? '(Fallback)' : `(${summary.model_provider})`}
          </span>
        </div>

        {/* Evidence Limitations */}
        {summary.limitations && summary.limitations.length > 0 && (
          <div className="pt-2">
            <h4 className="text-[11px] font-mono uppercase tracking-wider text-amber-400 font-semibold mb-1">
              Assumptions & Limitations
            </h4>
            <ul className="list-disc list-inside text-xs text-slate-400 space-y-1 font-mono">
              {summary.limitations.map((lim, idx) => (
                <li key={idx}>{lim}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
};
