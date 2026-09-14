import React from 'react';
import { Target, Gauge, ShieldAlert, Cpu } from 'lucide-react';
import { Card } from '../common/Card';
import { Incident } from '../../types/incident';
import { RCAAnalysis } from '../../types/rca';
import { ConfidenceBar } from '../common/ConfidenceBar';

interface IncidentOverviewProps {
  incident: Incident;
  rca?: RCAAnalysis | null;
}

export const IncidentOverview: React.FC<IncidentOverviewProps> = ({ incident, rca }) => {
  const rootCause = rca?.primary_root_cause || 'Analyzing telemetry signals...';
  const confidence = rca?.primary_confidence ?? incident.confidence;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      {/* Probable Root Cause */}
      <Card
        className="border-sky-500/20 bg-sky-950/10"
        title={
          <div className="flex items-center gap-2 text-sky-400 font-mono text-xs font-semibold">
            <Target className="w-4 h-4" />
            <span>PROBABLE ROOT CAUSE</span>
          </div>
        }
      >
        <div className="text-base font-semibold text-slate-100 mt-1">
          {rootCause}
        </div>
        <p className="text-xs text-slate-400 mt-2 font-mono">
          Identified via multi-factor directed causal graph analysis
        </p>
      </Card>

      {/* Structured Confidence Score */}
      <Card
        className="border-emerald-500/20 bg-emerald-950/10"
        title={
          <div className="flex items-center gap-2 text-emerald-400 font-mono text-xs font-semibold">
            <Gauge className="w-4 h-4" />
            <span>RCA CONFIDENCE SCORE</span>
          </div>
        }
      >
        <div className="mt-1">
          <ConfidenceBar confidence={confidence} showText />
        </div>
        <p className="text-xs text-slate-400 mt-3 font-mono">
          Based on temporal proximity, trace linkage, and topology weights
        </p>
      </Card>

      {/* Impact & Blast Radius */}
      <Card
        className="border-amber-500/20 bg-amber-950/10"
        title={
          <div className="flex items-center gap-2 text-amber-400 font-mono text-xs font-semibold">
            <ShieldAlert className="w-4 h-4" />
            <span>BLAST RADIUS</span>
          </div>
        }
      >
        <div className="flex items-center gap-2 mt-1">
          <span className="font-mono text-xs font-bold text-amber-300 bg-amber-950/80 px-2 py-0.5 rounded border border-amber-800">
            {incident.service || 'booking-api'}
          </span>
          <span className="text-xs text-slate-400 font-mono">
            Environment: {incident.environment || 'production'}
          </span>
        </div>
        <p className="text-xs text-slate-400 mt-3 font-mono">
          Severity: <strong className="text-slate-200">{incident.severity}</strong>
        </p>
      </Card>
    </div>
  );
};
