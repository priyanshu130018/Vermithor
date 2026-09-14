import React from 'react';
import { cn } from '../../lib/utils';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'outline' | 'critical' | 'high' | 'medium' | 'low' | 'healthy';
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  className,
  variant = 'default',
  ...props
}) => {
  const variantStyles = {
    default: 'bg-slate-800 text-slate-300 border-slate-700',
    outline: 'bg-transparent text-slate-400 border-slate-700',
    critical: 'bg-red-950/70 text-red-400 border-red-800/80',
    high: 'bg-orange-950/70 text-orange-400 border-orange-800/80',
    medium: 'bg-yellow-950/70 text-yellow-400 border-yellow-800/80',
    low: 'bg-blue-950/70 text-blue-400 border-blue-800/80',
    healthy: 'bg-emerald-950/70 text-emerald-400 border-emerald-800/80',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium border transition-colors',
        variantStyles[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};
