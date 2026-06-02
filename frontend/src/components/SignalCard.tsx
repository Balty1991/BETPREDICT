import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { TeamLogo } from './TeamLogo';
import { GradeBadge } from './GradeBadge';
import { ScoreBar } from './ScoreBar';
import type { Signal } from '@/types/betpredict';
import {
  effectiveScore, effectiveGrade, effectiveEV, effectiveProb,
  isVeyra, marketLabel, formatDate,
} from '@/utils/filters';

interface SignalCardProps {
  signal: Signal;
  isValue?: boolean;
}

export const SignalCard: React.FC<SignalCardProps> = ({ signal: s, isValue }) => {
  const [expanded, setExpanded] = useState(false);
  const grade = effectiveGrade(s);
  const sc = effectiveScore(s);
  const ev = effectiveEV(s);
  const prob = effectiveProb(s);
  const veyra = isVeyra(s);
  const mktLabel = s.market_label ?? marketLabel(s.market);

  const evPct = (ev * 100).toFixed(1);
  const evPos = ev > 0;
  const probPct = prob.toFixed(0);
  const metric4 = veyra && s.agreement != null
    ? `${Math.round(s.agreement * 100)}%`
    : null;

  const riskTier = s.risk_tier?.toLowerCase() ?? '';
  const gapPp = s.model_vs_market_gap_pp;

  return (
    <div
      className="rounded-2xl border overflow-hidden"
      style={{ background: '#0d1322', borderColor: `${gradeAccent(grade)}22` }}
    >
      {/* Top row: league + date + grade */}
      <div className="flex items-center justify-between px-3.5 pt-3 pb-1">
        <span className="text-[10px] text-[#6b7a9e] font-medium tracking-wide truncate max-w-[70%]">
          {s.league ?? 'Liga necunoscută'} · {formatDate(s.event_date)}
        </span>
        <GradeBadge grade={grade} />
      </div>

      {/* Teams */}
      <div className="flex items-center justify-between px-3.5 py-2.5">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <TeamLogo id={s.home_team_id} size={30} />
          <span className="text-sm font-bold text-[#e8eeff] truncate">{s.home_team}</span>
        </div>
        <span className="text-[10px] font-bold text-[#303d57] mx-2 flex-shrink-0">VS</span>
        <div className="flex items-center gap-2 flex-1 min-w-0 justify-end">
          <span className="text-sm font-bold text-[#e8eeff] truncate text-right">{s.away_team}</span>
          <TeamLogo id={s.away_team_id} size={30} />
        </div>
      </div>

      {/* Bet info */}
      <div className="mx-3.5 mb-2.5 rounded-xl p-3" style={{ background: '#131c2e' }}>
        {/* Market + engine tag */}
        <div className="flex items-center justify-between mb-2.5">
          <span className="text-sm font-semibold text-[#e8eeff]">
            ⚡ {mktLabel}
          </span>
          <span
            className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
            style={{ background: veyra ? '#2BE5C522' : '#4a9eff22', color: veyra ? '#2BE5C5' : '#4a9eff' }}
          >
            {veyra ? 'VEYRA v5' : 'ENGINE v6'}
          </span>
        </div>

        {/* Metrics row */}
        <div className="flex items-center gap-0 divide-x divide-white/10">
          <MetricCol label="COTĂ" value={s.odds?.toFixed(2) ?? '—'} />
          <MetricCol label="PROB" value={`${probPct}%`} color="#00e87a" />
          <MetricCol label="EV" value={`${evPos ? '+' : ''}${evPct}%`} color={evPos ? '#00e87a' : '#ff3d5a'} />
          {metric4 && <MetricCol label="ACORD" value={metric4} color="#22d3ee" />}
        </div>
      </div>

      {/* SmartBet score */}
      <div className="px-3.5 pb-2.5">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[9px] font-bold uppercase tracking-widest text-[#6b7a9e]">SmartBet</span>
          <div className="flex gap-1 ml-auto">
            {riskTier === 'low' && <Tag color="#00e87a">✓ risc scăzut</Tag>}
            {riskTier === 'medium' && <Tag color="#ffb830">~ risc mediu</Tag>}
            {(riskTier === 'high' || riskTier === 'very_high') && <Tag color="#ff3d5a">⚠ risc înalt</Tag>}
            {(isValue || evPos) && <Tag color="#00e87a">{isValue ? '★ VALUE' : 'EV+'}</Tag>}
            {gapPp != null && gapPp > 20 && <Tag color="#ffb830">+{Math.round(gapPp)}pp gap</Tag>}
          </div>
        </div>
        <ScoreBar score={sc} />
      </div>

      {/* AI Rationale (VEYRA only) */}
      {veyra && s.rationale && (
        <div className="px-3.5 pb-3">
          <button
            onClick={() => setExpanded(e => !e)}
            className="flex items-center gap-1.5 text-[10px] text-[#6b7a9e] hover:text-[#e8eeff] transition-colors w-full"
          >
            <span>💡 Motivare AI</span>
            {s.wfv_auc != null && (
              <span className="text-[#303d57]">· AUC {s.wfv_auc.toFixed(3)}</span>
            )}
            <ChevronDown
              className={`w-3 h-3 ml-auto transition-transform ${expanded ? 'rotate-180' : ''}`}
            />
          </button>
          {expanded && (
            <p className="mt-2 text-[10px] text-[#6b7a9e] leading-relaxed">{s.rationale}</p>
          )}
        </div>
      )}
    </div>
  );
};

const MetricCol: React.FC<{ label: string; value: string; color?: string }> = ({ label, value, color }) => (
  <div className="flex-1 flex flex-col items-center gap-0.5 px-2">
    <span className="text-[8px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</span>
    <span className="text-sm font-bold" style={{ color: color ?? '#e8eeff' }}>{value}</span>
  </div>
);

const Tag: React.FC<{ color: string; children: React.ReactNode }> = ({ color, children }) => (
  <span
    className="text-[8px] font-bold px-1.5 py-0.5 rounded-full"
    style={{ color, background: `${color}22` }}
  >
    {children}
  </span>
);

function gradeAccent(grade: string): string {
  switch (grade) {
    case 'A+': return '#00e87a';
    case 'A': return '#22c55e';
    case 'B': return '#4a9eff';
    default: return '#ffffff';
  }
}
