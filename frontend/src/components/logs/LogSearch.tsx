import React, { useState } from 'react';
import { Search, Terminal, Filter } from 'lucide-react';
import { Card } from '../common/Card';
import { useSearchLogs } from '../../hooks/useLogs';
import { formatDateTime, formatPercentage } from '../../lib/formatters';
import { LoadingState } from '../common/LoadingState';

export const LogSearch: React.FC = () => {
  const [query, setQuery] = useState('database connection pool timeout');
  const [service, setService] = useState('');
  const [severity, setSeverity] = useState('');
  const searchMutation = useSearchLogs();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    searchMutation.mutate({
      query,
      top_k: 10,
      service: service || undefined,
      severity: severity || undefined,
    });
  };

  return (
    <div className="space-y-6">
      {/* Search Input Card */}
      <Card
        title={
          <div className="flex items-center gap-2 text-slate-200 font-mono text-xs font-semibold">
            <Search className="w-4 h-4 text-sky-400" />
            <span>SEMANTIC LOG INTELLIGENCE SEARCH</span>
          </div>
        }
      >
        <form onSubmit={handleSearch} className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Terminal className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search logs with natural language or semantic query..."
                className="w-full bg-background border border-border rounded-md pl-9 pr-4 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500 transition-colors"
              />
            </div>
            <button
              type="submit"
              disabled={searchMutation.isPending}
              className="px-5 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-md text-xs font-mono font-medium transition-colors cursor-pointer"
            >
              {searchMutation.isPending ? 'Searching...' : 'Vector Search'}
            </button>
          </div>

          {/* Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-border font-mono text-xs">
            <div className="flex items-center gap-2">
              <span className="text-slate-400">Service:</span>
              <input
                type="text"
                value={service}
                onChange={(e) => setService(e.target.value)}
                placeholder="e.g. booking-api"
                className="flex-1 bg-background border border-border rounded px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-slate-400">Severity:</span>
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
                className="flex-1 bg-background border border-border rounded px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
              >
                <option value="">All Severities</option>
                <option value="CRITICAL">CRITICAL</option>
                <option value="ERROR">ERROR</option>
                <option value="WARNING">WARNING</option>
                <option value="INFO">INFO</option>
              </select>
            </div>
          </div>
        </form>
      </Card>

      {/* Search Results */}
      {searchMutation.isPending && (
        <LoadingState message="Executing 384-dimensional dense cosine similarity search..." />
      )}

      {searchMutation.data && (
        <Card
          title={
            <div className="flex items-center justify-between w-full font-mono text-xs">
              <span className="text-slate-200 font-semibold">
                SEARCH RESULTS ({searchMutation.data.total_matches} MATCHES)
              </span>
              <span className="text-slate-400">
                Model: <strong>sentence-transformers/all-MiniLM-L6-v2</strong>
              </span>
            </div>
          }
        >
          {searchMutation.data.matches.length === 0 ? (
            <div className="py-8 text-center text-xs font-mono text-slate-500">
              No matching semantic logs found for query "{query}".
            </div>
          ) : (
            <div className="space-y-3">
              {searchMutation.data.matches.map((match) => (
                <div
                  key={match.id}
                  className="p-3 bg-surface-elevated/40 border border-border rounded-md hover:border-sky-500/40 transition-colors"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5 font-mono text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-red-400 font-bold bg-red-950/60 px-1.5 py-0.5 rounded border border-red-900 text-[10px]">
                        {match.severity}
                      </span>
                      <strong className="text-slate-200">{match.service}</strong>
                      <span className="text-slate-500 text-[11px]">{match.domain_category}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-emerald-400 font-bold">
                        Cosine Sim: {formatPercentage(match.similarity_score)}
                      </span>
                      <span className="text-slate-500 text-[11px]">
                        {formatDateTime(match.timestamp)}
                      </span>
                    </div>
                  </div>
                  <p className="font-mono text-xs text-slate-300 bg-background/60 p-2.5 rounded border border-border/60 whitespace-pre-wrap">
                    {match.normalized_message}
                  </p>
                  {match.template && (
                    <div className="mt-2 text-[10px] font-mono text-slate-500 truncate">
                      Template: {match.template}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
};
