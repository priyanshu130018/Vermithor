import React, { useState } from 'react';
import { PageHeader } from '../components/layout/PageHeader';
import { IncidentTable } from '../components/dashboard/IncidentTable';
import { Card } from '../components/common/Card';
import { useIncidents } from '../hooks/useIncidents';
import { IncidentSeverity, IncidentStatus } from '../types/incident';
import { LoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';
import { Filter, Search } from 'lucide-react';

export const Incidents: React.FC = () => {
  const [service, setService] = useState('');
  const [severity, setSeverity] = useState<IncidentSeverity | ''>('');
  const [status, setStatus] = useState<IncidentStatus | ''>('');
  const [page, setPage] = useState(1);

  const { data, isLoading, isError, refetch } = useIncidents({
    page,
    page_size: 20,
    service: service || undefined,
    severity: severity || undefined,
    status: status || undefined,
  });

  return (
    <div>
      <PageHeader
        title="Production Incident Directory"
        description="Comprehensive index of detected and correlated operational incidents."
      />

      {/* Filter Bar */}
      <Card className="mb-6 p-3">
        <div className="flex flex-wrap items-center gap-3 font-mono text-xs">
          <div className="flex items-center gap-2 flex-1 min-w-[200px]">
            <Search className="w-4 h-4 text-slate-500" />
            <input
              type="text"
              value={service}
              onChange={(e) => setService(e.target.value)}
              placeholder="Filter by service name..."
              className="w-full bg-background border border-border rounded px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-slate-500" />
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value as IncidentSeverity | '')}
              className="bg-background border border-border rounded px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
            >
              <option value="">All Severities</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
            </select>
          </div>

          <div>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as IncidentStatus | '')}
              className="bg-background border border-border rounded px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
            >
              <option value="">All Statuses</option>
              <option value="OPEN">OPEN</option>
              <option value="INVESTIGATING">INVESTIGATING</option>
              <option value="IDENTIFIED">IDENTIFIED</option>
              <option value="MONITORING">MONITORING</option>
              <option value="RESOLVED">RESOLVED</option>
              <option value="CLOSED">CLOSED</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Incidents Table */}
      {isLoading ? (
        <LoadingState message="Loading incidents..." />
      ) : isError ? (
        <ErrorState
          title="Incident Service Error"
          message="Failed to retrieve incidents from Incident Service."
          onRetry={() => refetch()}
        />
      ) : (
        <Card
          title={
            <div className="flex items-center justify-between w-full font-mono text-xs">
              <span>ALL INCIDENTS ({data?.total || 0} TOTAL)</span>
              <span>Page {page} of {data?.total_pages || 1}</span>
            </div>
          }
        >
          <IncidentTable incidents={data?.items || []} />
        </Card>
      )}
    </div>
  );
};
