import React from 'react';
import { PageHeader } from '../components/layout/PageHeader';
import { IncidentStats } from '../components/dashboard/IncidentStats';
import { IncidentTable } from '../components/dashboard/IncidentTable';
import { ServiceHealth } from '../components/dashboard/ServiceHealth';
import { SeverityChart } from '../components/dashboard/SeverityChart';
import { Card } from '../components/common/Card';
import { useIncidents } from '../hooks/useIncidents';
import { LoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';

export const Dashboard: React.FC = () => {
  const { data, isLoading, isError, refetch } = useIncidents({ page_size: 10 });
  const incidents = data?.items || [];

  return (
    <div>
      <PageHeader
        title="Incident Intelligence Command Center"
        description="Live operational telemetry, multi-signal incident correlation, and RCA status."
      />

      {isLoading ? (
        <LoadingState message="Loading platform incident telemetry..." />
      ) : isError ? (
        <ErrorState
          title="Incident Service Unavailable"
          message="Could not connect to the Incident Service on port 8002. Please ensure the backend is running."
          onRetry={() => refetch()}
        />
      ) : (
        <>
          {/* Top Metric Cards */}
          <IncidentStats incidents={incidents} />

          {/* Service Matrix & Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
            <div className="lg:col-span-2">
              <ServiceHealth />
            </div>
            <div>
              <SeverityChart incidents={incidents} />
            </div>
          </div>

          {/* Active / Recent Incidents Table */}
          <Card
            title={
              <div className="flex items-center justify-between w-full">
                <span className="font-mono text-xs font-semibold text-slate-200">
                  ACTIVE & RECENT INCIDENTS
                </span>
                <span className="font-mono text-xs text-slate-400">
                  Total: <strong className="text-slate-200">{data?.total || 0}</strong>
                </span>
              </div>
            }
          >
            <IncidentTable incidents={incidents} />
          </Card>
        </>
      )}
    </div>
  );
};
