import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { useIncident } from '../hooks/useIncident';
import { useRCA } from '../hooks/useRCA';
import { useRAGContext } from '../hooks/useRetrieval';
import { useSummary, useGenerateSummary } from '../hooks/useSummary';
import { IncidentHeader } from '../components/incident/IncidentHeader';
import { IncidentOverview } from '../components/incident/IncidentOverview';
import { AISummary } from '../components/incident/AISummary';
import { IncidentTimeline } from '../components/incident/IncidentTimeline';
import { RCAExplanation } from '../components/incident/RCAExplanation';
import { CorrelationGraph } from '../components/incident/CorrelationGraph';
import { IncidentEvidence } from '../components/incident/IncidentEvidence';
import { SimilarIncidents } from '../components/incident/SimilarIncidents';
import { RunbookPanel } from '../components/incident/RunbookPanel';
import { CodeRepairPanel } from '../components/incident/CodeRepairPanel';
import { LoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';

export const IncidentDetails: React.FC = () => {
  const { incidentKey } = useParams<{ incidentKey: string }>();
  const navigate = useNavigate();

  const {
    data: incident,
    isLoading: isIncidentLoading,
    isError: isIncidentError,
    refetch: refetchIncident,
  } = useIncident(incidentKey);

  const { data: rca, isLoading: isRCALoading } = useRCA();
  const { data: ragContext, isLoading: isRAGLoading } = useRAGContext(incidentKey);
  const { data: summary, isLoading: isSummaryLoading } = useSummary(incidentKey);
  const generateSummaryMutation = useGenerateSummary(incidentKey || '');

  if (isIncidentLoading) {
    return <LoadingState message={`Loading telemetry for incident ${incidentKey}...`} />;
  }

  if (isIncidentError || !incident) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/incidents')}
          className="inline-flex items-center gap-1.5 text-xs font-mono text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Incidents
        </button>
        <ErrorState
          title="Incident Not Found"
          message={`Could not load incident ${incidentKey} from the Incident Service.`}
          onRetry={() => refetchIncident()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Navigation Breadcrumb */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate('/incidents')}
          className="inline-flex items-center gap-1.5 text-xs font-mono text-slate-400 hover:text-sky-400 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Incidents Directory
        </button>
        <div className="text-[11px] font-mono text-slate-500">
          Last refreshed: {new Date().toLocaleTimeString()}
        </div>
      </div>

      {/* 1. WHAT HAPPENED? (Incident Header & Overview) */}
      <IncidentHeader
        incident={incident}
        onGenerateSummary={() => generateSummaryMutation.mutate(false)}
        isGeneratingSummary={generateSummaryMutation.isPending}
      />

      <IncidentOverview incident={incident} rca={rca} />

      {/* AI Grounded Summary */}
      <AISummary
        summary={summary}
        isLoading={isSummaryLoading}
        isGenerating={generateSummaryMutation.isPending}
        onGenerate={(regenerate) => generateSummaryMutation.mutate(regenerate || false)}
      />

      {/* 2. WHEN? (Chronological Timeline) */}
      <IncidentTimeline timeline={summary?.timeline} />

      {/* 3. WHY? (Multi-Signal Correlation & Root Cause Analysis) */}
      <CorrelationGraph />
      <RCAExplanation rca={rca} isLoading={isRCALoading} />

      {/* 4. EVIDENCE? (Grounded Evidence Explorer) */}
      <IncidentEvidence evidence={ragContext?.context} isLoading={isRAGLoading} />

      {/* 5. WHAT NEXT? (Historical Context & SOP Runbooks) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SimilarIncidents />
        <RunbookPanel />
      </div>

      {/* 6. CODE REPAIR? (AI Code Repair Agent & Sandboxed Validation) */}
      <CodeRepairPanel incidentKey={incidentKey || ''} />
    </div>
  );
};
