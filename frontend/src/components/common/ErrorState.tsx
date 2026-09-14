import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Service Unavailable',
  message = 'Failed to load telemetry from upstream service.',
  onRetry,
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-6 bg-red-950/20 border border-red-900/40 rounded-lg text-center space-y-3">
      <AlertTriangle className="w-6 h-6 text-red-400" />
      <div>
        <h4 className="text-sm font-semibold text-red-300">{title}</h4>
        <p className="text-xs text-slate-400 mt-1 max-w-md">{message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 px-3 py-1 bg-surface-elevated hover:bg-surface-hover border border-border rounded text-xs font-mono text-slate-300 transition-colors"
        >
          <RefreshCw className="w-3 h-3" /> Retry
        </button>
      )}
    </div>
  );
};
