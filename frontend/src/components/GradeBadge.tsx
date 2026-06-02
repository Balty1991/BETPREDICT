import React from 'react';
import { gradeColor } from '@/utils/filters';

export const GradeBadge: React.FC<{ grade: string; small?: boolean }> = ({ grade, small }) => {
  const color = gradeColor(grade);
  const size = small ? 'text-[9px] px-1.5 py-0.5' : 'text-[10px] px-2 py-0.5';
  return (
    <span
      className={`inline-flex items-center font-bold rounded-full ${size}`}
      style={{ color, background: `${color}22`, border: `1px solid ${color}44` }}
    >
      {grade}
    </span>
  );
};
