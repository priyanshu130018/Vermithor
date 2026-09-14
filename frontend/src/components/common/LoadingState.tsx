import React from 'react';
import { Loader2 } from 'lucide-react';

interface LoadingStateProps {
  message?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = 'Loading telemetry...',
  size = 'md',
}) => {
  const iconSizes = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8',
  };

  return (
    <div className="flex flex-col items-center justify-center p-8 text-slate-400 space-y-3">
      <Loader2 className={`${iconSizes[size]} animate-spin text-sky-400`} />
      {message && <p className="text-xs font-mono tracking-wide">{message}</p>}
    </div>
  );
};
