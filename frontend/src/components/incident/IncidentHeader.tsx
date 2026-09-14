import React from 'react';
import { Sparkles, Clock, Globe, Server, AlertTriangle } from 'lucide-react';
import { Incident } from '../../types/incident';
import { formatDateTime, formatDuration, getSeverityBadgeClass, getStatusBadgeClass } from '../../lib/formatters';

interface IncidentHeaderProps {
  incident: Incident;
  onGenerateSummary: () => void;
  isGeneratingSummary: boolean;
}

export const IncidentHeader: React.FC<IncidentHeaderProps> = ({
  incident,
  onGenerateSummary,
  isGeneratingSummary,
}) => {
  return (
    <div className="bg-surface border border-border rounded-lg p-6 mb-6 shadow-sm">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2.5 mb-2">
            <span className="font-mono text-sm font-bold text-sky-400 bg-sky-950/60 border border-sky-800/80 px-2.5 py-0.5 rounded">
              {incident.incident_key}
            </span>
            <span className={`px-2.5 py-0.5 rounded border text-xs font-semibold font-mono ${getSeverityBadgeClass(incident.severity)}`}>
              {incident.severity}
            </span>
            <span className={`px-2.5 py-0.5 rounded border text-xs font-medium font-mono ${getStatusBadgeClass(incident.status)}`}>
              {incident.status}
            </span>
          </div>
          <h1 className="text-xl font-bold text-slate-100 tracking-tight">
            {incident.title || 'Untitled Incident'}
          </h1>
          {incident.description && (
            <p className="text-xs text-slate-400 mt-1.5 max-w-3xl leading-relaxed">
              {incident.description}
            </p>
          )}
        </div>

        {/* Action Button */}
        <div className="shrink-0">
          <button
            onClick={onGenerateSummary}
            disabled={isGeneratingSummary}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 disabled:opacity-50 text-white rounded-md text-xs font-medium font-mono shadow-md shadow-sky-900/30 transition-all cursor-pointer"
          >
            <Sparkles className={`w-4 h-4 ${isGeneratingSummary ? 'animate-spin' : ''}`} />
            <span>{isGeneratingSummary ? 'Synthesizing Summary...' : 'Generate AI Summary'}</span>
          </button>
        </div>
      </div>

      {/* Telemetry Metadata Chips */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5 pt-4 border-t border-border/80 font-mono text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <Server className="w-3.5 h-3.5 text-slate-500" />
          <span>Service: <strong className="text-slate-200">{incident.service || 'N/A'}</strong></span>
        </div>
        <div className="flex items-center gap-2">
          <Globe className="w-3.5 h-3.5 text-slate-500" />
          <span>Env: <strong className="text-slate-200">{incident.environment || 'production'}</strong></span>
        </div>
        <div className="flex items-center gap-2">
          <Clock className="w-3.5 h-3.5 text-slate-500" />
          <span>Started: <strong className="text-slate-200">{formatDateTime(incident.started_at)}</strong></span>
        </div>
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-slate-500" />
          <span>Duration: <strong className="text-slate-200">{formatDuration(incident.started_at, incident.ended_at)}</strong></span>
        </div>
      </div>
    </div>
  );
};
