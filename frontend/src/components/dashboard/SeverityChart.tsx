import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { Card } from '../common/Card';
import { Incident } from '../../types/incident';

interface SeverityChartProps {
  incidents: Incident[];
}

export const SeverityChart: React.FC<SeverityChartProps> = ({ incidents }) => {
  const counts = {
    CRITICAL: 0,
    HIGH: 0,
    MEDIUM: 0,
    LOW: 0,
  };

  incidents.forEach((inc) => {
    const sev = inc.severity.toUpperCase();
    if (sev in counts) {
      counts[sev as keyof typeof counts]++;
    }
  });

  const data = [
    { name: 'Critical', value: counts.CRITICAL, color: '#ef4444' },
    { name: 'High', value: counts.HIGH, color: '#f97316' },
    { name: 'Medium', value: counts.MEDIUM, color: '#eab308' },
    { name: 'Low', value: counts.LOW, color: '#3b82f6' },
  ].filter((d) => d.value > 0);

  return (
    <Card title="Severity Distribution">
      {data.length === 0 ? (
        <div className="py-8 text-center text-xs font-mono text-slate-500">No active telemetry</div>
      ) : (
        <div className="h-44 flex items-center justify-center">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                innerRadius={36}
                outerRadius={60}
                paddingAngle={4}
                dataKey="value"
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} stroke="#0f172a" />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  borderColor: '#334155',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontFamily: 'monospace',
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="grid grid-cols-2 gap-2 mt-2 pt-2 border-t border-border">
        {data.map((d) => (
          <div key={d.name} className="flex items-center justify-between text-xs font-mono">
            <span className="flex items-center gap-1.5 text-slate-400">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: d.color }} />
              {d.name}
            </span>
            <span className="font-semibold text-slate-200">{d.value}</span>
          </div>
        ))}
      </div>
    </Card>
  );
};
