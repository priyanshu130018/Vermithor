import React from 'react';
import { BookOpen, ExternalLink, CheckCircle2 } from 'lucide-react';
import { Card } from '../common/Card';
import { useNavigate } from 'react-router-dom';

export const RunbookPanel: React.FC = () => {
  const navigate = useNavigate();

  const runbooks = [
    {
      key: 'RB-000001',
      title: 'Database Connection Pool Exhaustion Troubleshooting SOP',
      service: 'postgres-db',
      category: 'DATABASE',
      steps: [
        'Run `SELECT count(*) FROM pg_stat_activity WHERE state != \'idle\';`',
        'Verify PgBouncer `max_client_conn` and pool saturation metrics.',
        'Scale worker replicas or restart idle connections via DB pooler.',
      ],
    },
  ];

  return (
    <Card
      title={
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2 text-slate-200 font-mono text-xs font-semibold">
            <BookOpen className="w-4 h-4 text-sky-400" />
            <span>RECOMMENDED OPERATIONAL RUNBOOKS</span>
          </div>
          <button
            onClick={() => navigate('/runbooks')}
            className="text-[11px] font-mono text-sky-400 hover:text-sky-300 transition-colors flex items-center gap-1"
          >
            All Runbooks <ExternalLink className="w-3 h-3" />
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        {runbooks.map((rb) => (
          <div key={rb.key} className="p-3 bg-surface-elevated/40 border border-border rounded-md">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="font-mono text-xs font-bold text-sky-400">{rb.key}</span>
              <span className="font-mono text-xs font-semibold text-slate-200">{rb.title}</span>
            </div>
            <div className="text-[11px] font-mono text-slate-400 mb-2.5">
              Service: <strong className="text-slate-300">{rb.service}</strong> | Category: {rb.category}
            </div>

            <div className="space-y-1.5 bg-background/50 p-2.5 rounded border border-border/60">
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold mb-1">
                Standard Remediation Steps (SOP):
              </div>
              {rb.steps.map((step, idx) => (
                <div key={idx} className="flex items-start gap-2 text-xs text-slate-300 font-mono">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <span>{step}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
