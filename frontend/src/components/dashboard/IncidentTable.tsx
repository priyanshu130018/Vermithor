import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { Incident } from '../../types/incident';
import { formatDateTime, formatDuration, getSeverityBadgeClass, getStatusBadgeClass } from '../../lib/formatters';
import { ConfidenceBar } from '../common/ConfidenceBar';

interface IncidentTableProps {
  incidents: Incident[];
  compact?: boolean;
}

export const IncidentTable: React.FC<IncidentTableProps> = ({ incidents, compact = false }) => {
  const navigate = useNavigate();

  if (incidents.length === 0) {
    return (
      <div className="py-8 text-center text-slate-500 font-mono text-xs">
        No active incidents detected. All services operating normally.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse text-xs">
        <thead>
          <tr className="border-b border-border bg-surface-elevated/40 text-slate-400 font-mono uppercase text-[11px] tracking-wider">
            <th className="py-2.5 px-4 font-semibold">Incident</th>
            <th className="py-2.5 px-4 font-semibold">Severity</th>
            <th className="py-2.5 px-4 font-semibold">Service</th>
            <th className="py-2.5 px-4 font-semibold">Environment</th>
            <th className="py-2.5 px-4 font-semibold">Started</th>
            <th className="py-2.5 px-4 font-semibold">Duration</th>
            <th className="py-2.5 px-4 font-semibold">Status</th>
            <th className="py-2.5 px-4 font-semibold w-28">Confidence</th>
            <th className="py-2.5 px-3 text-right"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60 font-mono">
          {incidents.map((incident) => (
            <tr
              key={incident.id || incident.incident_key}
              onClick={() => navigate(`/incidents/${incident.incident_key}`)}
              className="hover:bg-surface-elevated/60 transition-colors cursor-pointer group"
            >
              <td className="py-3 px-4">
                <div className="font-semibold text-slate-200 group-hover:text-sky-400 transition-colors">
                  {incident.incident_key}
                </div>
                {!compact && incident.title && (
                  <div className="text-[11px] text-slate-400 truncate max-w-xs font-sans mt-0.5">
                    {incident.title}
                  </div>
                )}
              </td>
              <td className="py-3 px-4">
                <span className={`px-2 py-0.5 rounded border text-[11px] font-semibold ${getSeverityBadgeClass(incident.severity)}`}>
                  {incident.severity}
                </span>
              </td>
              <td className="py-3 px-4 text-slate-300">
                {incident.service || 'N/A'}
              </td>
              <td className="py-3 px-4 text-slate-400">
                {incident.environment || 'production'}
              </td>
              <td className="py-3 px-4 text-slate-400 whitespace-nowrap">
                {formatDateTime(incident.started_at)}
              </td>
              <td className="py-3 px-4 text-slate-300">
                {formatDuration(incident.started_at, incident.ended_at)}
              </td>
              <td className="py-3 px-4">
                <span className={`px-2 py-0.5 rounded border text-[11px] font-medium ${getStatusBadgeClass(incident.status)}`}>
                  {incident.status}
                </span>
              </td>
              <td className="py-3 px-4">
                <ConfidenceBar confidence={incident.confidence} showText />
              </td>
              <td className="py-3 px-3 text-right text-slate-500 group-hover:text-slate-200">
                <ChevronRight className="w-4 h-4 inline" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
