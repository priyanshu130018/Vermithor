import { IncidentSeverity, IncidentStatus } from '../types/incident';

export function formatDateTime(dateString?: string | null): string {
  if (!dateString) return 'N/A';
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return 'Invalid date';
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: 'UTC',
    }) + ' UTC';
  } catch {
    return dateString;
  }
}

export function formatDuration(startedAt?: string | null, endedAt?: string | null): string {
  if (!startedAt) return 'N/A';
  try {
    const start = new Date(startedAt).getTime();
    const end = endedAt ? new Date(endedAt).getTime() : Date.now();
    const diffSec = Math.max(0, Math.floor((end - start) / 1000));

    if (diffSec < 60) return `${diffSec}s`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m`;
    const diffHours = Math.floor(diffMin / 60);
    const remMin = diffMin % 60;
    return `${diffHours}h ${remMin}m`;
  } catch {
    return 'N/A';
  }
}

export function formatPercentage(value?: number | null): string {
  if (value === undefined || value === null || isNaN(value)) return '0%';
  const clamped = Math.max(0, Math.min(1, value));
  return `${Math.round(clamped * 100)}%`;
}

export function getSeverityBadgeClass(severity?: IncidentSeverity | string): string {
  switch (severity?.toUpperCase()) {
    case 'CRITICAL':
      return 'bg-red-950/80 text-red-400 border-red-800/80 shadow-[0_0_10px_rgba(239,68,68,0.2)]';
    case 'HIGH':
      return 'bg-orange-950/80 text-orange-400 border-orange-800/80';
    case 'MEDIUM':
      return 'bg-yellow-950/80 text-yellow-400 border-yellow-800/80';
    case 'LOW':
      return 'bg-blue-950/80 text-blue-400 border-blue-800/80';
    default:
      return 'bg-slate-800 text-slate-400 border-slate-700';
  }
}

export function getStatusBadgeClass(status?: IncidentStatus | string): string {
  switch (status?.toUpperCase()) {
    case 'OPEN':
      return 'bg-red-500/10 text-red-400 border-red-500/30';
    case 'INVESTIGATING':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/30 animate-pulse';
    case 'IDENTIFIED':
      return 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30';
    case 'MONITORING':
      return 'bg-sky-500/10 text-sky-400 border-sky-500/30';
    case 'RESOLVED':
    case 'CLOSED':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
    default:
      return 'bg-slate-800 text-slate-400 border-slate-700';
  }
}
