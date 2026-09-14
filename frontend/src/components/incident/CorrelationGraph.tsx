import React from 'react';
import { Network, Server, ArrowRight, AlertTriangle } from 'lucide-react';
import { Card } from '../common/Card';

export const CorrelationGraph: React.FC = () => {
  const nodes = [
    { id: 1, label: 'Deployment v2.1.0', type: 'DEPLOYMENT', color: 'border-purple-500 bg-purple-950/40 text-purple-300' },
    { id: 2, label: 'DB Query Latency Anomaly', type: 'METRIC', color: 'border-red-500 bg-red-950/40 text-red-300' },
    { id: 3, label: 'Connection Pool Saturation', type: 'LOG', color: 'border-amber-500 bg-amber-950/40 text-amber-300' },
    { id: 4, label: 'Booking API p99 Spike', type: 'METRIC', color: 'border-sky-500 bg-sky-950/40 text-sky-300' },
    { id: 5, label: 'HTTP 500 Error Cascade', type: 'ALERT', color: 'border-red-500 bg-red-950/40 text-red-300' },
  ];

  return (
    <Card
      className="mb-6"
      title={
        <div className="flex items-center gap-2 text-slate-200 font-mono text-xs font-semibold">
          <Network className="w-4 h-4 text-sky-400" />
          <span>MULTI-SIGNAL CORRELATION GRAPH</span>
        </div>
      }
    >
      <div className="flex flex-col md:flex-row items-center justify-between gap-3 p-4 bg-background/60 rounded-lg border border-border overflow-x-auto">
        {nodes.map((node, index) => (
          <React.Fragment key={node.id}>
            <div className={`p-3 rounded-lg border flex flex-col items-center justify-center text-center min-w-[140px] ${node.color} shadow-sm`}>
              <span className="text-[10px] font-mono uppercase tracking-widest opacity-70 mb-1">
                {node.type}
              </span>
              <span className="text-xs font-semibold font-mono">
                {node.label}
              </span>
            </div>
            {index < nodes.length - 1 && (
              <div className="flex items-center justify-center py-2 md:py-0 text-slate-500">
                <ArrowRight className="w-5 h-5 hidden md:block" />
                <span className="text-xs font-mono md:hidden">↓</span>
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
      <div className="flex items-center justify-between mt-3 text-[11px] font-mono text-slate-500">
        <span>Correlation Confidence: <strong className="text-emerald-400">92%</strong></span>
        <span>Window: <strong>15 minutes</strong></span>
      </div>
    </Card>
  );
};
