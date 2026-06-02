import React from 'react';

interface ConfidenceBarProps {
  value: number; // 0-100
  label?: string;
  size?: 'sm' | 'md';
  showValue?: boolean;
}

export const ConfidenceBar: React.FC<ConfidenceBarProps> = ({
  value,
  label,
  size = 'md',
  showValue = true,
}) => {
  const clamped = Math.max(0, Math.min(100, value));
  const height = size === 'sm' ? 'h-1.5' : 'h-2';

  const getColor = (v: number) => {
    if (v >= 80) return 'bg-emerald-500';
    if (v >= 60) return 'bg-cyan-500';
    if (v >= 40) return 'bg-amber-500';
    return 'bg-red-500';
  };

  return (
    <div className="flex items-center gap-2 w-full">
      {label && (
        <span className="text-[9px] uppercase tracking-wider text-slate-500 font-semibold min-w-[52px]">
          {label}
        </span>
      )}
      <div className={`flex-1 ${height} bg-slate-800 rounded-full overflow-hidden`}>
        <div
          className={`${height} ${getColor(clamped)} rounded-full transition-all duration-700 ease-out`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showValue && (
        <span className="text-[10px] font-mono font-bold text-slate-400 min-w-[24px] text-right">
          {Math.round(clamped)}
        </span>
      )}
    </div>
  );
};
