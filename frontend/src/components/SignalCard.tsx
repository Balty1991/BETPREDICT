import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { TeamLogo } from './TeamLogo';
import { GradeBadge } from './GradeBadge';
import { ScoreBar } from './ScoreBar';
import type { Signal } from '@/types/betpredict';
import {
  effectiveScore, effectiveGrade, effectiveEV, effectiveProb,
  isVeyra, marketLabel, formatDate, gradeColor,
} from '@/utils/filters';

interface SignalCardProps {
  signal: Signal;
  isValue?: boolean;
  allSignalsForEvent?: Signal[];
}

export const SignalCard: React.FC<SignalCardProps> = ({ signal: s, isValue, allSignalsForEvent }) => {
  const [expanded, setExpanded] = useState(false);
  const [marketsExpanded, setMarketsExpanded] = useState(false);

  const grade = effectiveGrade(s);
  const sc = effectiveScore(s);
  const ev = effectiveEV(s);
  const prob = effectiveProb(s);
  const veyra = isVeyra(s);
  const mktLabel = s.market_label ?? marketLabel(s.market);
  const accent = gradeColor(grade);

  const evPct = (ev * 100).toFixed(1);
  const evPos = ev > 0;
  const probPct = prob.toFixed(0);

  const predictedScore = s.most_likely_score ?? s.poisson_score ?? null;
  const riskTier = s.risk_tier?.toLowerCase() ?? '';
  const otherMarkets = allSignalsForEvent?.filter(x => x.market !== s.market) ?? [];

  const rationale = s.ai_insight ?? s.rationale;

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: 'var(--bp-card)', border: `1px solid ${accent}33` }}
    >
      <div className="flex">
        <div className="w-1 flex-shrink-0" style={{ background: `linear-gradient(to bottom, ${accent}, ${accent}66)` }} />
        <div className="flex-1 min-w-0">

          <div className="flex items-center justify-between px-3 pt-3 pb-1">
            <span className="text-[10px] text-[#6b7a9e] font-medium tracking-wide truncate max-w-[70%]">
              {s.league ?? 'Liga necunoscută'} · {formatDate(s.event_date)}
            </span>
            <GradeBadge grade={grade} />
          </div>

          <div className="flex items-center justify-between px-3 py-2">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <TeamLogo id={s.home_team_id} size={28} />
              <span className="text-sm font-bold text-[#e8eeff] truncate">{s.home_team}</span>
            </div>
            <span className="text-[10px] font-bold text-[#303d57] mx-2 flex-shrink-0">VS</span>
            <div className="flex items-center gap-2 flex-1 min-w-0 justify-end">
              <span className="text-sm font-bold text-[#e8eeff] truncate text-right">{s.away_team}</span>
              <TeamLogo id={s.away_team_id} size={28} />
            </div>
          </div>

          <div className="mx-3 mb-2.5 rounded-xl p-3" style={{ background: 'var(--bp-card2)' }}>
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-sm font-semibold text-[#e8eeff]">⚡ {mktLabel}</span>
              <div className="flex items-center gap-1.5">
                {isValue && (
                  <span className="text-[8px] font-bold px-1.5 py-0.5 rounded-full bg-[#00e87a22] text-[#00e87a]">★ VALUE</span>
                )}
                <span
                  className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
                  style={{ background: veyra ? '#2BE5C522' : '#4a9eff22', color: veyra ? '#2BE5C5' : '#4a9eff' }}
                >
                  {veyra ? 'VEYRA v5' : 'ENGINE v6'}
                </span>
              </div>
            </div>

            <div className="flex items-center divide-x divide-white/10">
              <MetricCol label="COTĂ" value={s.odds?.toFixed(2) ?? '—'} />
              <MetricCol label="PROB" value={`${probPct}%`} color="#00e87a" />
              <MetricCol label="EV" value={`${evPos ? '+' : ''}${evPct}%`} color={evPos ? '#00e87a' : '#ff3d5a'} />
              <MetricCol label="SCOR" value={predictedScore ?? '—'} color={predictedScore ? '#4a9eff' : '#6b7a9e'} />
            </div>
          </div>

          <div className="px-3 pb-2">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[9px] font-bold uppercase tracking-widest text-[#6b7a9e]">SmartBet {sc.toFixed(0)}</span>
              <div className="flex gap-1 ml-auto flex-wrap justify-end">
                {riskTier === 'low' && <Tag color="#00e87a">✓ risc scăzut</Tag>}
                {riskTier === 'medium' && <Tag color="#ffb830">~ risc mediu</Tag>}
                {(riskTier === 'high' || riskTier === 'very_high') && <Tag color="#ff3d5a">⚠ risc înalt</Tag>}
                {evPos && <Tag color="#00e87a">EV+</Tag>}
              </div>
            </div>
            <ScoreBar score={sc} />
          </div>

          {rationale && (
            <div className="px-3 pb-2.5">
              <button
                onClick={() => setExpanded(e => !e)}
                className="flex items-center gap-1.5 text-[10px] text-[#6b7a9e] hover:text-[#e8eeff] transition-colors w-full"
              >
                <span>💡 Motivare AI</span>
                <ChevronDown className={`w-3 h-3 ml-auto transition-transform ${expanded ? 'rotate-180' : ''}`} />
              </button>
              {expanded && (
                <p className="mt-1.5 text-[10px] text-[#6b7a9e] leading-relaxed">{rationale}</p>
              )}
            </div>
          )}

          <button
            onClick={() => setMarketsExpanded(m => !m)}
            className="w-full flex items-center justify-center gap-1.5 py-2.5 border-t border-white/5 text-[10px] text-[#6b7a9e] hover:text-[#e8eeff] hover:bg-white/[0.02] transition-colors"
          >
            <span>Toate piețele{otherMarkets.length > 0 ? ` (${otherMarkets.length + 1})` : ''}</span>
            {marketsExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>

          {marketsExpanded && otherMarkets.length > 0 && (
            <div className="px-3 pb-3 flex flex-col gap-2">
              {otherMarkets.map((m2, i) => (
                <MiniMarketRow key={i} signal={m2} />
              ))}
            </div>
          )}

        </div>
      </div>
    </div>
  );
};

const MetricCol: React.FC<{ label: string; value: string; color?: string }> = ({ label, value, color }) => (
  <div className="flex-1 flex flex-col items-center gap-0.5 px-1.5">
    <span className="text-[8px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</span>
    <span className="text-sm font-bold" style={{ color: color ?? '#e8eeff' }}>{value}</span>
  </div>
);

const Tag: React.FC<{ color: string; children: React.ReactNode }> = ({ color, children }) => (
  <span className="text-[8px] font-bold px-1.5 py-0.5 rounded-full" style={{ color, background: `${color}22` }}>
    {children}
  </span>
);

const MiniMarketRow: React.FC<{ signal: Signal }> = ({ signal: s }) => {
  const ev = effectiveEV(s);
  const mkt = s.market_label ?? marketLabel(s.market);
  return (
    <div className="flex items-center justify-between py-1.5 px-2 rounded-lg" style={{ background: 'var(--bp-surface)' }}>
      <span className="text-[10px] text-[#6b7a9e]">{mkt}</span>
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-[#e8eeff]">@{s.odds?.toFixed(2)}</span>
        <span className="text-[10px] font-bold" style={{ color: ev > 0 ? '#00e87a' : '#ff3d5a' }}>
          {ev > 0 ? '+' : ''}{(ev * 100).toFixed(1)}%
        </span>
      </div>
    </div>
  );
};
