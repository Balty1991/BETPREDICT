import React, { useState, useMemo } from 'react';
import { Zap, Sparkles, Ticket, TicketCheck } from 'lucide-react';
import { EventListCard } from '@/components/EventListCard';
import { useAppData } from '@/context/DataContext';
import { useSavedPredictions, verdictKey } from '@/hooks/useSavedPredictions';
import { useSavedTickets, ticketKey } from '@/hooks/useSavedTickets';
import { useBestOdds } from '@/hooks/useBestOdds';
import { pickBestMarket } from '@/utils/localAnalysis';
import { timeAgo, isQualifiedVerdict, formatDate, formatTicketProb } from '@/utils/filters';
import type { AccumulatorPeriodKey } from '@/hooks/useClaudeAnalysis';
import type { RawEvent, ClaudeAccumulator, PredictionRow, ClaudeVerdict } from '@/types/betpredict';

type ViewMode = 'all' | 'curated' | 'claude';
type DateChip = 'Toate' | 'Azi' | 'Mâine' | '7 zile' | '10 zile' | '30 zile';
type AllFilterChip = 'Toate' | 'Cu predicție' | 'Model Local' | 'Acumulator';
type AllSortKey = 'Oră' | 'Probabilitate';
type GenPeriod = '1 săptămână' | '10 zile' | '30 zile';

const DATE_CHIPS: DateChip[] = ['Toate', 'Azi', 'Mâine', '7 zile', '10 zile', '30 zile'];
const ALL_FILTER_CHIPS: AllFilterChip[] = ['Toate', 'Cu predicție', 'Model Local', 'Acumulator'];
const ALL_SORT_KEYS: AllSortKey[] = ['Oră', 'Probabilitate'];
const GEN_PERIODS: GenPeriod[] = ['1 săptămână', '10 zile', '30 zile'];
/** Cheile corespund ACCUMULATOR_PERIODS din src/claude_analysis.py — biletele sunt deja
 * pre-calculate de backend pentru fiecare fereastră, fără nicio regenerare în browser. */
const GEN_PERIOD_KEY: Record<GenPeriod, AccumulatorPeriodKey> = { '1 săptămână': '7', '10 zile': '10', '30 zile': '30' };

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
    if (filter === 'Model Local') return verdictsByEvent.has(eid);
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
    const daysAhead = chip === '30 zile' ? 30 : chip === '10 zile' ? 10 : 7;
    const rangeEnd = new Date(today0); rangeEnd.setDate(rangeEnd.getDate() + daysAhead);
    return d.getTime() >= today0.getTime() && d.getTime() < rangeEnd.getTime();
  });
}

function applyCuratedSort(
  events: RawEvent[], sort: AllSortKey, verdictsByEvent: Map<string, ClaudeVerdict>
): RawEvent[] {
  const copy = [...events];
  if (sort === 'Probabilitate') {
    return copy.sort((a, b) => (verdictsByEvent.get(String(b.event_id))?.probability ?? 0) - (verdictsByEvent.get(String(a.event_id))?.probability ?? 0));
  }
  return copy.sort((a, b) => new Date(a.event_date).getTime() - new Date(b.event_date).getTime());
}

export const PredictionsPage: React.FC = () => {
  const {
    events: {
      events, predictionsByEvent, teamForm, h2hByEvent, leaguesById, deepByEvent,
      loading: eventsLoading, updatedAt: eventsUpdatedAt,
    },
    claude: { verdictsByEvent, accumulatorsByPeriod, loading: claudeLoading, updatedAt: claudeUpdatedAt },
  } = useAppData();
  const { save: savePrediction, remove: removePrediction, isSaved } = useSavedPredictions();
  const { save: saveTicket, remove: removeTicket, isSaved: isTicketSaved } = useSavedTickets();
  const { oddsByEvent } = useBestOdds();
  const toggleSaveVerdict = (v: ClaudeVerdict) => {
    if (isSaved(v.event_id, v.market)) removePrediction(verdictKey(v.event_id, v.market));
    else savePrediction(v);
  };
  const toggleSaveTicket = (t: ClaudeAccumulator) => {
    if (isTicketSaved(t)) removeTicket(ticketKey(t.legs));
    else saveTicket(t);
  };

  const [view, setView] = useState<ViewMode>('all');
  const [dateChip, setDateChip] = useState<DateChip>('Toate');
  const [allFilterChip, setAllFilterChip] = useState<AllFilterChip>('Toate');
  const [allSort, setAllSort] = useState<AllSortKey>('Oră');
  const [curatedSort, setCuratedSort] = useState<AllSortKey>('Probabilitate');
  const [genPeriod, setGenPeriod] = useState<GenPeriod>('30 zile');

  const sortedEvents = useMemo(() => {
    const filteredByDate = applyDateFilter(events, dateChip);
    const filtered = applyAllFilter(filteredByDate, allFilterChip, predictionsByEvent, verdictsByEvent);
    return applyAllSort(filtered, allSort, predictionsByEvent);
  }, [events, dateChip, allFilterChip, allSort, predictionsByEvent, verdictsByEvent]);

  // Biletele sunt deja pre-calculate de backend pentru fiecare fereastră (7/10/30 zile) —
  // aici doar alegem setul potrivit, fără nicio recalculare în browser.
  const displayedAccumulators = accumulatorsByPeriod[GEN_PERIOD_KEY[genPeriod]];

  const curatedEvents = useMemo(() => {
    const qualified = events.filter(e => isQualifiedVerdict(verdictsByEvent.get(String(e.event_id))));
    return applyCuratedSort(qualified, curatedSort, verdictsByEvent);
  }, [events, verdictsByEvent, curatedSort]);

  const headerLabel = view === 'all'
    ? `${sortedEvents.length} meciuri${allFilterChip !== 'Toate' ? ` · ${allFilterChip}` : ' · fără filtre'}`
    : view === 'claude'
      ? `${displayedAccumulators.length} bilete generate · ${genPeriod}`
      : `${curatedEvents.length} predicții calificate · risc sigur/foarte sigur`;
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
              : { background: 'var(--bp-surface2)', color: 'var(--bp-muted)' }
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
              : { background: 'var(--bp-surface2)', color: 'var(--bp-muted)' }
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
              : { background: 'var(--bp-surface2)', color: 'var(--bp-muted)' }
          }
        >
          Predicții calificate
        </button>
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
                <ChipButton key={key} active={allSort === key} gradient="green" compact onClick={() => setAllSort(key)}>
                  {key}
                </ChipButton>
              ))}
            </FilterGroup>
          </FilterToolbar>

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
                    localPick={verdictsByEvent.get(eid) ? undefined : pickBestMarket(predictionsByEvent.get(eid), oddsByEvent.get(eid))}
                    isVerdictSaved={verdictsByEvent.get(eid) ? isSaved(eid, verdictsByEvent.get(eid)!.market) : false}
                    onToggleSaveVerdict={toggleSaveVerdict}
                  />
                );
              })}
            </div>
          )}
        </React.Fragment>
      ) : view === 'claude' ? (
        <React.Fragment key="claude">
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
                <ChipButton key={key} active={curatedSort === key} gradient="green" compact onClick={() => setCuratedSort(key)}>
                  {key}
                </ChipButton>
              ))}
            </FilterGroup>
          </FilterToolbar>

          {curatedEvents.length === 0 ? (
            <EmptyState text="Claude nu a găsit încă predicții suficient de sigure (risc sigur/foarte sigur) pentru lista calificată. Analiza rulează o dată pe zi." />
          ) : (
            <div className="flex flex-col gap-3">
              {curatedEvents.map(e => {
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
                    isVerdictSaved={verdictsByEvent.get(eid) ? isSaved(eid, verdictsByEvent.get(eid)!.market) : false}
                    onToggleSaveVerdict={toggleSaveVerdict}
                  />
                );
              })}
            </div>
          )}
        </React.Fragment>
      )}
    </div>
  );
};

const FilterToolbar: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    className="rounded-2xl p-3 flex flex-col gap-2.5"
    style={{ background: 'var(--bp-card)', border: '1px solid var(--bp-border)' }}
  >
    {children}
  </div>
);

const FilterGroup: React.FC<{ label: string; inline?: boolean; children: React.ReactNode }> = ({ label, inline, children }) => (
  <div className={inline ? 'flex items-center justify-between gap-2' : undefined}>
    <p className="text-[9px] font-bold uppercase tracking-widest text-[#6b7a9e]" style={{ marginBottom: inline ? 0 : 6 }}>
      {label}
    </p>
    <div className="flex gap-1.5 overflow-x-auto scrollbar-hide">{children}</div>
  </div>
);

const ChipButton: React.FC<{
  active: boolean; gradient: 'green' | 'purple'; compact?: boolean; onClick: () => void; children: React.ReactNode;
}> = ({ active, gradient, compact, onClick, children }) => (
  <button
    onClick={onClick}
    className={`flex-shrink-0 rounded-full font-bold transition-all ${compact ? 'px-2.5 py-1 text-[9px]' : 'px-3 py-1.5 text-[10px]'}`}
    style={
      active
        ? {
            background: gradient === 'purple' ? 'linear-gradient(135deg,#a78bfa,#4a9eff)' : 'linear-gradient(135deg,#00e87a,#4a9eff)',
            color: '#05080f',
          }
        : { background: 'var(--bp-surface2)', color: 'var(--bp-muted)' }
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

const AccumulatorTicketCard: React.FC<{
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
          ⚠ Risc foarte mare — cu {ticket.legs.length} selecții, șansa reală ca tot biletul să pice e mică
          (vezi probabilitatea combinată). E un bilet „de amuzament", nu o recomandare de bază.
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
