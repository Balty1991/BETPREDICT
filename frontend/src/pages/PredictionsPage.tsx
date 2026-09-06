import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { Zap, Sparkles, Ticket, TicketCheck, Layers, Award, Gem } from 'lucide-react';
import { EventListCard } from '@/components/EventListCard';
import { TicketGenerator } from '@/components/TicketGenerator';
import { useAppData } from '@/context/DataContext';
import { useSavedPredictions, verdictKey } from '@/hooks/useSavedPredictions';
import { useSavedTickets, ticketKey } from '@/hooks/useSavedTickets';
import { useBestOdds } from '@/hooks/useBestOdds';
import { pickBestMarket } from '@/utils/localAnalysis';
import { timeAgo, isQualifiedVerdict, formatDate, formatTicketProb, isEdgePass, isAccaLeg, ticketPassesEdge } from '@/utils/filters';
import type { AccumulatorPeriodKey } from '@/hooks/useClaudeAnalysis';
import type { RawEvent, ClaudeAccumulator, PredictionRow, ClaudeVerdict, V7Edge, DataConfidence, LocalPick, OddsBucket } from '@/types/betpredict';

type ViewMode = 'all' | 'curated' | 'claude';
type DateChip = 'Toate' | 'Azi' | 'Mâine' | '7 zile' | '10 zile' | '30 zile';
type AllFilterChip = 'Toate' | '💎 Value' | '✓ Date OK' | 'Acumulator';
type AllSortKey = 'Oră' | 'Probabilitate' | 'Date' | 'Edge';
type GenPeriod = '1 săptămână' | '10 zile' | '30 zile';

const DATE_CHIPS: DateChip[] = ['Toate', 'Azi', 'Mâine', '7 zile', '10 zile', '30 zile'];
const ALL_FILTER_CHIPS: AllFilterChip[] = ['Toate', '💎 Value', '✓ Date OK', 'Acumulator'];
const ALL_SORT_KEYS: AllSortKey[] = ['Oră', 'Probabilitate', 'Date', 'Edge'];

// Sortare COMBINATĂ multi-criteriu: fiecare criteriu selectat e normalizat 0-1
// peste setul curent și se adună. Ex: „Probabilitate" + „Date" => sus urcă
// meciurile cu probabilitate mare ȘI acoperire bună de date, în același timp.
function combinedSort(
  events: RawEvent[], keys: AllSortKey[],
  probOf: (e: RawEvent) => number,
  confOf: (e: RawEvent) => number,
  edgeOf: (e: RawEvent) => number,
): RawEvent[] {
  const active = keys.length ? keys : (['Oră'] as AllSortKey[]);
  const times = events.map(e => new Date(e.event_date).getTime()).filter(t => !Number.isNaN(t));
  const minT = times.length ? Math.min(...times) : 0;
  const maxT = times.length ? Math.max(...times) : 1;
  const span = maxT - minT || 1;
  // Edge (pp) e normalizat 0-1 peste setul curent, la fel ca ora — cel mai mare edge urcă.
  const edges = events.map(edgeOf).filter(v => Number.isFinite(v) && v > -900);
  const minE = edges.length ? Math.min(...edges) : 0;
  const maxE = edges.length ? Math.max(...edges) : 1;
  const spanE = (maxE - minE) || 1;
  const score = (e: RawEvent): number => {
    let s = 0;
    for (const k of active) {
      if (k === 'Probabilitate') s += Math.max(0, probOf(e)) / 100;
      else if (k === 'Date') s += Math.max(0, confOf(e)) / 100;
      else if (k === 'Edge') { const ev = edgeOf(e); s += (!Number.isFinite(ev) || ev <= -900) ? 0 : (ev - minE) / spanE; }
      else { // Oră: mai devreme = mai sus
        const t = new Date(e.event_date).getTime();
        s += Number.isNaN(t) ? 0 : (maxT - t) / span;
      }
    }
    return s;
  };
  return [...events].sort((a, b) => score(b) - score(a));
}
const GEN_PERIODS: GenPeriod[] = ['1 săptămână', '10 zile', '30 zile'];
/** Cheile corespund ACCUMULATOR_PERIODS din src/claude_analysis.py — biletele sunt deja
 * pre-calculate de backend pentru fiecare fereastră, fără nicio regenerare în browser. */
const GEN_PERIOD_KEY: Record<GenPeriod, AccumulatorPeriodKey> = { '1 săptămână': '7', '10 zile': '10', '30 zile': '30' };

function maxProbability(prediction?: PredictionRow): number {
  const mr = prediction?.markets?.match_result;
  if (!mr) return -1;
  return Math.max(mr.prob_home ?? -1, mr.prob_draw ?? -1, mr.prob_away ?? -1);
}

/** Doar pontul care trece Edge v8. Verdictul V7 blocat (O1.5 @1.13) e ignorat;
 *  dacă există o piață locală bună pe același meci, o arătăm pe aia. */
function passingDisplayPick(
  e: RawEvent,
  verdictsByEvent: Map<string, ClaudeVerdict>,
  predictionsByEvent: Map<string, PredictionRow>,
  oddsByEvent: Map<string, OddsBucket>,
): { verdict?: ClaudeVerdict; localPick?: LocalPick } | null {
  const eid = String(e.event_id);
  const verdict = verdictsByEvent.get(eid);
  if (isEdgePass(verdict)) return { verdict };
  const localPick = pickBestMarket(predictionsByEvent.get(eid), oddsByEvent.get(eid));
  if (isEdgePass(localPick) && localPick) return { localPick };
  return null;
}

function applyAllFilter(
  events: RawEvent[], filter: AllFilterChip,
  verdictsByEvent: Map<string, ClaudeVerdict>,
  v7Edge: Map<string, V7Edge>, dataConfidence: Map<string, DataConfidence>
): RawEvent[] {
  if (filter === 'Toate') return events;
  return events.filter(e => {
    const eid = String(e.event_id);
    if (filter === '💎 Value') {
      const edge = v7Edge.get(eid) ?? v7Edge.get(String(e.id));
      return edge?.is_value === true;
    }
    if (filter === '✓ Date OK') {
      const dc = dataConfidence.get(eid) ?? dataConfidence.get(String(e.id));
      return dc?.reliable === true;
    }
    // Acumulator
    // Acumulator Edge v8 — nu flag-ul V7 (p≥78 @1.10)
    return isAccaLeg(verdictsByEvent.get(eid));
  });
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
    const daysAhead = chip === '30 zile' ? 30 : chip === '10 zile' ? 10 : 7;
    const rangeEnd = new Date(today0); rangeEnd.setDate(rangeEnd.getDate() + daysAhead);
    return d.getTime() >= today0.getTime() && d.getTime() < rangeEnd.getTime();
  });
}

export const PredictionsPage: React.FC = () => {
  const {
    events: {
      events, predictionsByEvent, teamForm, h2hByEvent, leaguesById, deepByEvent,
      loading: eventsLoading, updatedAt: eventsUpdatedAt,
    },
    claude: { verdictsByEvent, accumulatorsByPeriod, loading: claudeLoading, updatedAt: claudeUpdatedAt },
    v7Edge, dataConfidence,
  } = useAppData();
  const { save: savePrediction, saveMany: savePredictions, remove: removePrediction, isSaved } = useSavedPredictions();
  const { save: saveTicket, remove: removeTicket, isSaved: isTicketSaved } = useSavedTickets();
  const { oddsByEvent } = useBestOdds();
  const toggleSaveVerdict = useCallback((v: ClaudeVerdict) => {
    if (isSaved(v.event_id, v.market)) removePrediction(verdictKey(v.event_id, v.market));
    else savePrediction(v);
  }, [isSaved, removePrediction, savePrediction]);
  const toggleSaveTicket = useCallback((t: ClaudeAccumulator) => {
    if (isTicketSaved(t)) removeTicket(ticketKey(t.legs));
    else saveTicket(t);
  }, [isTicketSaved, removeTicket, saveTicket]);

  const [view, setView] = useState<ViewMode>('all');
  const [dateChip, setDateChip] = useState<DateChip>('Toate');
  const [allFilterChip, setAllFilterChip] = useState<AllFilterChip>('Toate');
  const [allSort, setAllSort] = useState<AllSortKey[]>(['Oră']);
  const [curatedSort, setCuratedSort] = useState<AllSortKey[]>(['Probabilitate']);
  // Toggle multi-select: adaugă/scoate un criteriu; păstrează minim unul activ.
  const toggleSort = (cur: AllSortKey[], set: (v: AllSortKey[]) => void, key: AllSortKey) => {
    if (cur.includes(key)) { const next = cur.filter(k => k !== key); set(next.length ? next : cur); }
    else set([...cur, key]);
  };
  const dcScore = (e: RawEvent): number =>
    (dataConfidence.get(String(e.event_id)) ?? dataConfidence.get(String(e.id)))?.score ?? 0;
  // Edge (pp) al pontului afișat: întâi Edge Real v7, apoi edge-ul din verdict.
  const edgeScore = (e: RawEvent): number => {
    const eid = String(e.event_id);
    const ve = v7Edge.get(eid) ?? v7Edge.get(String(e.id));
    if (ve?.edge_pp != null) return ve.edge_pp;
    return verdictsByEvent.get(eid)?.edge_pp ?? -999;
  };
  const [genPeriod, setGenPeriod] = useState<GenPeriod>('30 zile');

  // Doar ponturi Edge v8. Volumul V7 (Over 1.5 @1.13, favorite @1.14) nu apare.
  const eventsWithSignal = useMemo(() => events.filter(e =>
    passingDisplayPick(e, verdictsByEvent, predictionsByEvent, oddsByEvent) != null
  ), [events, predictionsByEvent, verdictsByEvent, oddsByEvent]);

  // Auto-tracking: salvează automat toate predicțiile (verdictele) cu cotă validă,
  // ca să nu fie nevoie de salvare manuală per card. Rulează o dată per set de date;
  // cele deja salvate sunt ignorate. La reîncărcare re-adaugă orice predicție nouă.
  const autoSaveKeyRef = useRef<string>('');
  useEffect(() => {
    if (verdictsByEvent.size === 0) return;
    const key = `${verdictsByEvent.size}:${claudeUpdatedAt ?? ''}`;
    if (autoSaveKeyRef.current === key) return;
    autoSaveKeyRef.current = key;
    const toSave: ClaudeVerdict[] = [];
    verdictsByEvent.forEach(v => {
      if (isEdgePass(v)) toSave.push(v);
    });
    if (toSave.length) savePredictions(toSave);
  }, [verdictsByEvent, claudeUpdatedAt, savePredictions]);

  const sortedEvents = useMemo(() => {
    const filteredByDate = applyDateFilter(eventsWithSignal, dateChip);
    const filtered = applyAllFilter(filteredByDate, allFilterChip, verdictsByEvent, v7Edge, dataConfidence);
    // În modul Value, sortăm după EV (cel mai mare edge primul) — direct util pentru bilete.
    if (allFilterChip === '💎 Value') {
      return [...filtered].sort((a, b) => {
        const ea = v7Edge.get(String(a.event_id)) ?? v7Edge.get(String(a.id));
        const eb = v7Edge.get(String(b.event_id)) ?? v7Edge.get(String(b.id));
        return (eb?.ev_pct ?? -99) - (ea?.ev_pct ?? -99);
      });
    }
    return combinedSort(filtered, allSort,
      e => maxProbability(predictionsByEvent.get(String(e.event_id))),
      dcScore, edgeScore);
  }, [eventsWithSignal, dateChip, allFilterChip, allSort, predictionsByEvent, verdictsByEvent, v7Edge, dataConfidence]);

  // Paginare: randăm doar câteva zeci de carduri deodată (nu toate cele ~1700),
  // altfel randarea + logica per-card devine foarte lentă pe telefon.
  const PAGE_SIZE = 25;
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  React.useEffect(() => { setVisibleCount(PAGE_SIZE); }, [dateChip, allFilterChip, allSort, view]);
  const visibleEvents = useMemo(() => sortedEvents.slice(0, visibleCount), [sortedEvents, visibleCount]);

  // Biletele sunt deja pre-calculate de backend pentru fiecare fereastră (7/10/30 zile) —
  // aici doar alegem setul potrivit, fără nicio recalculare în browser.
  const displayedAccumulators = useMemo(
    () => (accumulatorsByPeriod[GEN_PERIOD_KEY[genPeriod]] ?? []).filter(ticketPassesEdge),
    [accumulatorsByPeriod, genPeriod],
  );

  // „Top" = cu adevărat selectiv: verdict sigur/foarte sigur ȘI date fiabile
  // (fără meciurile cu date insuficiente, care umflau lista la ~1500).
  const curatedEvents = useMemo(() => {
    const qualified = events.filter(e => {
      if (!isQualifiedVerdict(verdictsByEvent.get(String(e.event_id)))) return false;
      const dc = dataConfidence.get(String(e.event_id)) ?? dataConfidence.get(String(e.id));
      return dc?.reliable === true;
    });
    return combinedSort(qualified, curatedSort,
      e => verdictsByEvent.get(String(e.event_id))?.probability ?? 0,
      dcScore, edgeScore);
  }, [events, verdictsByEvent, curatedSort, dataConfidence, v7Edge]);
  // Dacă nu există verdict calificat, Top nu rămâne o pagină moartă: arătăm
  // strict analize locale pentru revizuire. Ele sunt etichetate explicit și
  // NU devin selecții calificate sau bilete automate.
  const topReviewEvents = useMemo(() => {
    const reviewable = eventsWithSignal.filter(e => {
      const pick = passingDisplayPick(e, verdictsByEvent, predictionsByEvent, oddsByEvent);
      return !!pick?.localPick && !pick.verdict;
    });
    return combinedSort(reviewable, curatedSort,
      e => maxProbability(predictionsByEvent.get(String(e.event_id))),
      dcScore, edgeScore);
  }, [eventsWithSignal, predictionsByEvent, curatedSort, dataConfidence, v7Edge, oddsByEvent, verdictsByEvent]);
  const topUsesReviewFallback = curatedEvents.length === 0 && topReviewEvents.length > 0;
  const displayedTopEvents = topUsesReviewFallback ? topReviewEvents : curatedEvents;
  const visibleTopEvents = useMemo(() => displayedTopEvents.slice(0, visibleCount), [displayedTopEvents, visibleCount]);

  const headerLabel = view === 'all'
    ? `${sortedEvents.length} predicții Edge v8${allFilterChip !== 'Toate' ? ` · ${allFilterChip}` : ''}`
    : view === 'claude'
      ? `${displayedAccumulators.length} bilete generate · ${genPeriod}`
      : topUsesReviewFallback
      ? `${topReviewEvents.length} analize locale · Edge v8`
      : `${curatedEvents.length} predicții calificate · Edge v8 (1.50–3.30)`;
  const headerUpdatedAt = view === 'all' ? eventsUpdatedAt : claudeUpdatedAt;
  const headerBadge = `⟳ ${timeAgo(headerUpdatedAt)}`;
  const headerBadgeColor = view === 'all' ? '#00e87a' : view === 'claude' ? '#a78bfa' : '#4a9eff';

  if ((view === 'all' && eventsLoading) || ((view === 'claude' || view === 'curated') && claudeLoading)) {
    return <LoadingState />;
  }

  return (
    <div className="pt-4 pb-4 flex flex-col gap-3">

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-extrabold text-[#e8eeff]">⚡ Predicții · Edge v8</h2>
          <p className="text-[10px] text-[#6b7a9e]">{headerLabel}</p>
        </div>
        <span
          className="text-[9px] font-bold px-2.5 py-1 rounded-full"
          style={{ background: `${headerBadgeColor}22`, color: headerBadgeColor }}
        >
          {headerBadge}
        </span>
      </div>

      <div className="rounded-2xl px-3.5 py-3 text-[11px] leading-relaxed" style={{ background: '#00e87a12', border: '1px solid #00e87a44', color: 'var(--bp-text)' }}>
        <strong style={{ color: '#00e87a' }}>Doar predicții Edge v8.</strong>{' '}
        Fereastră 1.50–3.30, edge ≥4%, Over 1.5 doar ≥1.68. Volumul V7 e ascuns, nu e marcat.
        Acca 50×/100× = loterie, miză 4–10 lei din 1000.
      </div>

      {/* View toggle — segmented control premium cu contoare + acces Sharp */}
      <div
        className="flex gap-1 p-1 rounded-2xl"
        style={{ background: 'var(--bp-surface2)', border: '1px solid var(--bp-border)', boxShadow: 'inset 0 1px 3px rgba(0,0,0,.3)' }}
      >
        <SegTab active={view === 'all'} onClick={() => setView('all')} icon={<Zap className="w-4 h-4" />} label="Meciuri" count={sortedEvents.length} accent="#00e87a" />
        <SegTab active={view === 'claude'} onClick={() => setView('claude')} icon={<Layers className="w-4 h-4" />} label="Bilete" count={displayedAccumulators.length} accent="#a78bfa" />
        <SegTab active={view === 'curated'} onClick={() => setView('curated')} icon={<Award className="w-4 h-4" />} label="Top" count={curatedEvents.length} accent="#4a9eff" />
        <SegTab active={false} onClick={() => window.dispatchEvent(new CustomEvent('betpredict:open-sharp'))} icon={<Gem className="w-4 h-4" />} label="Sharp" accent="#f5a623" />
      </div>

      {view === 'all' ? (
        <React.Fragment key="all">
          <FilterToolbar>
            <FilterGroup label="Perioadă">
              {DATE_CHIPS.map(chip => (
                <ChipButton key={chip} active={dateChip === chip} gradient="green" onClick={() => setDateChip(chip)}>
                  {chip}
                </ChipButton>
              ))}
            </FilterGroup>

            <FilterGroup label="Filtru">
              {ALL_FILTER_CHIPS.map(chip => (
                <ChipButton key={chip} active={allFilterChip === chip} gradient="purple" onClick={() => setAllFilterChip(chip)}>
                  {chip}
                </ChipButton>
              ))}
            </FilterGroup>

            <FilterGroup label="Sortare" inline>
              {ALL_SORT_KEYS.map(key => (
                <ChipButton key={key} active={allSort.includes(key)} gradient="green" compact onClick={() => toggleSort(allSort, setAllSort, key)}>
                  {key}
                </ChipButton>
              ))}
            </FilterGroup>
          </FilterToolbar>

          {sortedEvents.length === 0 ? (
            <EmptyState text="Nicio predicție Edge v8 în acest interval. Cotele de volum (Over 1.5 sub 1.68, favorite sub 1.50) sunt ascunse." />
          ) : (
            <div className="flex flex-col gap-3">
              {visibleEvents.map(e => {
                const eid = String(e.event_id);
                const pick = passingDisplayPick(e, verdictsByEvent, predictionsByEvent, oddsByEvent);
                if (!pick) return null;
                const ve = v7Edge.get(eid) ?? v7Edge.get(String(e.id));
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
                    claudeVerdict={pick.verdict}
                    localPick={pick.localPick}
                    isVerdictSaved={pick.verdict ? isSaved(eid, pick.verdict.market) : false}
                    onToggleSaveVerdict={toggleSaveVerdict}
                    v7Edge={ve && isEdgePass(ve) ? ve : undefined}
                    dataConf={dataConfidence.get(eid) ?? dataConfidence.get(String(e.id))}
                  />
                );
              })}
              {visibleCount < sortedEvents.length && (
                <button
                  onClick={() => setVisibleCount(c => c + PAGE_SIZE)}
                  className="mx-auto mt-1 mb-2 px-5 py-2.5 rounded-full text-[12px] font-bold transition-all"
                  style={{ background: 'var(--bp-surface2)', color: 'var(--bp-text)', border: '1px solid var(--bp-border)' }}
                >
                  Arată mai multe · {sortedEvents.length - visibleCount} rămase
                </button>
              )}
            </div>
          )}
        </React.Fragment>
      ) : view === 'claude' ? (
        <React.Fragment key="claude">
          <TicketGenerator onSave={toggleSaveTicket} isSaved={isTicketSaved} />

          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#8a97b8] mt-1 -mb-1">Bilete recomandate</p>
          <FilterToolbar>
            <FilterGroup label="Perioadă de generare" inline>
              {GEN_PERIODS.map(p => (
                <ChipButton key={p} active={genPeriod === p} gradient="purple" compact onClick={() => setGenPeriod(p)}>
                  {p}
                </ChipButton>
              ))}
            </FilterGroup>
          </FilterToolbar>

          {displayedAccumulators.length === 0 ? (
            <EmptyState text="Nu sunt destule meciuri sigure în această perioadă pentru un bilet. Încearcă o fereastră mai lungă." />
          ) : (
            <div className="flex flex-col gap-3">
              {displayedAccumulators.map((t, i) => (
                <AccumulatorTicketCard key={i} ticket={t} isPlaced={isTicketSaved(t)} onTogglePlace={() => toggleSaveTicket(t)} />
              ))}
            </div>
          )}
        </React.Fragment>
      ) : (
        <React.Fragment key="curated">
          <FilterToolbar>
            <FilterGroup label="Sortare" inline>
              {ALL_SORT_KEYS.map(key => (
                <ChipButton key={key} active={curatedSort.includes(key)} gradient="green" compact onClick={() => toggleSort(curatedSort, setCuratedSort, key)}>
                  {key}
                </ChipButton>
              ))}
            </FilterGroup>
          </FilterToolbar>

          {displayedTopEvents.length === 0 ? (
            <EmptyState text="Nicio predicție Edge v8 pentru Top în acest interval." />
          ) : (
            <div className="flex flex-col gap-3">
              {topUsesReviewFallback && (
                <div className="rounded-2xl px-4 py-3 text-xs leading-relaxed" style={{ background: '#00e87a16', border: '1px solid #00e87a55', color: 'var(--bp-text)' }}>
                  <strong style={{ color: '#00e87a' }}>Analize locale Edge v8.</strong>{' '}
                  Nu există încă verdicte calificate; astea sunt piețele locale din fereastra 1.50–3.30.
                </div>
              )}
              {visibleTopEvents.map(e => {
                const eid = String(e.event_id);
                const pick = passingDisplayPick(e, verdictsByEvent, predictionsByEvent, oddsByEvent);
                if (!pick) return null;
                const ve = v7Edge.get(eid) ?? v7Edge.get(String(e.id));
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
                    claudeVerdict={pick.verdict}
                    localPick={pick.localPick}
                    isVerdictSaved={pick.verdict ? isSaved(eid, pick.verdict.market) : false}
                    onToggleSaveVerdict={toggleSaveVerdict}
                    v7Edge={ve && isEdgePass(ve) ? ve : undefined}
                    dataConf={dataConfidence.get(eid) ?? dataConfidence.get(String(e.id))}
                  />
                );
              })}
              {visibleCount < displayedTopEvents.length && (
                <button
                  onClick={() => setVisibleCount(c => c + PAGE_SIZE)}
                  className="mx-auto mt-1 mb-2 px-5 py-2.5 rounded-full text-[12px] font-bold transition-all"
                  style={{ background: 'var(--bp-surface2)', color: 'var(--bp-text)', border: '1px solid var(--bp-border)' }}
                >
                  Arată mai multe · {displayedTopEvents.length - visibleCount} rămase
                </button>
              )}
            </div>
          )}
        </React.Fragment>
      )}
    </div>
  );
};

const SegTab: React.FC<{
  active: boolean; onClick: () => void; icon: React.ReactNode; label: string; count?: number; accent: string;
}> = ({ active, onClick, icon, label, count, accent }) => (
  <button
    onClick={onClick}
    className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl font-bold transition-all duration-200 active:scale-[0.97]"
    style={
      active
        ? { background: `linear-gradient(135deg, ${accent}, ${accent}bb)`, color: '#05080f', boxShadow: `0 6px 18px -6px ${accent}` }
        : { background: 'transparent', color: 'var(--bp-muted)' }
    }
  >
    <span style={{ opacity: active ? 1 : 0.7 }}>{icon}</span>
    <span className="text-[12.5px] tracking-tight">{label}</span>
    {count != null && count > 0 && (
      <span
        className="text-[9.5px] font-black px-1.5 py-0.5 rounded-full leading-none tabular-nums"
        style={active ? { background: 'rgba(5,8,15,.22)', color: '#05080f' } : { background: 'var(--bp-surface)', color: accent }}
      >
        {count > 999 ? `${(count / 1000).toFixed(1)}k` : count}
      </span>
    )}
  </button>
);

const FilterToolbar: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    className="rounded-2xl px-3 py-2.5 flex flex-col gap-2"
    style={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border)' }}
  >
    {children}
  </div>
);

// Etichetă scurtă la stânga, chip-urile inline la dreapta — compact, o singură linie pe grup.
const FilterGroup: React.FC<{ label: string; inline?: boolean; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-center gap-2.5">
    <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#8a97b8] flex-shrink-0 w-[52px]">
      {label}
    </p>
    <div className="flex gap-2 overflow-x-auto scrollbar-hide">{children}</div>
  </div>
);

const ChipButton: React.FC<{
  active: boolean; gradient: 'green' | 'purple'; compact?: boolean; onClick: () => void; children: React.ReactNode;
}> = ({ active, gradient, compact, onClick, children }) => (
  <button
    onClick={onClick}
    className={`flex-shrink-0 rounded-full font-bold transition-all duration-200 border ${compact ? 'px-3 py-1.5 text-[11px]' : 'px-3.5 py-1.5 text-[11px]'}`}
    style={
      active
        ? {
            background: gradient === 'purple' ? 'linear-gradient(135deg,#a78bfa,#7c6cf0)' : 'linear-gradient(135deg,#00e87a,#12b981)',
            color: '#05080f',
            borderColor: 'transparent',
          }
        : { background: 'var(--bp-surface)', color: 'var(--bp-text)', borderColor: 'var(--bp-border)' }
    }
  >
    {children}
  </button>
);

const LoadingState: React.FC = () => (
  <div className="flex flex-col items-center justify-center py-20 gap-3">
    <div className="w-8 h-8 border-2 border-[#00e87a] border-t-transparent rounded-full animate-spin" />
    <p className="text-[#6b7a9e] text-sm">Se încarcă predicțiile...</p>
  </div>
);

const LEG_PREVIEW_COUNT = 6;

export const AccumulatorTicketCard: React.FC<{
  ticket: ClaudeAccumulator; isPlaced?: boolean; onTogglePlace?: () => void;
}> = ({ ticket, isPlaced, onTogglePlace }) => {
  const [expanded, setExpanded] = useState(false);
  const isLongshot = ticket.risk_level === 'longshot';
  const accent = isLongshot ? '#f5a623' : '#a78bfa';
  const visibleLegs = expanded ? ticket.legs : ticket.legs.slice(0, LEG_PREVIEW_COUNT);
  const hasMore = ticket.legs.length > LEG_PREVIEW_COUNT;

  return (
    <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--bp-card)', border: `1px solid ${accent}44` }}>
      <div className="flex items-center justify-between px-3 pt-3 pb-1.5">
        <div className="flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5" style={{ color: accent }} />
          <span className="text-sm font-bold text-[#e8eeff]">{ticket.label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {ticket.claude_highlight && (
            <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-[#00e87a22] text-[#00e87a]">
              ★ Recomandat de Claude
            </span>
          )}
          <span className="text-[9px] font-bold px-2 py-0.5 rounded-full" style={{ background: `${accent}22`, color: accent }}>
            {ticket.legs.length} selecții
          </span>
        </div>
      </div>

      {isLongshot && (
        <div className="mx-3 mb-2 rounded-lg px-2.5 py-1.5 text-[9px] leading-relaxed" style={{ background: '#f5a62314', color: '#f5a623' }}>
          LOTERIE Edge v8 — miză 0.4–1% din bancă (4–10 lei din 1000). Un picior greșit anulează tot. Nu e piramidă @1.14.
        </div>
      )}

      {ticket.claude_concern && (
        <div className="mx-3 mb-2 rounded-lg px-2.5 py-1.5 text-[9px] leading-relaxed flex gap-1.5" style={{ background: '#ff5c7a14', color: '#ff5c7a' }}>
          <span className="flex-shrink-0">⚠ Claude a semnalat:</span>
          <span>{ticket.claude_concern}</span>
        </div>
      )}

      <div className="mx-3 mb-2.5 rounded-xl p-3 flex items-center divide-x divide-white/10" style={{ background: 'var(--bp-card2)' }}>
        <div className="flex-1 flex flex-col items-center gap-0.5 px-1.5">
          <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">COTĂ TOTALĂ</span>
          <span className="text-lg font-black text-[#e8eeff]">@{ticket.combined_odds.toFixed(2)}</span>
        </div>
        <div className="flex-1 flex flex-col items-center gap-0.5 px-1.5">
          <span className="text-[9px] font-bold uppercase tracking-wider text-[#6b7a9e]">PROB. COMBINATĂ</span>
          <span className="text-lg font-black" style={{ color: isLongshot ? '#f5a623' : '#00e87a' }}>
            {formatTicketProb(ticket.combined_probability_pct)}
          </span>
        </div>
      </div>

      {(ticket.avg_edge_pp != null || ticket.n_sharp_confirmed != null) && (
        <div className="mx-3 mb-2.5 flex items-center gap-2 flex-wrap">
          {ticket.avg_edge_pp != null && (
            <span
              className="text-[9px] font-bold px-2 py-0.5 rounded-full"
              style={{ background: ticket.avg_edge_pp > 0 ? '#00e87a1f' : '#6b7a9e1f', color: ticket.avg_edge_pp > 0 ? '#00e87a' : '#6b7a9e' }}
            >
              Edge mediu {ticket.avg_edge_pp > 0 ? '+' : ''}{ticket.avg_edge_pp.toFixed(1)}pp
            </span>
          )}
          {ticket.n_sharp_confirmed != null && ticket.n_sharp_confirmed > 0 && (
            <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-[#00e87a1f] text-[#00e87a]">
              ✓ {ticket.n_sharp_confirmed} confirmate sharp
            </span>
          )}
          <span className="text-[9px] font-bold px-2 py-0.5 rounded-full" style={{ background: '#a78bfa1f', color: '#a78bfa' }}>
            Probabilitate reală (ancorată pe piață)
          </span>
        </div>
      )}

      {onTogglePlace && (
        <div className="mx-3 mb-2.5">
          <button
            onClick={onTogglePlace}
            className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-bold transition-colors"
            style={
              isPlaced
                ? { background: '#00e87a22', color: '#00e87a' }
                : { background: `${accent}22`, color: accent }
            }
          >
            {isPlaced ? <TicketCheck className="w-3.5 h-3.5" /> : <Ticket className="w-3.5 h-3.5" />}
            {isPlaced ? 'Bilet plasat — monitorizat în Statistici' : 'Plasează biletul'}
          </button>
        </div>
      )}

      <div className="px-3 pb-3 flex flex-col gap-2">
        {visibleLegs.map((leg, i) => (
          <div key={i} className="rounded-lg p-2.5" style={{ background: 'var(--bp-surface)' }}>
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-[11px] font-semibold text-[#e8eeff] truncate max-w-[65%]">
                {leg.home_team} vs {leg.away_team}
              </span>
              <span className="text-[10px] font-bold flex-shrink-0" style={{ color: accent }}>@{leg.odds.toFixed(2)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-[#6b7a9e] truncate max-w-[75%]">
                {leg.market_label} · {leg.league}{leg.bookmaker ? ` · ${leg.bookmaker}` : ''}
              </span>
              <span className="text-[10px] font-bold text-[#00e87a] flex-shrink-0">{leg.probability.toFixed(0)}%</span>
            </div>
            {leg.event_date && (
              <div className="text-[9px] text-[#4a9eff] mt-0.5">{formatDate(leg.event_date)}</div>
            )}
            {leg.rationale && (
              <div className="text-[9px] text-[#8a97b8] mt-0.5 leading-relaxed">{leg.rationale}</div>
            )}
          </div>
        ))}
        {hasMore && (
          <button
            onClick={() => setExpanded(v => !v)}
            className="text-[10px] text-[#6b7a9e] py-1.5 text-center"
          >
            {expanded ? 'Arată mai puțin' : `Arată toate (${ticket.legs.length})`}
          </button>
        )}
      </div>
    </div>
  );
};

const EmptyState: React.FC<{ text: string }> = ({ text }) => (
  <div className="flex flex-col items-center justify-center py-16 gap-3">
    <div className="w-14 h-14 rounded-2xl bg-[#131c2e] flex items-center justify-center">
      <Zap className="w-6 h-6 text-[#303d57]" />
    </div>
    <p className="text-[#e8eeff] font-semibold">Niciun rezultat</p>
    <p className="text-[#6b7a9e] text-sm text-center max-w-[240px] leading-relaxed">{text}</p>
  </div>
);
