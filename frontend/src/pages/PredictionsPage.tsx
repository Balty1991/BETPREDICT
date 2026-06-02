import React, { useState, useMemo } from 'react';
import { Zap } from 'lucide-react';
import { SignalCard } from '@/components/SignalCard';
import { useBetPredictData } from '@/hooks/useBetPredictData';
import { filteredSignals, vbSetFromList, effectiveGrade, effectiveEV, effectiveScore, isVeyra } from '@/utils/filters';
import type { Signal } from '@/types/betpredict';

type FilterChip = 'Toate' | 'A+' | 'A' | 'B' | 'C+' | 'EV+';
type SortKey = 'Scor' | 'EV' | 'Cotă' | 'Timp';

const FILTER_CHIPS: FilterChip[] = ['Toate', 'A+', 'A', 'B', 'C+', 'EV+'];
const SORT_KEYS: SortKey[] = ['Scor', 'EV', 'Cotă', 'Timp'];

function applyFilter(picks: Signal[], filter: FilterChip): Signal[] {
  if (filter === 'Toate') return picks;
  if (filter === 'EV+') return picks.filter(s => effectiveEV(s) > 0.05);
  if (filter === 'C+') return picks.filter(s => ['A+', 'A', 'B', 'C'].includes(effectiveGrade(s)));
  return picks.filter(s => effectiveGrade(s) === filter);
}

function applySort(picks: Signal[], sort: SortKey): Signal[] {
  const copy = [...picks];
  if (sort === 'Scor') return copy.sort((a, b) => effectiveScore(b) - effectiveScore(a));
  if (sort === 'EV') return copy.sort((a, b) => effectiveEV(b) - effectiveEV(a));
  if (sort === 'Cotă') return copy.sort((a, b) => (b.odds ?? 0) - (a.odds ?? 0));
  return copy.sort((a, b) => new Date(a.event_date).getTime() - new Date(b.event_date).getTime());
}

export const PredictionsPage: React.FC = () => {
  const { signals, valueBets, loading } = useBetPredictData();
  const vbSet = vbSetFromList(valueBets);
  const allPicks = filteredSignals(signals, vbSet);

  const [filter, setFilter] = useState<FilterChip>('Toate');
  const [sort, setSort] = useState<SortKey>('Timp');

  const picks = useMemo(() => applySort(applyFilter(allPicks, filter), sort), [allPicks, filter, sort]);

  const veyraCount = allPicks.filter(s => isVeyra(s)).length;
  const engineLabel = veyraCount > 0
    ? `VEYRA v5: ${veyraCount} · Engine v6: ${allPicks.length - veyraCount}`
    : `Engine v6: ${allPicks.length}`;

  const signalsByEvent = useMemo(() => {
    const map = new Map<string | number, Signal[]>();
    for (const s of signals) {
      const arr = map.get(s.event_id) ?? [];
      arr.push(s);
      map.set(s.event_id, arr);
    }
    return map;
  }, [signals]);

  if (loading) return <LoadingState />;

  return (
    <div className="pt-4 pb-4 flex flex-col gap-3">

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-extrabold text-[#e8eeff]">⚡ Predicții</h2>
          <p className="text-[10px] text-[#6b7a9e]">{engineLabel} · cotă 1.35–3.50</p>
        </div>
        <span className="text-[9px] font-bold px-2.5 py-1 rounded-full" style={{ background: '#4a9eff22', color: '#4a9eff' }}>
          ENGINE v6 · Calibrat
        </span>
      </div>

      {/* Filter chips */}
      <div className="flex gap-1.5 overflow-x-auto pb-0.5 scrollbar-hide">
        {FILTER_CHIPS.map(chip => (
          <button
            key={chip}
            onClick={() => setFilter(chip)}
            className="flex-shrink-0 px-3 py-1.5 rounded-full text-[10px] font-bold transition-all"
            style={
              filter === chip
                ? { background: 'linear-gradient(135deg,#00e87a,#4a9eff)', color: '#05080f' }
                : { background: 'rgba(255,255,255,0.06)', color: '#6b7a9e' }
            }
          >
            {chip}
          </button>
        ))}
      </div>

      {/* Sort tabs */}
      <div className="flex gap-0 border-b border-white/10">
        {SORT_KEYS.map(key => (
          <button
            key={key}
            onClick={() => setSort(key)}
            className="px-3 py-2 text-xs font-bold transition-colors border-b-2"
            style={{
              color: sort === key ? 'var(--bp-text)' : 'var(--bp-muted)',
              borderBottomColor: sort === key ? '#00e87a' : 'transparent',
            }}
          >
            {key}
          </button>
        ))}
      </div>

      {picks.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="flex flex-col gap-3">
          {picks.map((s, i) => (
            <SignalCard
              key={`${s.event_id}_${s.market}_${i}`}
              signal={s}
              isValue={vbSet.has(`${s.event_id}_${s.market}`)}
              allSignalsForEvent={signalsByEvent.get(s.event_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const LoadingState: React.FC = () => (
  <div className="flex flex-col items-center justify-center py-20 gap-3">
    <div className="w-8 h-8 border-2 border-[#00e87a] border-t-transparent rounded-full animate-spin" />
    <p className="text-[#6b7a9e] text-sm">Se încarcă predicțiile...</p>
  </div>
);

const EmptyState: React.FC = () => (
  <div className="flex flex-col items-center justify-center py-16 gap-3">
    <div className="w-14 h-14 rounded-2xl bg-[#131c2e] flex items-center justify-center">
      <Zap className="w-6 h-6 text-[#303d57]" />
    </div>
    <p className="text-[#e8eeff] font-semibold">Nicio predicție calificată</p>
    <p className="text-[#6b7a9e] text-sm text-center max-w-[240px] leading-relaxed">
      Engine v6 se actualizează orar. Revin când găsește oportunități cu EV pozitiv.
    </p>
  </div>
);
