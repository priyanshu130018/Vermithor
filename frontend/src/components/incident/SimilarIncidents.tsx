import React from 'react';
import { useNavigate } from 'react-router-dom';
import { History, ArrowUpRight } from 'lucide-react';
import { Card } from '../common/Card';
import { formatPercentage } from '../../lib/formatters';

export const SimilarIncidents: React.FC = () => {
  const navigate = useNavigate();

  const similar = [
    {
      key: 'INC-000017',
      title: 'PostgreSQL DB Connection Saturation on Booking API',
      similarity: 0.93,
      status: 'RESOLVED',
      date: 'Aug 14, 2026',
    },
    {
      key: 'INC-000012',
      title: 'PgBouncer Max Client Pool Exhaustion',
      similarity: 0.86,
      status: 'RESOLVED',
      date: 'Jul 22, 2026',
    },
  ];

  return (
    <Card
      title={
        <div className="flex items-center gap-2 text-slate-200 font-mono text-xs font-semibold">
          <History className="w-4 h-4 text-sky-400" />
          <span>SIMILAR HISTORICAL INCIDENTS</span>
        </div>
      }
    >
      <div className="space-y-2.5">
        {similar.map((inc) => (
          <div
            key={inc.key}
            onClick={() => navigate(`/incidents/${inc.key}`)}
            className="p-3 bg-surface-elevated/40 border border-border rounded-md hover:border-sky-500/40 transition-colors cursor-pointer group flex items-start justify-between gap-3"
          >
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs font-bold text-sky-400 group-hover:underline">
                  {inc.key}
                </span>
                <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-900">
                  {inc.status}
                </span>
              </div>
              <p className="text-xs text-slate-300 font-medium line-clamp-1">{inc.title}</p>
              <p className="text-[10px] text-slate-500 font-mono mt-1">{inc.date}</p>
            </div>
            <div className="text-right shrink-0">
              <span className="font-mono text-xs font-bold text-emerald-400 block">
                {formatPercentage(inc.similarity)}
              </span>
              <span className="text-[10px] text-slate-500 font-mono">Similarity</span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
