import React from 'react';
import { formatPercentage } from '../../lib/formatters';

interface ConfidenceBarProps {
  confidence: number;
  label?: string;
  showText?: boolean;
}

export const ConfidenceBar: React.FC<ConfidenceBarProps> = ({
  confidence,
  label,
  showText = true,
}) => {
  const percentage = Math.round(Math.max(0, Math.min(1, confidence)) * 100);

  const getColor = (val: number) => {
    if (val >= 80) return 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]';
    if (val >= 60) return 'bg-sky-500';
    if (val >= 40) return 'bg-yellow-500';
    return 'bg-slate-500';
  };

  return (
    <div className="w-full">
      {(label || showText) && (
        <div className="flex justify-between items-center mb-1 text-xs">
          {label && <span className="text-slate-400 font-medium">{label}</span>}
          {showText && <span className="font-mono text-slate-200 font-semibold">{formatPercentage(confidence)}</span>}
        </div>
      )}
      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${getColor(percentage)}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};
