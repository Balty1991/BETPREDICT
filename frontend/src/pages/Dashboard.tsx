import React, { useEffect, useMemo, useState } from 'react';
import { Activity, Sparkles, CheckCircle2, Layers, Bookmark, ChevronRight } from 'lucide-react';
import { TeamLogo } from '@/components/TeamLogo';
import { useAppData } from '@/context/DataContext';
import { useSavedPredictions } from '@/hooks/useSavedPredictions';
import { timeAgo, formatDate, formatTicketProb, isQualifiedVerdict } from '@/utils/filters';
import { profitUnits } from '@/utils/settlement';
import type { ClaudeVerdict } from '@/types/betpredict';

const RISK_LABELS: Record<string, string> = {
  foarte_sigur: 'Foarte sigur', sigur: 'Sigur', moderat: 'Moderat', riscant: 'Riscant',
};
const RISK_COLORS: Record<string, string> = {
  foarte_sigur: '#00e87a', sigur: '#4a9eff', moderat: '#f5a623', riscant: '#ff5c7a',
};

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

interface DashboardProps {
  onNavigate?: (page: 'predictions' | 'stats') => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate }) => {
  const { events: { events, loading: eventsLoading }, claude: { verdictsByEvent, accumulators, updatedAt, loading: claudeLoading } } = useAppData();
  const { predictions } = useSavedPredictions();

  const eventsById = useMemo(() => new Map(events.map(e => [String(e.event_id), e])), [events]);
  const verdicts = useMemo(() => Array.from(verdictsByEvent.values()), [verdictsByEvent]);
  const qualified = useMemo(() => verdicts.filter(isQualifiedVerdict), [verdicts]);

  const topPick = useMemo(
    () => [...qualified].sort((a, b) => b.probability - a.probability)[0] ?? null,
    [qualified]
  );
  const topPickEvent = topPick ? eventsById.get(String(topPick.event_id)) : undefined;
  const countdown = useCountdown(topPick?.event_date ?? null);

  const upcoming = useMemo(() => {
    const rest = topPick ? qualified.filter(v => v !== topPick) : qualified;
    return [...rest]
      .sort((a, b) => new Date(a.event_date ?? 0).getTime() - new Date(b.event_date ?? 0).getTime())
      .slice(0, 4);
  }, [qualified, topPick]);

  const bestTicket = accumulators.find(t => t.risk_level !== 'longshot') ?? accumulators[0] ?? null;

  const settled = predictions.filter(p => p.status !== 'pending');
  const wins = settled.filter(p => p.status === 'won').length;
  const losses = settled.filter(p => p.status === 'lost').length;
  const wr = settled.length ? Math.round((wins / settled.length) * 100) : null;
  const roi = settled.length
    ? Math.round((settled.reduce((acc, p) => acc + profitUnits(p.status as 'won' | 'lost', p.odds), 0) / settled.length) * 1000) / 10
    : null;

  const today = new Date();
  const dateStr = today.toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });

  if (eventsLoading || claudeLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3">
        <div className="w-8 h-8 border-2 border-[#00e87a] border-t-transparent rounded-full animate-spin" />
        <p className="text-[#6b7a9e] text-sm">Se încarcă dashboard-ul...</p>
      </div>
    );
  }

  return (
    <div className="pt-4 pb-4 flex flex-col gap-4">

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-extrabold text-[#e8eeff]">Dashboard</h2>
          <p className="text-[10px] capitalize text-[#6b7a9e]">{dateStr}</p>
        </div>
        <span className="text-[9px] font-bold px-2.5 py-1 rounded-full" style={{ background: '#a78bfa22', color: '#a78bfa' }}>
          ⟳ {timeAgo(updatedAt)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <KpiTile label="Meciuri urmărite" value={String(events.length)} icon={<Activity className="w-3.5 h-3.5" />} color="#4a9eff" />
        <KpiTile label="Verdicte AI" value={String(verdicts.length)} icon={<Sparkles className="w-3.5 h-3.5" />} color="#a78bfa" />
        <KpiTile label="Calificate" value={String(qualified.length)} icon={<CheckCircle2 className="w-3.5 h-3.5" />} color="#00e87a" />
        <KpiTile label="Bilete acumulator" value={String(accumulators.length)} icon={<Layers className="w-3.5 h-3.5" />} color="#f5a623" />
      </div>

      {verdicts.length === 0 ? (
        <EmptyPipelineNotice />
      ) : (
        <>
          {topPick && (
            <TopPickCard verdict={topPick} homeTeamId={topPickEvent?.home_team_id} awayTeamId={topPickEvent?.away_team_id}
              countdown={countdown} onNavigate={onNavigate} />
          )}

          <JournalSummary wins={wins} losses={losses} wr={wr} roi={roi} totalSaved={predictions.length}
            settledCount={settled.length} onNavigate={onNavigate} />

          {bestTicket && (
            <div className="rounded-[22px] p-4 flex flex-col gap-3" style={{ background: 'var(--bp-card)', border: '1px solid #f5a62333' }}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5" style={{ color: '#f5a623' }} />
                  <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: '#f5a623' }}>
                    Bilet recomandat · {bestTicket.label}
                  </span>
                </div>
                {onNavigate && (
                  <button onClick={() => onNavigate('predictions')} className="flex items-center gap-0.5 text-[10px] text-[#6b7a9e]">
                    Toate ({accumulators.length}) <ChevronRight className="w-3 h-3" />
                  </button>
                )}
              </div>
              <div className="flex items-center gap-4">
                <div className="flex-1 flex flex-col items-center gap-0.5">
                  <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">Cotă totală</span>
                  <span className="text-xl font-black text-[#e8eeff]">@{bestTicket.combined_odds.toFixed(2)}</span>
                </div>
                <div className="flex-1 flex flex-col items-center gap-0.5">
                  <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">Probabilitate</span>
                  <span className="text-xl font-black" style={{ color: '#00e87a' }}>{formatTicketProb(bestTicket.combined_probability_pct)}</span>
                </div>
                <div className="flex-1 flex flex-col items-center gap-0.5">
                  <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">Selecții</span>
                  <span className="text-xl font-black text-[#e8eeff]">{bestTicket.legs.length}</span>
                </div>
              </div>
            </div>
          )}

          {upcoming.length > 0 && (
            <div className="rounded-[22px] overflow-hidden" style={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border)' }}>
              <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--bp-border)' }}>
                <span className="text-sm font-bold text-[#e8eeff]">Vin în curând</span>
                {onNavigate && (
                  <button onClick={() => onNavigate('predictions')} className="flex items-center gap-0.5 text-[10px] text-[#6b7a9e]">
                    Toate ({qualified.length}) <ChevronRight className="w-3 h-3" />
                  </button>
                )}
              </div>
              <div className="p-3 flex flex-col gap-2">
                {upcoming.map((v, i) => (
                  <div key={i} className="flex items-center justify-between py-2 px-3 rounded-xl" style={{ background: 'var(--bp-surface)' }}>
                    <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                      <span className="text-xs font-semibold truncate text-[#e8eeff]">{v.home_team} vs {v.away_team}</span>
                      <span className="text-[10px] text-[#6b7a9e]">⚡ {v.market_label} · {formatDate(v.event_date ?? '')}</span>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-[10px] font-bold" style={{ color: RISK_COLORS[v.risk_tier] ?? '#e8eeff' }}>
                        {v.probability.toFixed(0)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

const KpiTile: React.FC<{ label: string; value: string; icon: React.ReactNode; color: string }> = ({ label, value, icon, color }) => (
  <div className="rounded-2xl p-3 flex flex-col gap-1.5 border-t-2" style={{ background: 'var(--bp-card)', borderTopColor: color }}>
    <div className="flex items-center gap-1.5" style={{ color }}>
      {icon}
      <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</span>
    </div>
    <span className="text-2xl font-black" style={{ color }}>{value}</span>
  </div>
);

const TopPickCard: React.FC<{
  verdict: ClaudeVerdict; homeTeamId?: number | null; awayTeamId?: number | null;
  countdown: { days: number; hours: number; mins: number; secs: number };
  onNavigate?: (page: 'predictions' | 'stats') => void;
}> = ({ verdict: v, homeTeamId, awayTeamId, countdown, onNavigate }) => {
  const glow = v.accumulator_eligible ? '#00e87a' : (RISK_COLORS[v.risk_tier] ?? '#a78bfa');
  return (
    <div className="relative">
      <div className="absolute inset-0 rounded-[26px] pointer-events-none" style={{ boxShadow: `0 0 22px 1px ${glow}55` }} />
      <div className="rounded-[26px] p-4 flex flex-col gap-3 relative" style={{ background: 'var(--bp-card)', border: `1px solid ${glow}77` }}>
        <div className="flex items-center justify-between">
          <span className="text-[9px] font-bold uppercase tracking-widest" style={{ color: glow }}>★ Pick-ul zilei</span>
          {onNavigate && (
            <button onClick={() => onNavigate('predictions')} className="flex items-center gap-0.5 text-[10px] text-[#6b7a9e]">
              Detalii <ChevronRight className="w-3 h-3" />
            </button>
          )}
        </div>

        <div className="flex items-center justify-center gap-4">
          <div className="flex flex-col items-center gap-1 flex-1">
            <TeamLogo id={homeTeamId} size={36} />
            <span className="text-xs font-bold text-center leading-tight text-[#e8eeff]">{v.home_team}</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <span className="text-[9px] text-[#6b7a9e] max-w-[80px] text-center truncate">{v.league}</span>
            <span className="text-sm font-black text-[#303d57]">VS</span>
          </div>
          <div className="flex flex-col items-center gap-1 flex-1">
            <TeamLogo id={awayTeamId} size={36} />
            <span className="text-xs font-bold text-center leading-tight text-[#e8eeff]">{v.away_team}</span>
          </div>
        </div>

        <div className="rounded-xl p-3 flex items-center justify-around" style={{ background: 'var(--bp-surface2)' }}>
          {[
            { label: 'ZILE', value: countdown.days }, { label: 'ORE', value: countdown.hours },
            { label: 'MIN', value: countdown.mins }, { label: 'SEC', value: countdown.secs },
          ].map(({ label, value }) => (
            <div key={label} className="flex flex-col items-center gap-0.5">
              <span className="text-2xl font-black tabular-nums w-10 text-center text-[#e8eeff]">{String(value).padStart(2, '0')}</span>
              <span className="text-[9px] font-bold tracking-widest text-[#6b7a9e]">{label}</span>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm font-bold text-[#e8eeff]">{v.market_label}</span>
            <span className="text-[10px] block text-[#6b7a9e]">Risc: {RISK_LABELS[v.risk_tier] ?? v.risk_tier}</span>
          </div>
          <div className="text-right">
            <span className="text-2xl font-black block" style={{ color: glow }}>{v.probability.toFixed(0)}%</span>
            {v.odds != null && <span className="text-[10px] text-[#6b7a9e]">@{v.odds.toFixed(2)}</span>}
          </div>
        </div>
      </div>
    </div>
  );
};

const JournalSummary: React.FC<{
  wins: number; losses: number; wr: number | null; roi: number | null;
  totalSaved: number; settledCount: number; onNavigate?: (page: 'predictions' | 'stats') => void;
}> = ({ wins, losses, wr, roi, totalSaved, settledCount, onNavigate }) => (
  <div className="rounded-[22px] p-4 flex flex-col gap-3" style={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border)' }}>
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-1.5">
        <Bookmark className="w-3.5 h-3.5 text-[#4a9eff]" />
        <span className="text-[10px] font-bold uppercase tracking-widest text-[#4a9eff]">Jurnalul meu</span>
      </div>
      {onNavigate && (
        <button onClick={() => onNavigate('stats')} className="flex items-center gap-0.5 text-[10px] text-[#6b7a9e]">
          Statistici <ChevronRight className="w-3 h-3" />
        </button>
      )}
    </div>
    {totalSaved === 0 ? (
      <p className="text-xs text-[#6b7a9e] leading-relaxed">
        Nu ai salvat încă nicio predicție. Din tab-ul Predicții, apasă „Salvează" pe un verdict AI ca să-ți urmărești aici win/lose și ROI.
      </p>
    ) : (
      <div className="grid grid-cols-4 gap-2">
        <MiniStat label="W" value={String(wins)} color="#00e87a" />
        <MiniStat label="L" value={String(losses)} color="#ff3d5a" />
        <MiniStat label="WR" value={wr != null ? `${wr}%` : '—'} color={wr != null && wr >= 55 ? '#00e87a' : '#f5a623'} />
        <MiniStat label="ROI" value={roi != null ? `${roi > 0 ? '+' : ''}${roi}%` : '—'} color={roi != null && roi > 0 ? '#00e87a' : '#ff3d5a'} />
      </div>
    )}
    {totalSaved > 0 && settledCount === 0 && (
      <p className="text-[10px] text-[#6b7a9e]">{totalSaved} predicții salvate, încă în așteptare — reveniți după ce meciurile se termină.</p>
    )}
  </div>
);

const MiniStat: React.FC<{ label: string; value: string; color: string }> = ({ label, value, color }) => (
  <div className="flex flex-col items-center gap-0.5 rounded-xl py-2 border-t-2" style={{ background: 'var(--bp-surface)', borderTopColor: color }}>
    <span className="text-[9px] font-bold uppercase tracking-widest text-[#6b7a9e]">{label}</span>
    <span className="text-base font-bold" style={{ color }}>{value}</span>
  </div>
);

const EmptyPipelineNotice: React.FC = () => (
  <div className="flex flex-col items-center justify-center py-16 gap-4">
    <div className="w-16 h-16 rounded-2xl flex items-center justify-center" style={{ background: '#a78bfa1a', border: '1px solid #a78bfa33' }}>
      <Sparkles className="w-7 h-7" style={{ color: '#a78bfa' }} />
    </div>
    <div className="text-center">
      <p className="font-bold text-[#e8eeff] mb-1">Analiza Claude AI nu a rulat încă azi</p>
      <p className="text-[#6b7a9e] text-sm max-w-[260px] leading-relaxed">
        Rulează o dată pe zi, dimineața devreme. Revino în câteva ore sau verifică tab-ul Predicții.
      </p>
    </div>
  </div>
);
