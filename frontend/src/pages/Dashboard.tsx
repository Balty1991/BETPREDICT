import React from 'react';
import { TrendingUp, Target, RefreshCw, Zap } from 'lucide-react';
import { TeamLogo } from '@/components/TeamLogo';
import { GradeBadge } from '@/components/GradeBadge';
import { useBetPredictData } from '@/hooks/useBetPredictData';
import { filteredSignals, vbSetFromList, journalStats, effectiveGrade, effectiveEV, marketLabel } from '@/utils/filters';

export const Dashboard: React.FC = () => {
  const { signals, journal, valueBets, updatedAt, loading, refresh } = useBetPredictData();
  const vbSet = vbSetFromList(valueBets);
  const picks = filteredSignals(signals, vbSet);
  const stats = journalStats(journal);

  const roiColor = stats.roi == null ? '#6b7a9e' : stats.roi > 0 ? '#00e87a' : stats.roi > -20 ? '#ffb830' : '#ff3d5a';
  const wrColor = stats.wr == null ? '#6b7a9e' : stats.wr >= 55 ? '#00e87a' : stats.wr >= 45 ? '#ffb830' : '#ff3d5a';

  const top3 = picks.slice(0, 3);

  return (
    <div className="pt-4 pb-4 flex flex-col gap-4">

      {/* KPI Row */}
      <div className="grid grid-cols-3 gap-2">
        <KpiCard label="Predicții" value={String(picks.length)} icon={<Zap className="w-4 h-4" />} color="#00e87a" />
        <KpiCard label="Win Rate" value={stats.wr != null ? `${stats.wr}%` : '—'} icon={<Target className="w-4 h-4" />} color={wrColor} />
        <KpiCard label="ROI" value={stats.roi != null ? `${stats.roi > 0 ? '+' : ''}${stats.roi}%` : '—'} icon={<TrendingUp className="w-4 h-4" />} color={roiColor} />
      </div>

      {/* Plan Zilei */}
      <Section title="Plan Zilei" badge={top3.length > 0 ? `${top3.length} picks` : undefined}>
        {loading ? (
          <Skeleton />
        ) : top3.length === 0 ? (
          <p className="text-[#6b7a9e] text-sm text-center py-4">Nicio predicție activă momentan</p>
        ) : (
          <div className="flex flex-col gap-2">
            {top3.map((s, i) => (
              <MiniPickRow key={`${s.event_id}_${i}`} signal={s} isValue={vbSet.has(`${s.event_id}_${s.market}`)} />
            ))}
          </div>
        )}
      </Section>

      {/* Statistici rapide */}
      <Section title="Statistici Generale">
        <div className="grid grid-cols-2 gap-3">
          <StatBox label="Parieri urmărite" value={stats.settled + stats.pending} />
          <StatBox label="Decontate" value={stats.settled} />
          <StatBox label="Victorii" value={stats.wins} color="#00e87a" />
          <StatBox label="Înfrângeri" value={stats.losses} color="#ff3d5a" />
        </div>
        {stats.settled > 0 && (
          <div className="mt-3 p-3 rounded-xl bg-white/5 flex items-center justify-between">
            <span className="text-[#6b7a9e] text-xs">Profit total</span>
            <span className="font-bold text-sm" style={{ color: stats.profit >= 0 ? '#00e87a' : '#ff3d5a' }}>
              {stats.profit >= 0 ? '+' : ''}{stats.profit.toFixed(2)}u
            </span>
          </div>
        )}
      </Section>

      {/* Footer */}
      <div className="flex items-center justify-between px-1">
        <span className="text-[10px] text-[#303d57]">
          {updatedAt ? `Actualizat: ${new Date(updatedAt).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })}` : 'Se încarcă...'}
        </span>
        <button onClick={refresh} className="flex items-center gap-1 text-[10px] text-[#6b7a9e] hover:text-[#e8eeff] transition-colors">
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          Reîmprospătează
        </button>
      </div>
    </div>
  );
};

const KpiCard: React.FC<{ label: string; value: string; icon: React.ReactNode; color: string }> = ({ label, value, icon, color }) => (
  <div className="rounded-xl p-3 flex flex-col gap-1.5" style={{ background: '#0d1322', border: '1px solid rgba(255,255,255,.06)' }}>
    <div className="flex items-center gap-1.5" style={{ color }}>
      {icon}
      <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</span>
    </div>
    <span className="text-xl font-bold" style={{ color }}>{value}</span>
  </div>
);

const Section: React.FC<{ title: string; badge?: string; children: React.ReactNode }> = ({ title, badge, children }) => (
  <div className="rounded-2xl overflow-hidden" style={{ background: '#0d1322', border: '1px solid rgba(255,255,255,.06)' }}>
    <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
      <span className="text-sm font-bold text-[#e8eeff]">{title}</span>
      {badge && <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-[#00e87a22] text-[#00e87a]">{badge}</span>}
    </div>
    <div className="p-3">{children}</div>
  </div>
);

const StatBox: React.FC<{ label: string; value: number; color?: string }> = ({ label, value, color }) => (
  <div className="rounded-xl p-3 bg-white/[0.03] flex flex-col gap-1">
    <span className="text-[9px] text-[#6b7a9e] font-medium uppercase tracking-wide">{label}</span>
    <span className="text-lg font-bold" style={{ color: color ?? '#e8eeff' }}>{value}</span>
  </div>
);

const Skeleton: React.FC = () => (
  <div className="flex flex-col gap-2">
    {[1,2,3].map(i => (
      <div key={i} className="h-12 rounded-xl bg-white/5 animate-pulse" />
    ))}
  </div>
);

interface MiniPickRowProps { signal: ReturnType<typeof filteredSignals>[0]; isValue?: boolean; }
const MiniPickRow: React.FC<MiniPickRowProps> = ({ signal: s }) => {
  const grade = effectiveGrade(s);
  const ev = effectiveEV(s);
  const evPct = (ev * 100).toFixed(1);
  const mkt = s.market_label ?? marketLabel(s.market);

  return (
    <div className="flex items-center gap-2.5 px-2 py-2 rounded-xl bg-white/[0.03]">
      <GradeBadge grade={grade} small />
      <div className="flex items-center gap-1.5 flex-1 min-w-0">
        <TeamLogo id={s.home_team_id} size={18} />
        <span className="text-xs text-[#e8eeff] truncate">{s.home_team}</span>
        <span className="text-[9px] text-[#303d57]">vs</span>
        <span className="text-xs text-[#e8eeff] truncate">{s.away_team}</span>
      </div>
      <div className="flex flex-col items-end flex-shrink-0 gap-0.5">
        <span className="text-[9px] text-[#6b7a9e] font-medium truncate max-w-[80px]">{mkt}</span>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-bold text-[#e8eeff]">@{s.odds?.toFixed(2)}</span>
          <span className="text-[10px] font-bold" style={{ color: ev > 0 ? '#00e87a' : '#ff3d5a' }}>
            {ev > 0 ? '+' : ''}{evPct}%
          </span>
        </div>
      </div>
    </div>
  );
};
