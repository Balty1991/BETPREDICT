import React from 'react';
import { ShieldCheck, TrendingUp, Target } from 'lucide-react';
import type { V7Edge } from '@/types/betpredict';

/**
 * EdgeBadge — banda de "edge real v7" afișată pe cardul meciului / analiză.
 * Probabilitate ancorată pe piață (onestă), edge + EV, grad și confirmare sharp.
 * Se afișează doar când există un verdict de valoare relevant.
 */
const gradeColor = (g: string): string =>
  g === 'A+' ? '#00e87a' : g === 'A' ? '#34d399' : g === 'B' ? '#a78bfa' : '#6b7a9e';

export const EdgeBadge: React.FC<{ edge?: V7Edge; compact?: boolean }> = ({ edge, compact }) => {
  if (!edge) return null;
  const isValue = edge.is_value;
  const accent = isValue ? '#00e87a' : '#6b7a9e';
  const gc = gradeColor(edge.grade);

  if (compact) {
    // varianta mică pentru header-ul cardului
    return (
      <span
        className="inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full"
        style={{ background: `${gc}22`, color: gc }}
        title={`Edge real v7: ${edge.pick} · prob onestă ${edge.honest_prob_pct}% · EV ${edge.ev_pct > 0 ? '+' : ''}${edge.ev_pct}%`}
      >
        <Target className="w-2.5 h-2.5" />
        {edge.grade}{edge.sharp_confirmed ? ' · ✓' : ''}
      </span>
    );
  }

  return (
    <div
      className="mx-3.5 mb-2.5 rounded-xl px-3 py-2 border"
      style={{ borderColor: `${accent}55`, background: `${accent}12` }}
    >
      <div className="flex items-center gap-1.5 mb-1.5">
        <TrendingUp className="w-3 h-3" style={{ color: accent }} />
        <span className="text-[9px] font-bold uppercase tracking-widest" style={{ color: accent }}>
          Edge Real v7
        </span>
        <span
          className="ml-1 text-[9px] font-black px-1.5 py-0.5 rounded-full"
          style={{ background: `${gradeColor(edge.grade)}22`, color: gradeColor(edge.grade) }}
        >
          {edge.grade}
        </span>
        {edge.sharp_confirmed && (
          <span className="ml-auto inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-[#00e87a22] text-[#00e87a]">
            <ShieldCheck className="w-2.5 h-2.5" /> CONFIRMAT SHARP
          </span>
        )}
      </div>

      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="text-[13px] font-bold text-[#e8eeff] block truncate">{edge.pick}</span>
          <span className="text-[9px] text-[#6b7a9e]">
            {isValue ? 'Valoare vs. piață' : 'Neutru vs. piață'}
            {edge.consensus_tier ? ` · consens ${edge.consensus_tier}` : ''}
          </span>
        </div>
        <div className="flex-shrink-0 text-right">
          <span className="text-base font-black block" style={{ color: '#e8eeff' }}>@{edge.odds.toFixed(2)}</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-1.5 mt-2">
        <MiniCell label="PROB. REALĂ" value={`${edge.honest_prob_pct.toFixed(0)}%`} />
        <MiniCell label="EDGE" value={`${edge.edge_pp > 0 ? '+' : ''}${edge.edge_pp.toFixed(1)}pp`} positive={edge.edge_pp > 0} />
        <MiniCell label="EV" value={`${edge.ev_pct > 0 ? '+' : ''}${edge.ev_pct.toFixed(1)}%`} positive={edge.ev_pct > 0} />
      </div>
    </div>
  );
};

const MiniCell: React.FC<{ label: string; value: string; positive?: boolean }> = ({ label, value, positive }) => (
  <div className="rounded-lg px-1.5 py-1 text-center" style={{ background: 'var(--bp-surface)' }}>
    <span className="text-[8px] font-bold uppercase tracking-wider text-[#6b7a9e] block">{label}</span>
    <span
      className="text-[12px] font-black block"
      style={{ color: positive === undefined ? '#e8eeff' : positive ? '#00e87a' : '#ff5c7a' }}
    >
      {value}
    </span>
  </div>
);
