import React from 'react';
import { Clock, Tag } from 'lucide-react';
import { Card } from '../common/Card';
import { SummaryTimelineItem } from '../../types/summary';
import { formatDateTime } from '../../lib/formatters';

interface IncidentTimelineProps {
  timeline?: SummaryTimelineItem[];
}

export const IncidentTimeline: React.FC<IncidentTimelineProps> = ({ timeline = [] }) => {
  const sampleTimeline: SummaryTimelineItem[] = [
    { timestamp: '2026-08-29T12:00:00Z', event: 'Deployment v2.1.0 rolled out to production', source: '[DEPLOYMENT:dep-001]' },
    { timestamp: '2026-08-29T12:02:00Z', event: 'Database connection latency anomaly detected (z=4.2)', source: '[ANOMALY:anom-101]' },
    { timestamp: '2026-08-29T12:02:30Z', event: 'PostgreSQL connection pool exhausted (100% active)', source: '[LOG:evt-db-01]' },
    { timestamp: '2026-08-29T12:03:00Z', event: 'Booking API p99 latency spiked past 4500ms', source: '[ANOMALY:anom-102]' },
    { timestamp: '2026-08-29T12:04:00Z', event: 'HTTP 500 error rate exceeded 15% threshold', source: '[ALERT:alt-500]' },
  ];

  const items = timeline.length > 0 ? timeline : sampleTimeline;

  return (
    <Card
      className="mb-6"
      title={
        <div className="flex items-center gap-2 text-slate-200 font-mono text-xs font-semibold">
          <Clock className="w-4 h-4 text-sky-400" />
          <span>INCIDENT CHRONOLOGICAL TIMELINE</span>
        </div>
      }
    >
      <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
        {items.map((item, idx) => (
          <div key={idx} className="relative group">
            {/* Timeline Dot */}
            <div className="absolute -left-6 top-1.5 w-2.5 h-2.5 rounded-full bg-sky-500 border-2 border-background group-hover:scale-125 transition-transform" />

            <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
              <span className="font-mono text-xs font-semibold text-slate-200">
                {item.event}
              </span>
              <span className="font-mono text-[11px] text-slate-500 shrink-0">
                {formatDateTime(item.timestamp)}
              </span>
            </div>

            {item.source && (
              <div className="mt-1 flex items-center gap-1.5">
                <Tag className="w-3 h-3 text-slate-500" />
                <span className="font-mono text-[10px] text-sky-400 bg-sky-950/60 px-1.5 py-0.5 rounded border border-sky-900">
                  {item.source}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
};
