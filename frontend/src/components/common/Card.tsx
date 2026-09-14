import React from 'react';
import { cn } from '../../lib/utils';

interface CardProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: React.ReactNode;
  action?: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({
  children,
  className,
  title,
  action,
  ...props
}) => {
  return (
    <div
      className={cn(
        'bg-surface border border-border rounded-lg shadow-sm overflow-hidden flex flex-col',
        className
      )}
      {...props}
    >
      {(title || action) && (
        <div className="px-4 py-3 border-b border-border flex items-center justify-between bg-surface-elevated/40">
          {typeof title === 'string' ? (
            <h3 className="text-sm font-semibold text-slate-200 tracking-wide">{title}</h3>
          ) : (
            title
          )}
          {action && <div>{action}</div>}
        </div>
      )}
      <div className="p-4 flex-1">{children}</div>
    </div>
  );
};
