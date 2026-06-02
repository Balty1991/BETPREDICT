import React from 'react';
import { scoreColor } from '@/utils/filters';

export const ScoreBar: React.FC<{ score: number }> = ({ score }) => {
  const color = scoreColor(score);
  const pct = Math.min(100, Math.max(0, score));
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bp-surface2)' }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-xs font-bold font-mono tabular-nums" style={{ color, minWidth: 28, textAlign: 'right' }}>
        {Math.round(score)}
      </span>
    </div>
  );
};
