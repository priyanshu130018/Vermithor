import React from 'react';
import { Database } from 'lucide-react';

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No records found',
  description = 'No telemetry data matches the current criteria.',
  icon,
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center text-slate-400 space-y-3">
      <div className="p-3 bg-surface-elevated rounded-full text-slate-500 border border-border">
        {icon || <Database className="w-6 h-6" />}
      </div>
      <div>
        <h4 className="text-sm font-medium text-slate-300">{title}</h4>
        {description && <p className="text-xs text-slate-500 mt-1 max-w-sm">{description}</p>}
      </div>
    </div>
  );
};
