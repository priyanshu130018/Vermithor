import React from 'react';
import { ShieldCheck, ShieldAlert, Activity } from 'lucide-react';
import { Card } from '../common/Card';
import { useServiceHealth } from '../../hooks/useHealth';

export const ServiceHealth: React.FC = () => {
  const { data: services, isLoading } = useServiceHealth();

  return (
    <Card
      title={
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-sky-400" />
          <span>Microservices Health Matrix</span>
        </div>
      }
    >
      {isLoading ? (
        <div className="py-4 text-center text-xs font-mono text-slate-500">Checking microservices...</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {services?.map((svc) => {
            const isHealthy = svc.status === 'healthy';
            return (
              <div
                key={svc.name}
                className="p-3 bg-surface-elevated/40 border border-border rounded-md flex flex-col justify-between"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono text-slate-400">:{svc.port}</span>
                  {isHealthy ? (
                    <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.8)]" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.8)] animate-pulse" />
                  )}
                </div>
                <div className="mt-2">
                  <div className="text-xs font-medium text-slate-200 truncate">{svc.name}</div>
                  <div className="text-[10px] font-mono text-slate-500 mt-0.5">
                    {svc.latencyMs ? `${svc.latencyMs}ms` : svc.status}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
};
