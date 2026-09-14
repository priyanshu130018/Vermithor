import React from 'react';
import { AlertCircle, Flame, ShieldAlert, Layers } from 'lucide-react';
import { Card } from '../common/Card';
import { Incident } from '../../types/incident';

interface IncidentStatsProps {
  incidents: Incident[];
}

export const IncidentStats: React.FC<IncidentStatsProps> = ({ incidents }) => {
  const activeIncidents = incidents.filter((i) => !['RESOLVED', 'CLOSED'].includes(i.status.toUpperCase()));
  const criticalIncidents = activeIncidents.filter((i) => i.severity.toUpperCase() === 'CRITICAL');
  const highIncidents = activeIncidents.filter((i) => i.severity.toUpperCase() === 'HIGH');
  
  const affectedServices = Array.from(
    new Set(activeIncidents.map((i) => i.service).filter(Boolean))
  );

  const stats = [
    {
      label: 'Active Incidents',
      value: activeIncidents.length,
      icon: AlertCircle,
      textColor: activeIncidents.length > 0 ? 'text-amber-400' : 'text-slate-200',
      borderColor: 'border-amber-500/20',
      bgGlow: 'bg-amber-500/5',
    },
    {
      label: 'Critical Outages',
      value: criticalIncidents.length,
      icon: Flame,
      textColor: criticalIncidents.length > 0 ? 'text-red-400' : 'text-slate-200',
      borderColor: 'border-red-500/20',
      bgGlow: 'bg-red-500/5',
    },
    {
      label: 'High Severity',
      value: highIncidents.length,
      icon: ShieldAlert,
      textColor: highIncidents.length > 0 ? 'text-orange-400' : 'text-slate-200',
      borderColor: 'border-orange-500/20',
      bgGlow: 'bg-orange-500/5',
    },
    {
      label: 'Affected Services',
      value: affectedServices.length,
      icon: Layers,
      textColor: 'text-sky-400',
      borderColor: 'border-sky-500/20',
      bgGlow: 'bg-sky-500/5',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {stats.map((stat) => {
        const Icon = stat.icon;
        return (
          <Card
            key={stat.label}
            className={`p-4 border ${stat.borderColor} ${stat.bgGlow} hover:border-border-focus transition-all`}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-mono uppercase tracking-wider text-slate-400">{stat.label}</p>
                <h3 className={`text-2xl font-bold font-mono mt-1 ${stat.textColor}`}>{stat.value}</h3>
              </div>
              <div className="p-3 bg-surface-elevated rounded-lg border border-border">
                <Icon className={`w-5 h-5 ${stat.textColor}`} />
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
};
