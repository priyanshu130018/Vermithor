import React, { useState } from 'react';
import { PageHeader } from '../components/layout/PageHeader';
import { Card } from '../components/common/Card';
import { useRunbooks } from '../hooks/useRetrieval';
import { BookOpen, Plus, Search, Tag, Trash2, CheckCircle2 } from 'lucide-react';
import { LoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';

export const Runbooks: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRunbook, setSelectedRunbook] = useState<any | null>(null);
  const { data, isLoading, isError, refetch } = useRunbooks();

  const fallbackRunbooks = [
    {
      id: '1',
      runbook_key: 'RB-000001',
      title: 'PostgreSQL Connection Saturation SOP',
      description: 'Standard operational procedure for resolving database connection exhaustion.',
      content: `## Symptoms
- Elevated latency on checkout and booking endpoints
- Logs showing: "FATAL: remaining connection slots are reserved"

## Diagnostic Steps
1. Connect via psql: \`SELECT count(*) FROM pg_stat_activity WHERE state != 'idle';\`
2. Check PgBouncer connection pooler metrics.

## Mitigation Steps
1. Scale up max_connections on DB proxy.
2. Restart hung background worker processes.
3. Verify connection pool releases after request completion.`,
      service: 'postgres-db',
      category: 'DATABASE',
      tags: ['database', 'postgres', 'connection-pool', 'latency'],
    },
    {
      id: '2',
      runbook_key: 'RB-000002',
      title: 'High CPU Utilization Incident SOP',
      description: 'Runbook for diagnosing and isolating runaway CPU spikes in containerized services.',
      content: `## Symptoms
- Pod CPU throttling alarms triggering in Kubernetes
- Increased response p99 across microservices

## Steps
1. Inspect top consumers with \`kubectl top pods -n prod\`
2. Capture flamegraph/pprof CPU profile.
3. Roll back any canary deployments within the last 30 minutes.`,
      service: 'booking-api',
      category: 'INFRASTRUCTURE',
      tags: ['cpu', 'kubernetes', 'scaling', 'performance'],
    },
  ];

  const runbooks = data?.items?.length ? data.items : fallbackRunbooks;
  const filtered = runbooks.filter((rb) =>
    rb.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    rb.service?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    rb.category?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div>
      <PageHeader
        title="Runbook Knowledge Base"
        description="Standard Operating Procedures (SOPs) and remediation guides for rapid incident resolution."
      />

      {/* Search Bar */}
      <Card className="mb-6 p-3">
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search runbooks by title, service, or category..."
              className="w-full bg-background border border-border rounded pl-9 pr-4 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
            />
          </div>
        </div>
      </Card>

      {/* Grid Layout: List on Left, Viewer on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Runbook List */}
        <div className="lg:col-span-1 space-y-3">
          {isLoading ? (
            <LoadingState message="Loading runbooks..." />
          ) : isError ? (
            <ErrorState title="Error Loading Runbooks" onRetry={() => refetch()} />
          ) : (
            filtered.map((rb) => (
              <div
                key={rb.runbook_key}
                onClick={() => setSelectedRunbook(rb)}
                className={`p-3 rounded-lg border transition-all cursor-pointer ${
                  selectedRunbook?.runbook_key === rb.runbook_key
                    ? 'bg-sky-950/30 border-sky-500/60 shadow-[0_0_8px_rgba(56,189,248,0.15)]'
                    : 'bg-surface border-border hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs font-bold text-sky-400">{rb.runbook_key}</span>
                  <span className="font-mono text-[10px] text-slate-400 bg-surface-elevated px-1.5 py-0.5 rounded border border-border">
                    {rb.category || 'GENERAL'}
                  </span>
                </div>
                <h4 className="text-xs font-semibold text-slate-200 line-clamp-1">{rb.title}</h4>
                <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">{rb.description}</p>
                {rb.service && (
                  <div className="mt-2 text-[10px] font-mono text-slate-500">
                    Service: <strong className="text-slate-400">{rb.service}</strong>
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Selected Runbook Content View */}
        <div className="lg:col-span-2">
          <Card
            title={
              <div className="flex items-center gap-2 text-slate-200 font-mono text-xs font-semibold">
                <BookOpen className="w-4 h-4 text-sky-400" />
                <span>
                  {selectedRunbook ? selectedRunbook.title : 'RUNBOOK VIEWER'}
                </span>
              </div>
            }
          >
            {selectedRunbook || filtered[0] ? (
              (() => {
                const active = selectedRunbook || filtered[0];
                return (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-2 pb-3 border-b border-border font-mono text-xs text-slate-400">
                      <span>Key: <strong className="text-sky-400">{active.runbook_key}</strong></span>
                      <span>•</span>
                      <span>Service: <strong className="text-slate-200">{active.service || 'N/A'}</strong></span>
                      <span>•</span>
                      <span>Category: <strong className="text-slate-200">{active.category || 'N/A'}</strong></span>
                    </div>

                    <div className="bg-background/60 p-4 rounded-lg border border-border font-mono text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">
                      {active.content}
                    </div>

                    {active.tags && (
                      <div className="flex flex-wrap items-center gap-1.5 pt-2">
                        <Tag className="w-3.5 h-3.5 text-slate-500" />
                        {active.tags.map((tag: string) => (
                          <span
                            key={tag}
                            className="font-mono text-[10px] text-slate-400 bg-surface-elevated px-2 py-0.5 rounded border border-border"
                          >
                            #{tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()
            ) : (
              <div className="py-12 text-center text-xs font-mono text-slate-500">
                Select a runbook from the left to view instructions.
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};
