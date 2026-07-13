import React, { useState, useMemo } from 'react';
import { Zap, Sparkles } from 'lucide-react';
import { SignalCard } from '@/components/SignalCard';
import { EventListCard } from '@/components/EventListCard';
import { useBetPredictData } from '@/hooks/useBetPredictData';
import { useAllEvents } from '@/hooks/useAllEvents';
import { useClaudeAnalysis } from '@/hooks/useClaudeAnalysis';
import { filteredSignals, vbSetFromList, effectiveGrade, effectiveEV, effectiveScore, isVeyra } from '@/utils/filters';
import type { Signal, RawEvent, ClaudeAccumulator, PredictionRow, ClaudeVerdict } from '@/types/betpredict';

type FilterChip = 'Toate' | 'A+' | 'A' | 'B' | 'C+' | 'EV+';
type SortKey = 'Scor' | 'EV' | 'Cotă' | 'Timp';
type ViewMode = 'all' | 'curated' | 'claude';
type DateChip = 'Toate' | 'Azi' | 'Mâine' | '7 zile' | '30 zile';
type AllFilterChip = 'Toate' | 'Cu predicție' | 'Verdict AI' | 'Acumulator';
type AllSortKey = 'Oră' | 'Probabilitate';

const FILTER_CHIPS: FilterChip[] = ['Toate', 'A+', 'A', 'B', 'C+', 'EV+'];
const SORT_KEYS: SortKey[] = ['Scor', 'EV', 'Cotă', 'Timp'];
const DATE_CHIPS: DateChip[] = ['Toate', 'Azi', 'Mâine', '7 zile', '30 zile'];
const ALL_FILTER_CHIPS: AllFilterChip[] = ['Toate', 'Cu predicție', 'Verdict AI', 'Acumulator'];
const ALL_SORT_KEYS: AllSortKey[] = ['Oră', 'Probabilitate'];

function maxProbability(prediction?: PredictionRow): number {
  const mr = prediction?.markets?.match_result;
  if (!mr) return -1;
  return Math.max(mr.prob_home ?? -1, mr.prob_draw ?? -1, mr.prob_away ?? -1);
}

function applyAllFilter(
  events: RawEvent[], filter: AllFilterChip,
  predictionsByEvent: Map<string, PredictionRow>, verdictsByEvent: Map<string, ClaudeVerdict>
): RawEvent[] {
  if (filter === 'Toate') return events;
  return events.filter(e => {
    const eid = String(e.event_id);
    if (filter === 'Cu predicție') return predictionsByEvent.has(eid);
    if (filter === 'Verdict AI') return verdictsByEvent.has(eid);
    return verdictsByEvent.get(eid)?.accumulator_eligible === true;
  });
}

function applyAllSort(
  events: RawEvent[], sort: AllSortKey, predictionsByEvent: Map<string, PredictionRow>
): RawEvent[] {
  const copy = [...events];
  if (sort === 'Probabilitate') {
    return copy.sort((a, b) => maxProbability(predictionsByEvent.get(String(b.event_id))) - maxProbability(predictionsByEvent.get(String(a.event_id))));
  }
  return copy.sort((a, b) => new Date(a.event_date).getTime() - new Date(b.event_date).getTime());
}

function applyDateFilter(events: RawEvent[], chip: DateChip): RawEvent[] {
  if (chip === 'Toate') return events;
  const now = new Date();
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const today0 = startOfDay(now);
  return events.filter(e => {
    const d = new Date(e.event_date);
    if (Number.isNaN(d.getTime())) return false;
    if (chip === 'Azi') return startOfDay(d).getTime() === today0.getTime();
    if (chip === 'Mâine') {
      const tom = new Date(today0); tom.setDate(tom.getDate() + 1);
      return startOfDay(d).getTime() === tom.getTime();
    }
    const daysAhead = chip === '30 zile' ? 30 : 7;
    const rangeEnd = new Date(today0); rangeEnd.setDate(rangeEnd.getDate() + daysAhead);
    return d.getTime() >= today0.getTime() && d.getTime() < rangeEnd.getTime();
  });
}

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
  const {
    events, predictionsByEvent, teamForm, h2hByEvent, leaguesById, deepByEvent,
    loading: eventsLoading,
  } = useAllEvents();
  const { verdictsByEvent, accumulators, loading: claudeLoading } = useClaudeAnalysis();
  const vbSet = vbSetFromList(valueBets);
  const allPicks = filteredSignals(signals, vbSet);

  const [view, setView] = useState<ViewMode>('all');
  const [filter, setFilter] = useState<FilterChip>('Toate');
  const [sort, setSort] = useState<SortKey>('Timp');
  const [dateChip, setDateChip] = useState<DateChip>('Toate');
  const [allFilterChip, setAllFilterChip] = useState<AllFilterChip>('Toate');
  const [allSort, setAllSort] = useState<AllSortKey>('Oră');

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

  const sortedEvents = useMemo(() => {
    const filteredByDate = applyDateFilter(events, dateChip);
    const filtered = applyAllFilter(filteredByDate, allFilterChip, predictionsByEvent, verdictsByEvent);
    return applyAllSort(filtered, allSort, predictionsByEvent);
  }, [events, dateChip, allFilterChip, allSort, predictionsByEvent, verdictsByEvent]);

  const headerLabel = view === 'all'
    ? `${sortedEvents.length} meciuri${allFilterChip !== 'Toate' ? ` · ${allFilterChip}` : ' · fără filtre'}`
    : view === 'claude'
      ? `${accumulators.length} bilete generate · ${verdictsByEvent.size} verdicte`
      : `${engineLabel} · cotă 1.35–3.50`;
  const headerBadge = view === 'all' ? 'TOATE EVENIMENTELE' : view === 'claude' ? 'CLAUDE AI' : 'ENGINE v6 · Calibrat';
  const headerBadgeColor = view === 'all' ? '#00e87a' : view === 'claude' ? '#a78bfa' : '#4a9eff';

  if ((view === 'all' && eventsLoading) || (view === 'claude' && claudeLoading) || (view === 'curated' && loading)) {
    return <LoadingState />;
  }

  return (
    <div className="pt-4 pb-4 flex flex-col gap-3">

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-extrabold text-[#e8eeff]">⚡ Predicții</h2>
          <p className="text-[10px] text-[#6b7a9e]">{headerLabel}</p>
        </div>
        <span
          className="text-[9px] font-bold px-2.5 py-1 rounded-full"
          style={{ background: `${headerBadgeColor}22`, color: headerBadgeColor }}
        >
          {headerBadge}
        </span>
      </div>

      {/* View toggle */}
      <div className="flex gap-1.5">
        <button
          onClick={() => setView('all')}
          className="flex-1 px-2 py-2 rounded-xl text-[11px] font-bold transition-all"
          style={
            view === 'all'
              ? { background: 'linear-gradient(135deg,#00e87a,#4a9eff)', color: '#05080f' }
              : { background: 'rgba(255,255,255,0.06)', color: '#6b7a9e' }
          }
        >
          Toate evenimentele
        </button>
        <button
          onClick={() => setView('claude')}
          className="flex-1 px-2 py-2 rounded-xl text-[11px] font-bold transition-all"
          style={
            view === 'claude'
              ? { background: 'linear-gradient(135deg,#a78bfa,#4a9eff)', color: '#05080f' }
              : { background: 'rgba(255,255,255,0.06)', color: '#6b7a9e' }
          }
        >
          Acumulator AI
        </button>
        <button
          onClick={() => setView('curated')}
          className="flex-1 px-2 py-2 rounded-xl text-[11px] font-bold transition-all"
          style={
            view === 'curated'
              ? { background: 'linear-gradient(135deg,#00e87a,#4a9eff)', color: '#05080f' }
              : { background: 'rgba(255,255,255,0.06)', color: '#6b7a9e' }
          }
        >
          Predicții calificate
        </button>
      </div>

      {view === 'all' ? (
        <>
          {/* Date chips */}
          <div className="flex gap-1.5 overflow-x-auto pb-0.5 scrollbar-hide">
            {DATE_CHIPS.map(chip => (
              <button
                key={chip}
                onClick={() => setDateChip(chip)}
                className="flex-shrink-0 px-3 py-1.5 rounded-full text-[10px] font-bold transition-all"
                style={
                  dateChip === chip
                    ? { background: 'linear-gradient(135deg,#00e87a,#4a9eff)', color: '#05080f' }
                    : { background: 'rgba(255,255,255,0.06)', color: '#6b7a9e' }
                }
              >
                {chip}
              </button>
            ))}
          </div>

          {/* Filter chips */}
          <div className="flex gap-1.5 overflow-x-auto pb-0.5 scrollbar-hide">
            {ALL_FILTER_CHIPS.map(chip => (
              <button
                key={chip}
                onClick={() => setAllFilterChip(chip)}
                className="flex-shrink-0 px-3 py-1.5 rounded-full text-[10px] font-bold transition-all"
                style={
                  allFilterChip === chip
                    ? { background: 'linear-gradient(135deg,#a78bfa,#4a9eff)', color: '#05080f' }
                    : { background: 'rgba(255,255,255,0.06)', color: '#6b7a9e' }
                }
              >
                {chip}
              </button>
            ))}
          </div>

          {/* Sort toggle */}
          <div className="flex gap-0 border-b border-white/10">
            {ALL_SORT_KEYS.map(key => (
              <button
                key={key}
                onClick={() => setAllSort(key)}
                className="px-3 py-2 text-xs font-bold transition-colors border-b-2"
                style={{
                  color: allSort === key ? 'var(--bp-text)' : 'var(--bp-muted)',
                  borderBottomColor: allSort === key ? '#00e87a' : 'transparent',
                }}
              >
                {key}
              </button>
            ))}
          </div>

          {sortedEvents.length === 0 ? (
            <EmptyState text="Niciun eveniment disponibil pentru acest interval." />
          ) : (
            <div className="flex flex-col gap-3">
              {sortedEvents.map(e => {
                const eid = String(e.event_id);
                return (
                  <EventListCard
                    key={eid}
                    event={e}
                    prediction={predictionsByEvent.get(eid)}
                    homeForm={e.home_team_id != null ? teamForm.get(String(e.home_team_id)) : undefined}
                    awayForm={e.away_team_id != null ? teamForm.get(String(e.away_team_id)) : undefined}
                    h2h={h2hByEvent.get(eid)}
                    deep={deepByEvent.get(eid)}
                    leagueName={e.league_name ?? (e.league_id != null ? leaguesById.get(e.league_id)?.name : undefined)}
                    claudeVerdict={verdictsByEvent.get(eid)}
                  />
                );
              })}
            </div>
          )}
        </>
      ) : view === 'claude' ? (
        accumulators.length === 0 ? (
          <EmptyState text="Claude nu a găsit încă suficiente meciuri sigure pentru un bilet. Analiza rulează de câteva ori pe zi." />
        ) : (
          <div className="flex flex-col gap-3">
            {accumulators.map((t, i) => <AccumulatorTicketCard key={i} ticket={t} />)}
          </div>
        )
      ) : (
        <>
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
        </>
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

const AccumulatorTicketCard: React.FC<{ ticket: ClaudeAccumulator }> = ({ ticket }) => (
  <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--bp-card)', border: '1px solid #a78bfa44' }}>
    <div className="flex items-center justify-between px-3 pt-3 pb-1.5">
      <div className="flex items-center gap-1.5">
        <Sparkles className="w-3.5 h-3.5" style={{ color: '#a78bfa' }} />
        <span className="text-sm font-bold text-[#e8eeff]">{ticket.label}</span>
      </div>
      <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-[#a78bfa22]" style={{ color: '#a78bfa' }}>
        {ticket.legs.length} selecții
      </span>
    </div>

    <div className="mx-3 mb-2.5 rounded-xl p-3 flex items-center divide-x divide-white/10" style={{ background: 'var(--bp-card2)' }}>
      <div className="flex-1 flex flex-col items-center gap-0.5 px-1.5">
        <span className="text-[8px] font-bold uppercase tracking-wider text-[#6b7a9e]">COTĂ TOTALĂ</span>
        <span className="text-lg font-black text-[#e8eeff]">@{ticket.combined_odds.toFixed(2)}</span>
      </div>
      <div className="flex-1 flex flex-col items-center gap-0.5 px-1.5">
        <span className="text-[8px] font-bold uppercase tracking-wider text-[#6b7a9e]">PROB. COMBINATĂ</span>
        <span className="text-lg font-black" style={{ color: '#00e87a' }}>{ticket.combined_probability_pct.toFixed(0)}%</span>
      </div>
    </div>

    <div className="px-3 pb-3 flex flex-col gap-2">
      {ticket.legs.map((leg, i) => (
        <div key={i} className="rounded-lg p-2.5" style={{ background: 'var(--bp-surface)' }}>
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[11px] font-semibold text-[#e8eeff] truncate max-w-[65%]">
              {leg.home_team} vs {leg.away_team}
            </span>
            <span className="text-[10px] font-bold text-[#a78bfa]">@{leg.odds.toFixed(2)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-[#6b7a9e]">
              {leg.market_label} · {leg.league}{leg.bookmaker ? ` · ${leg.bookmaker}` : ''}
            </span>
            <span className="text-[10px] font-bold text-[#00e87a]">{leg.probability.toFixed(0)}%</span>
          </div>
        </div>
      ))}
    </div>
  </div>
);

const EmptyState: React.FC<{ text?: string }> = ({ text }) => (
  <div className="flex flex-col items-center justify-center py-16 gap-3">
    <div className="w-14 h-14 rounded-2xl bg-[#131c2e] flex items-center justify-center">
      <Zap className="w-6 h-6 text-[#303d57]" />
    </div>
    <p className="text-[#e8eeff] font-semibold">{text ? 'Niciun eveniment' : 'Nicio predicție calificată'}</p>
    <p className="text-[#6b7a9e] text-sm text-center max-w-[240px] leading-relaxed">
      {text ?? 'Engine v6 se actualizează orar. Revin când găsește oportunități cu EV pozitiv.'}
    </p>
  </div>
);
