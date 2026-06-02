import React, { useState, useEffect } from 'react';
import { Zap, Star, Activity } from 'lucide-react';
import { TeamLogo } from '@/components/TeamLogo';
import { GradeBadge } from '@/components/GradeBadge';
import { useBetPredictData } from '@/hooks/useBetPredictData';
import {
  filteredSignals, vbSetFromList, journalStats, effectiveGrade,
  effectiveEV, effectiveScore, marketLabel, formatDate,
} from '@/utils/filters';
import type { Signal } from '@/types/betpredict';

function useCountdown(targetDate: string | null) {
  const [timeLeft, setTimeLeft] = useState({ days: 0, hours: 0, mins: 0, secs: 0 });

  useEffect(() => {
    if (!targetDate) return;
    const update = () => {
      const diff = new Date(targetDate).getTime() - Date.now();
      if (diff <= 0) { setTimeLeft({ days: 0, hours: 0, mins: 0, secs: 0 }); return; }
      setTimeLeft({
        days: Math.floor(diff / 86400000),
        hours: Math.floor((diff % 86400000) / 3600000),
        mins: Math.floor((diff % 3600000) / 60000),
        secs: Math.floor((diff % 60000) / 1000),
      });
    };
    update();
    const t = setInterval(update, 1000);
    return () => clearInterval(t);
  }, [targetDate]);

  return timeLeft;
}

export const Dashboard: React.FC = () => {
  const { signals, journal, valueBets, updatedAt, loading } = useBetPredictData();
  const vbSet = vbSetFromList(valueBets);
  const picks = filteredSignals(signals, vbSet);
  const stats = journalStats(journal);

  const roiColor = stats.roi == null ? 'var(--bp-muted)' : stats.roi > 0 ? '#00e87a' : stats.roi > -20 ? '#ffb830' : '#ff3d5a';
  const wrColor = stats.wr == null ? 'var(--bp-muted)' : stats.wr >= 55 ? '#00e87a' : stats.wr >= 45 ? '#ffb830' : '#ff3d5a';

  const featured = picks[0] ?? null;
  const top3 = picks.slice(0, 3);
  const countdown = useCountdown(featured?.event_date ?? null);

  const today = new Date();
  const dateStr = today.toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
  const updatedStr = updatedAt
    ? new Date(updatedAt).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
    : null;

  return (
    <div className="pt-4 pb-4 flex flex-col gap-4">

      {/* Header row — date + last update */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-extrabold" style={{ color: 'var(--bp-text)' }}>Dashboard</h2>
          <p className="text-[10px] capitalize" style={{ color: 'var(--bp-muted)' }}>{dateStr}</p>
        </div>
        {updatedStr && (
          <span
            className="text-[10px] px-2.5 py-1 rounded-lg"
            style={{ color: 'var(--bp-muted)', background: 'var(--bp-surface)' }}
          >
            Actualizat {updatedStr}
          </span>
        )}
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-3 gap-2">
        <KpiCard label="Semnale" value={String(signals.length)} icon={<Activity className="w-4 h-4" />} color="#4a9eff" />
        <KpiCard label="Value Bets" value={String(valueBets.length)} icon={<Star className="w-4 h-4" />} color="#ffb830" />
        <KpiCard label="Predicții" value={String(picks.length)} icon={<Zap className="w-4 h-4" />} color="#00e87a" />
      </div>

      {/* Featured Match + Countdown */}
      {featured && (
        <Section title="Meciul Zilei">
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-center gap-4">
              <div className="flex flex-col items-center gap-1 flex-1">
                <TeamLogo id={featured.home_team_id} size={40} />
                <span className="text-xs font-bold text-center leading-tight mt-1 text-[#e8eeff]">{featured.home_team}</span>
              </div>
              <div className="flex flex-col items-center gap-1">
                <div className="text-[10px] font-medium text-[#6b7a9e]">{featured.league}</div>
                <span className="text-sm font-black text-[#303d57]">VS</span>
                <GradeBadge grade={effectiveGrade(featured)} />
              </div>
              <div className="flex flex-col items-center gap-1 flex-1">
                <TeamLogo id={featured.away_team_id} size={40} />
                <span className="text-xs font-bold text-center leading-tight mt-1 text-[#e8eeff]">{featured.away_team}</span>
              </div>
            </div>

            {/* Countdown */}
            <div className="rounded-xl p-3 flex items-center justify-around" style={{ background: 'var(--bp-surface2)' }}>
              {[
                { label: 'ZILE', value: countdown.days },
                { label: 'ORE', value: countdown.hours },
                { label: 'MIN', value: countdown.mins },
                { label: 'SEC', value: countdown.secs },
              ].map(({ label, value }) => (
                <div key={label} className="flex flex-col items-center gap-0.5">
                  <span className="text-2xl font-black tabular-nums w-10 text-center" style={{ color: 'var(--bp-text)' }}>
                    {String(value).padStart(2, '0')}
                  </span>
                  <span className="text-[8px] font-bold tracking-widest" style={{ color: 'var(--bp-muted)' }}>{label}</span>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[10px] text-[#6b7a9e]">
                ⚡ {featured.market_label ?? marketLabel(featured.market)}
              </span>
              <span className="text-[10px] font-bold" style={{ color: 'var(--bp-text)' }}>@{featured.odds?.toFixed(2)}</span>
            </div>
          </div>
        </Section>
      )}

      {/* Decision Center */}
      {picks.length > 0 && (
        <Section title="Decision Center" badge={`${picks.length} active`}>
          <div className="flex flex-col gap-2">
            {picks.slice(0, 5).map((s, i) => (
              <DecisionRow key={`${s.event_id}_${i}`} signal={s} rank={i + 1} />
            ))}
          </div>
        </Section>
      )}

      {/* Planul Zilei */}
      <Section title="Planul Zilei" badge={top3.length > 0 ? `${top3.length} picks` : undefined}>
        {loading ? (
          <Skeleton />
        ) : top3.length === 0 ? (
          <p className="text-sm text-center py-4" style={{ color: 'var(--bp-muted)' }}>Nicio predicție activă momentan</p>
        ) : (
          <div className="flex flex-col gap-2">
            {top3.map((s, i) => (
              <PlanRow key={`${s.event_id}_${i}`} signal={s} index={i + 1} />
            ))}
          </div>
        )}
      </Section>

      {/* Value Bets */}
      {valueBets.length > 0 && (
        <Section title="Value Bets" badge={`${valueBets.length}`}>
          <div className="flex flex-col gap-2">
            {valueBets.map((vb, i) => {
              const teamLabel = vb.home_team && vb.away_team
                ? `${vb.home_team} vs ${vb.away_team}`
                : (() => { const sig = signals.find(s => s.event_id == vb.event_id); return sig ? `${sig.home_team} vs ${sig.away_team}` : `Event ${vb.event_id}`; })();
              const mkt = vb.market_label ?? marketLabel(vb.market);
              const oddsVal = vb.market_odds ?? vb.odds;
              const edgeStr = typeof vb.edge_pct === 'string'
                ? vb.edge_pct.replace(/^\+/, '')
                : vb.edge != null ? `${(vb.edge * 100).toFixed(1)}%` : '—';
              const grade = vb.quality_grade;
              return (
                <div key={i} className="flex items-center justify-between py-2 px-3 rounded-xl" style={{ background: 'var(--bp-surface)' }}>
                  <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      {grade && (
                        <span className="text-[8px] font-bold px-1 py-0.5 rounded"
                          style={{ background: 'rgba(255,184,48,0.15)', color: '#ffb830' }}>
                          {grade}
                        </span>
                      )}
                      <span className="text-xs truncate" style={{ color: 'var(--bp-text)' }}>{teamLabel}</span>
                    </div>
                    <span className="text-[10px]" style={{ color: 'var(--bp-muted)' }}>
                      {mkt}{vb.event_date ? ` · ${formatDate(vb.event_date)}` : ''}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-[10px]" style={{ color: 'var(--bp-text)' }}>
                      @{oddsVal != null ? oddsVal.toFixed(2) : '—'}
                    </span>
                    <span className="text-[10px] font-bold text-[#00e87a]">+{edgeStr}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* Steam Monitor */}
      <Section title="Steam Monitor">
        <div className="grid grid-cols-2 gap-3">
          <StatBox label="Win Rate" value={stats.wr != null ? `${stats.wr}%` : '—'} color={wrColor} />
          <StatBox label="ROI" value={stats.roi != null ? `${stats.roi > 0 ? '+' : ''}${stats.roi}%` : '—'} color={roiColor} />
          <StatBox label="Victorii" value={String(stats.wins)} color="#00e87a" />
          <StatBox label="Înfrângeri" value={String(stats.losses)} color="#ff3d5a" />
        </div>
        {stats.settled > 0 && (
          <div className="mt-3 p-3 rounded-xl flex items-center justify-between" style={{ background: 'var(--bp-surface2)' }}>
            <span className="text-xs" style={{ color: 'var(--bp-muted)' }}>{stats.settled} decontate · {stats.pending} în așteptare</span>
            <span className="font-bold text-sm" style={{ color: stats.profit >= 0 ? '#00e87a' : '#ff3d5a' }}>
              {stats.profit >= 0 ? '+' : ''}{stats.profit.toFixed(2)}u
            </span>
          </div>
        )}
      </Section>
    </div>
  );
};

const KpiCard: React.FC<{ label: string; value: string; icon: React.ReactNode; color: string }> = ({ label, value, icon, color }) => (
  <div className="rounded-xl p-3 flex flex-col gap-1.5" style={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border)' }}>
    <div className="flex items-center gap-1.5" style={{ color }}>
      {icon}
      <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color: 'var(--bp-muted)' }}>{label}</span>
    </div>
    <span className="text-xl font-bold" style={{ color }}>{value}</span>
  </div>
);

const Section: React.FC<{ title: string; badge?: string; children: React.ReactNode }> = ({ title, badge, children }) => (
  <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border)' }}>
    <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--bp-surface2)' }}>
      <span className="text-sm font-bold" style={{ color: 'var(--bp-text)' }}>{title}</span>
      {badge && <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-[#00e87a22] text-[#00e87a]">{badge}</span>}
    </div>
    <div className="p-3">{children}</div>
  </div>
);

const StatBox: React.FC<{ label: string; value: string; color: string }> = ({ label, value, color }) => (
  <div className="rounded-xl p-3 flex flex-col gap-1" style={{ background: 'var(--bp-surface)' }}>
    <span className="text-[9px] font-medium uppercase tracking-wide" style={{ color: 'var(--bp-muted)' }}>{label}</span>
    <span className="text-lg font-bold" style={{ color }}>{value}</span>
  </div>
);

const Skeleton: React.FC = () => (
  <div className="flex flex-col gap-2">
    {[1, 2, 3].map(i => <div key={i} className="h-12 rounded-xl bg-white/5 animate-pulse" />)}
  </div>
);

const PlanRow: React.FC<{ signal: Signal; index: number }> = ({ signal: s, index }) => {
  const grade = effectiveGrade(s);
  const ev = effectiveEV(s);
  const mkt = s.market_label ?? marketLabel(s.market);

  return (
    <div className="flex items-center gap-2.5 px-2 py-2 rounded-xl" style={{ background: 'var(--bp-surface)' }}>
      <span className="text-[11px] font-black w-5 text-center" style={{ color: 'var(--bp-dim)' }}>{index}</span>
      <GradeBadge grade={grade} small />
      <div className="flex flex-col flex-1 min-w-0 gap-0.5">
        <div className="flex items-center gap-1.5 min-w-0">
          <TeamLogo id={s.home_team_id} size={16} />
          <span className="text-xs truncate text-[#e8eeff]">{s.home_team}</span>
          <span className="text-[9px] text-[#303d57]">vs</span>
          <span className="text-xs truncate text-[#e8eeff]">{s.away_team}</span>
        </div>
        <span className="text-[9px]" style={{ color: 'var(--bp-muted)' }}>{formatDate(s.event_date)}</span>
      </div>
      <div className="flex flex-col items-end flex-shrink-0 gap-0.5">
        <span className="text-[9px] font-medium truncate max-w-[80px] text-[#6b7a9e]">{mkt}</span>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-bold text-[#e8eeff]">@{s.odds?.toFixed(2)}</span>
          <span className="text-[10px] font-bold" style={{ color: ev > 0 ? '#00e87a' : '#ff3d5a' }}>
            {ev > 0 ? '+' : ''}{(ev * 100).toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
};

const DecisionRow: React.FC<{ signal: Signal; rank: number }> = ({ signal: s, rank }) => {
  const sc = effectiveScore(s);
  const ev = effectiveEV(s);
  const grade = effectiveGrade(s);

  return (
    <div
      className="flex items-center gap-2 px-2 py-2 rounded-xl"
      style={{ background: 'var(--bp-surface)', border: '1px solid var(--bp-border)' }}
    >
      <span className="text-[10px] font-black w-4 text-center" style={{ color: 'var(--bp-dim)' }}>{rank}</span>
      <GradeBadge grade={grade} small />
      <div className="flex-1 min-w-0">
        <span className="text-xs truncate block text-[#e8eeff]">{s.home_team} vs {s.away_team}</span>
        <span className="text-[9px] text-[#6b7a9e]">{formatDate(s.event_date)}</span>
      </div>
      <div className="flex flex-col items-end gap-0.5">
        <span className="text-[10px] font-bold text-[#4a9eff]">{sc.toFixed(0)}</span>
        <span className="text-[9px] font-bold" style={{ color: ev > 0 ? '#00e87a' : 'var(--bp-muted)' }}>
          EV {ev > 0 ? '+' : ''}{(ev * 100).toFixed(1)}%
        </span>
      </div>
    </div>
  );
};
