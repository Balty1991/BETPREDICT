import React, { useMemo } from 'react';
import { Shield, Star, TrendingUp, Zap } from 'lucide-react';
import { SignalCard } from '@/components/SignalCard';
import { useBetPredictData } from '@/hooks/useBetPredictData';
import { effectiveGrade, effectiveScore, effectiveEV, vbSetFromList } from '@/utils/filters';

const PREMIUM_GRADES = new Set(['A+', 'A']);

export const PremiumPage: React.FC = () => {
  const { signals, valueBets, loading } = useBetPredictData();
  const vbSet = vbSetFromList(valueBets);

  const premiumPicks = useMemo(() => {
    return signals
      .filter(s => {
        const grade = effectiveGrade(s);
        const sc = effectiveScore(s);
        const ev = effectiveEV(s);
        const odds = s.odds ?? 0;
        return PREMIUM_GRADES.has(grade) && sc >= 65 && ev > 0 && odds >= 1.2 && odds <= 4.0;
      })
      .sort((a, b) => {
        const evBonus = (effectiveEV(b) - effectiveEV(a)) * 30;
        return effectiveScore(b) - effectiveScore(a) + evBonus;
      });
  }, [signals]);

  const valuePremium = premiumPicks.filter(s => vbSet.has(`${s.event_id}_${s.market}`));
  const avgEv = premiumPicks.length > 0
    ? (premiumPicks.reduce((acc, s) => acc + effectiveEV(s), 0) / premiumPicks.length * 100).toFixed(1)
    : '—';
  const avgScore = premiumPicks.length > 0
    ? Math.round(premiumPicks.reduce((acc, s) => acc + effectiveScore(s), 0) / premiumPicks.length)
    : 0;

  return (
    <div className="pt-4 pb-4 flex flex-col gap-4">

      {/* Header */}
      <div
        className="rounded-2xl p-4 flex flex-col gap-3"
        style={{
          background: 'linear-gradient(135deg, rgba(255,184,48,0.12) 0%, rgba(255,107,53,0.08) 100%)',
          border: '1px solid rgba(255,184,48,0.25)',
        }}
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#ffb830] to-[#ff6b35] flex items-center justify-center flex-shrink-0">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-extrabold text-[#e8eeff]">PREMIUM</h2>
            <p className="text-[10px] text-[#6b7a9e]">Grade A+ · A · scor ≥ 65 · EV pozitiv</p>
          </div>
          <span className="text-xs font-bold px-2.5 py-1 rounded-full"
            style={{ background: 'rgba(255,184,48,0.20)', color: '#ffb830' }}>
            {premiumPicks.length} picks
          </span>
        </div>

        {/* Premium KPI row */}
        <div className="grid grid-cols-3 gap-2">
          <PremiumKpi label="Total picks" value={String(premiumPicks.length)} icon={<Zap className="w-3.5 h-3.5" />} color="#ffb830" />
          <PremiumKpi label="EV mediu" value={avgEv !== '—' ? `+${avgEv}%` : '—'} icon={<TrendingUp className="w-3.5 h-3.5" />} color="#00e87a" />
          <PremiumKpi label="Value Bets" value={String(valuePremium.length)} icon={<Star className="w-3.5 h-3.5" />} color="#4a9eff" />
        </div>

        {avgScore > 0 && (
          <div className="flex items-center justify-between pt-2" style={{ borderTop: '1px solid rgba(255,184,48,0.15)' }}>
            <span className="text-[10px] text-[#6b7a9e]">Scor mediu SmartBet</span>
            <span className="text-[11px] font-bold text-[#ffb830]">{avgScore} / 100</span>
          </div>
        )}
      </div>

      {/* Signals */}
      {loading ? (
        <div className="flex flex-col gap-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-40 rounded-2xl animate-pulse" style={{ background: 'var(--bp-card)' }} />
          ))}
        </div>
      ) : premiumPicks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-4">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center"
            style={{ background: 'rgba(255,184,48,0.10)', border: '1px solid rgba(255,184,48,0.20)' }}>
            <Shield className="w-8 h-8 text-[#ffb830]" />
          </div>
          <div className="text-center">
            <p className="font-bold text-[#e8eeff] mb-1">Niciun pick Premium disponibil</p>
            <p className="text-[#6b7a9e] text-sm max-w-[240px] leading-relaxed">
              Engine-ul caută oportunități de grad A+/A cu EV pozitiv. Revin în curând.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {premiumPicks.map((s, i) => (
            <SignalCard
              key={`${s.event_id}_${s.market}_${i}`}
              signal={s}
              isValue={vbSet.has(`${s.event_id}_${s.market}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const PremiumKpi: React.FC<{ label: string; value: string; icon: React.ReactNode; color: string }> = ({ label, value, icon, color }) => (
  <div
    className="rounded-xl p-2.5 flex flex-col gap-1"
    style={{ background: 'var(--bp-surface2)', border: '1px solid rgba(255,184,48,0.18)' }}
  >
    <div className="flex items-center gap-1" style={{ color }}>
      {icon}
      <span className="text-[8px] font-bold uppercase tracking-wider text-[#6b7a9e]">{label}</span>
    </div>
    <span className="text-base font-bold" style={{ color }}>{value}</span>
  </div>
);
