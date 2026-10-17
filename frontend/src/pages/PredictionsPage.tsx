import { SupersocialList } from '@/components/SupersocialList';
import { useCardMode, setCardMode } from '@/lib/cardMode';
import { Fragment, useCallback, useMemo, useRef, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import { SlidersHorizontal, Search, CalendarDays } from 'lucide-react';
import { useDay, useDays } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadDayIndex } from '@/lib/data';
import { useStore } from '@/lib/store';
import { addDays, todayRo, longDay, roDay, roDateTime } from '@/lib/format';
import { MARKET_GROUPS, SAFE_GOALS, isFinished, isStarted, passesSafeGoal, safeGoalKind, superbetPrice } from '@/lib/markets';
import { Segmented, Loading, Empty, Notice, Sheet, InfoTip } from '@/components/kit';
import { confidence, isHighSafety, safetyOf } from '@/lib/ui';
import { isRecommended, REC } from '@/lib/rules';
import { MatchCard, PredLine, sbEdge } from '@/components/MatchCard';
import { LoadMore } from '@/components/LoadMore';
import type { Match, Prediction } from '@/lib/types';
import { cn } from '@/lib/utils';

type Sort = 'time' | 'p' | 'ev' | 'conf' | 'safety';
type View = 'match' | 'flat';
type Status = 'all' | 'upcoming' | 'done';
type Slot = 'all' | 'am' | 'pm' | 'eve';
type Goal = 'off' | 'o15' | 'ht' | 'both';

const hourRo = (iso: string) => Number(new Intl.DateTimeFormat('ro-RO', { timeZone: 'Europe/Bucharest', hour: '2-digit', hour12: false }).format(new Date(iso)));

const wdFmt = new Intl.DateTimeFormat('ro-RO', { weekday: 'short', timeZone: 'UTC' });
const dmFmt = new Intl.DateTimeFormat('ro-RO', { day: 'numeric', month: 'short', timeZone: 'UTC' });
function dayPill(d: string, today: string): [string, string] {
  const dt = new Date(`${d}T12:00:00Z`);
  const top = d === today ? 'Azi' : d === addDays(today, 1) ? 'Mâine' : d === addDays(today, -1) ? 'Ieri' : wdFmt.format(dt).replace('.', '');
  return [top, dmFmt.format(dt).replace('.', '')];
}

function DayHeader({ d, today }: { d: string; today: string }) {
  return (
    <h2 className="col-span-full -mb-1 mt-2 flex items-baseline gap-2 first:mt-0">
      <span className="text-[17px] font-extrabold">{d === today ? 'Azi' : longDay(d)}</span>
      {d === today && <span className="text-xs font-semibold text-muted-foreground">{longDay(d)}</span>}
    </h2>
  );
}

/** Un rând de filtru cu explicație: ce face, într-o propoziție. */
function FilterToggle({ on, onClick, title, desc }: { on: boolean; onClick: () => void; title: string; desc: string }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={cn('press flex w-full items-center gap-3 rounded-2xl border px-3 py-2.5 text-left', on ? 'border-primary/60 bg-primary/10' : 'bg-card')}>
      <span className="min-w-0 flex-1"><span className={cn('block text-sm font-bold', on && 'text-primary')}>{title}</span><span className="block text-xs text-muted-foreground">{desc}</span></span>
      <span aria-hidden className={cn('relative h-6 w-10 shrink-0 rounded-full transition-colors', on ? 'bg-primary' : 'bg-muted')}><span className={cn('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform', on ? 'translate-x-[18px]' : 'translate-x-0.5')} /></span>
    </button>
  );
}

function FilterGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-[11px] font-extrabold uppercase tracking-wider text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

/** true după ce utilizatorul derulează în jos (dincolo de 220px); false la derulare în sus. */
export default function PredictionsPage() {
  const [sp, setSp] = useSearchParams();
  const today = todayRo();
  const ALL = 'toate';
  const rawDate = sp.get('zi') || today;
  const isAll = rawDate === ALL;
  const date = isAll ? today : rawDate;
  const setDate = (d: string) => { sp.set('zi', d); setSp(sp, { replace: true }); };
  const settingsMin = useStore((s) => s.settings.minOdds);
  const index = useAsync(() => loadDayIndex(settingsMin), [settingsMin]);
  const day = useDay(date);
  const allDates = useMemo(() => (isAll ? (index.data?.days ?? []).filter((d) => d >= today).sort() : []), [isAll, index.data, today]);
  const multi = useDays(allDates);

  const [group, setGroup] = useState('all');
  const [minP, setMinP] = useState(0.5);
  const [minOdds, setMinOdds] = useState(settingsMin);
  const [maxOdds, setMaxOdds] = useState(10);
  const [onlyValue, setOnlyValue] = useState(false);
  const [onlyRec, setOnlyRec] = useState(false);
  const [onlySafe, setOnlySafe] = useState(false);
  const [ssMode, setSsMode] = useState(false);
  const [onlySbBeats, setOnlySbBeats] = useState(false); // Superbet > piață cu ≥2%
  const [onlyWithOdds, setOnlyWithOdds] = useState(true); // implicit: doar selecții cu cotă reală
  const [showCheap, setShowCheap] = useState(false); // și selecțiile sub cota minimă din Setări (ex. 80%+ la 1.05–1.14)
  const [grades, setGrades] = useState<string[]>([]);
  const [league, setLeague] = useState('');
  const [status, setStatus] = useState<Status>('all');
  const [slot, setSlot] = useState<Slot>('all');
  const [goal, setGoal] = useState<Goal>('off');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<Sort>('time');
  const cardMode = useCardMode();
  const [view, setView] = useState<View>('match');
  const [limit, setLimit] = useState(12);
  const [sheet, setSheet] = useState(false);
  const collapsed = false; // fără comutare la scroll (eliminat saltul de layout); doar rândul zilelor e sticky
  const searchRef = useRef<HTMLInputElement>(null);
  const closeSheet = useCallback(() => setSheet(false), []);

  // ieri … ultima zi publicată (pipeline-ul publică azi + 6 zile; minim până la +6)
  const lastDay = index.data?.days?.length ? index.data.days.reduce((a, b) => (b > a ? b : a)) : '';
  const strip = useMemo(() => {
    const out: string[] = [];
    for (let i = -1; i <= 13; i++) {
      const d = addDays(today, i);
      if (i > 6 && d > lastDay) break;
      out.push(d);
    }
    return out;
  }, [today, lastDay]);
  const available = new Set(index.data?.days ?? []);

  const matches = useMemo(() => (isAll ? (multi.data ?? []).flatMap((d) => d?.matches ?? []) : day.data?.matches ?? []), [isAll, multi.data, day.data]);
  const loadingList = isAll ? index.loading || multi.loading : day.loading;
  const leagues = useMemo(() => [...new Set(matches.map((m) => m.league.name))].sort((a, b) => a.localeCompare(b, 'ro')), [matches]);
  const g = MARKET_GROUPS.find((x) => x.id === group) ?? MARKET_GROUPS[0];

  // o = filtre „ce-ar fi dacă” (cifrele de sus numără exact ce ar apărea la atingere)
  type Over = { minP?: number; onlyValue?: boolean; onlyRec?: boolean; status?: Status; noOddsFloor?: boolean };
  const passP = (p: Prediction, o: Over = {}) => {
    const mp = o.minP ?? minP, val = o.onlyValue ?? onlyValue, rec = o.onlyRec ?? onlyRec;
    if (goal !== 'off') return passesSafeGoal(p, goal);
    return g.match(p) && p.p >= mp &&
    (p.odds == null ? !onlyWithOdds && !val && minOdds <= settingsMin : ((o.noOddsFloor ?? showCheap) || p.odds >= Math.max(minOdds, settingsMin)) && p.odds <= maxOdds) &&
    (!val || !!p.value) &&
    (!onlySbBeats || ((sbEdge(p) ?? -1) >= 0.02 && (sbEdge(p) ?? 1) <= 0.3)) && // >30% = aproape sigur linie/piață nepotrivită
    (!rec || isRecommended(p)) &&
    (!onlySafe || isHighSafety(p)) &&
    (!grades.length || (p.grade != null && grades.includes(p.grade)));
  };

  const passM = (m: Match, o: Over = {}) => {
    const st = o.status ?? status;
    if (league && m.league.name !== league) return false;
    if (q && !`${m.home.name} ${m.away.name} ${m.league.name}`.toLowerCase().includes(q.toLowerCase())) return false;
    if (st === 'upcoming' && m.status !== 'notstarted') return false;
    if (st === 'done' && !isFinished(m.status)) return false;
    if (slot !== 'all') { const h = hourRo(m.kickoff_utc); if (slot === 'am' && h >= 12) return false; if (slot === 'pm' && (h < 12 || h >= 18)) return false; if (slot === 'eve' && h < 18) return false; }
    return true;
  };

  const sortP = (a: Prediction, b: Prediction) => onlySbBeats ? (sbEdge(b) ?? -1) - (sbEdge(a) ?? -1) : Number(b.odds != null) - Number(a.odds != null) || (sort === 'safety' ? safetyOf(b) - safetyOf(a) : sort === 'ev' ? (b.ev ?? -9) - (a.ev ?? -9) : sort === 'conf' ? (b.confidence ?? b.p * 100) - (a.confidence ?? a.p * 100) : b.p - a.p);
  const filtered = useMemo(() => {
    const out: Array<{ m: Match; ps: Prediction[] }> = [];
    for (const m of matches) {
      if (!passM(m)) continue;
      const ps = m.predictions.filter((p) => passP(p)).sort(sort === 'time' && !onlySbBeats ? (a, b) => Number(isRecommended(b)) - Number(isRecommended(a)) || Number(!!b.is_pick) - Number(!!a.is_pick) || Number(b.odds != null) - Number(a.odds != null) || b.p - a.p : sortP);
      const noFilter = group === 'all' && minP <= 0.5 && !onlyValue && !onlyRec && !onlySafe && !grades.length;
      if (!ps.length && !(noFilter && q && !m.predictions.length)) continue;
      out.push({ m, ps });
    }
    const key = (x: { m: Match; ps: Prediction[] }) => x.ps[0];
    const hasOdds = (x: { ps: Prediction[] }) => Number(x.ps[0]?.odds != null);
    if (sort === 'time' && !onlySbBeats) out.sort((a, b) => (isAll ? roDay(a.m.kickoff_utc).localeCompare(roDay(b.m.kickoff_utc)) : 0) || Number(isStarted(a.m)) - Number(isStarted(b.m)) || hasOdds(b) - hasOdds(a) || Number(isFinished(a.m.status)) - Number(isFinished(b.m.status)) || a.m.kickoff_utc.localeCompare(b.m.kickoff_utc));
    else out.sort((a, b) => { const pa = key(a), pb = key(b); if (!pa) return 1; if (!pb) return -1; return sortP(pa, pb); });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matches, isAll, group, minP, minOdds, maxOdds, onlyValue, onlyRec, onlySafe, onlySbBeats, onlyWithOdds, showCheap, grades, league, status, slot, q, sort, settingsMin, goal]);
  const flat = useMemo(() => filtered.flatMap(({ m, ps }) => ps.map((p) => ({ m, p }))).sort((a, b) => sort === 'time' && !onlySbBeats ? Number(b.p.odds != null) - Number(a.p.odds != null) || a.m.kickoff_utc.localeCompare(b.m.kickoff_utc) : sortP(a.p, b.p)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filtered, sort]);
  const nPred = flat.length;
  const nRec = flat.filter((x) => isRecommended(x.p)).length;
  // cifrele de sus: câte MECIURI ar apărea dacă atingi filtrul, cu toate celelalte filtre și cota minimă din Setări
  const countM = (o: Over) => matches.filter((m) => passM(m, o) && m.predictions.some((p) => passP(p, o))).length;
  const hud = {
    open: countM({ status: 'upcoming' }), p80: countM({ minP: Math.max(minP, 0.8) }),
    value: countM({ onlyValue: true }), rec: countM({ onlyRec: true }),
  };
  // meciuri ascunse doar de cota minimă din Setări (ex. 80%+ la cote 1.04–1.14)
  const hiddenCheap = minP >= 0.7 && !showCheap ? matches.filter((m) => passM(m) && !m.predictions.some((p) => passP(p)) && m.predictions.some((p) => passP(p, { noOddsFloor: true }))).length : 0;
  const nActive = [goal !== 'off', group !== 'all', minP !== 0.5, minOdds !== settingsMin, maxOdds < 10, onlyValue, onlyRec, onlySafe, onlySbBeats, !onlyWithOdds, showCheap, grades.length > 0, !!league, status !== 'all', slot !== 'all'].filter(Boolean).length;
  const reset = () => { setGoal('off'); setGroup('all'); setMinP(0.5); setMinOdds(settingsMin); setMaxOdds(10); setOnlyValue(false); setOnlyRec(false); setOnlySafe(false); setOnlySbBeats(false); setOnlyWithOdds(true); setShowCheap(false); setGrades([]); setLeague(''); setStatus('all'); setSlot('all'); };
  const goalScan = useMemo(() => {
    let priced = 0, cheap = 0, low = 0, htSeen = 0;
    for (const m of matches) for (const p of m.predictions) {
      const kind = safeGoalKind(p);
      if (!kind || (goal !== 'both' && goal !== 'off' && kind !== goal)) continue;
      if (kind === 'ht') htSeen += 1;
      if (goal === 'off') continue;
      const sb = superbetPrice(p);
      const rule = SAFE_GOALS[kind];
      if (sb == null) continue;
      priced += 1;
      if (sb < rule.minOdds) cheap += 1;
      else if (p.p < rule.minP) low += 1;
    }
    return { priced, cheap, low, htSeen };
  }, [matches, goal]);

  const filterBody = (
    <div className="space-y-5">
      <FilterGroup title="Ce selecții vrei">
        <FilterToggle on={onlyRec} onClick={() => setOnlyRec(!onlyRec)} title="Recomandate" desc={`Trec toate pragurile Robotului: șansă ≥ ${REC.minP * 100}%, cotă ${REC.minOdds}–${REC.maxOdds}, valoare pozitivă.`} />
        <FilterToggle on={onlyValue} onClick={() => setOnlyValue(!onlyValue)} title="Cu valoare" desc="Cota e peste șansa Robotului (EV pozitiv)." />
        <FilterToggle on={onlySafe} onClick={() => setOnlySafe(!onlySafe)} title="Sigure" desc="Șansă mare și încredere mare în același timp." />
        <FilterToggle on={onlySbBeats} onClick={() => setOnlySbBeats(!onlySbBeats)} title="Superbet plătește mai bine" desc="Cota Superbet e cu cel puțin 2% peste media pieței." />
        <FilterToggle on={onlyWithOdds} onClick={() => setOnlyWithOdds(!onlyWithOdds)} title="Doar cu cotă reală" desc="Ascunde selecțiile fără cotă la Superbet (nu se pot juca)." />
      </FilterGroup>
      <FilterGroup title="Goluri sigure (Superbet)">
        <p className="text-xs text-muted-foreground">Peste 1,5 în meci (șansă ≥ {Math.round(SAFE_GOALS.o15.minP * 100)}%, cotă de la {SAFE_GOALS.o15.minOdds.toFixed(2)}) sau gol până la pauză (șansă ≥ {Math.round(SAFE_GOALS.ht.minP * 100)}%, cotă de la {SAFE_GOALS.ht.minOdds.toFixed(2)}).</p>
        <Segmented size="sm" value={goal} onChange={setGoal} options={[{ value: 'off', label: 'Oprit' }, { value: 'o15', label: 'Peste 1,5' }, { value: 'ht', label: 'Pauză' }, { value: 'both', label: 'Ambele' }]} />
      </FilterGroup>
      <FilterGroup title="Piață">
        <div className="flex flex-wrap gap-1.5">
          {MARKET_GROUPS.map((m) => <button key={m.id} className={cn('chip', group === m.id && 'chip-on')} onClick={() => setGroup(m.id)}>{m.label}</button>)}
        </div>
      </FilterGroup>
      <FilterGroup title="Șansă și cote">
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-xs text-muted-foreground">Șansă minimă: <b className="text-foreground">{minP <= 0 ? 'toate' : `${Math.round(minP * 100)}%`}</b>
            <input type="range" min={0} max={0.95} step={0.05} value={minP} onChange={(e) => setMinP(Number(e.target.value))} className="mt-1 h-8 w-full" />
          </label>
          <label className="text-xs text-muted-foreground">Cotă minimă: <b className="text-foreground">{minOdds.toFixed(2)}</b>
            <input type="range" min={settingsMin} max={3} step={0.05} value={minOdds} onChange={(e) => setMinOdds(Number(e.target.value))} className="mt-1 h-8 w-full" />
          </label>
          <label className="text-xs text-muted-foreground">Cotă maximă: <b className="text-foreground">{maxOdds >= 10 ? 'fără limită' : maxOdds.toFixed(2)}</b>
            <input type="range" min={1.3} max={10} step={0.1} value={maxOdds} onChange={(e) => setMaxOdds(Number(e.target.value))} className="mt-1 h-8 w-full" />
          </label>
        </div>
      </FilterGroup>
      <FilterGroup title="Încredere">
        <div className="flex flex-wrap gap-1.5">{['A', 'B', 'C', 'D'].map((x) => <button key={x} aria-pressed={grades.includes(x)} className={cn('chip justify-center', grades.includes(x) && 'chip-on')} onClick={() => setGrades(grades.includes(x) ? grades.filter((y) => y !== x) : [...grades, x])}>{confidence(x)!.short}</button>)}</div>
      </FilterGroup>
      <FilterGroup title="Ligă">
        <select aria-label="Ligă" className="input min-h-11" value={league} onChange={(e) => setLeague(e.target.value)}>
          <option value="">Toate ligile ({leagues.length})</option>
          {leagues.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      </FilterGroup>
      <FilterGroup title="Stare și oră">
        <div className="flex flex-col gap-2">
          <Segmented size="sm" value={status} onChange={setStatus} options={[{ value: 'all', label: 'Toate' }, { value: 'upcoming', label: 'Nejucate' }, { value: 'done', label: 'Terminate' }]} />
          <Segmented size="sm" value={slot} onChange={setSlot} options={[{ value: 'all', label: 'Orice oră' }, { value: 'am', label: '< 12' }, { value: 'pm', label: '12–18' }, { value: 'eve', label: '> 18' }]} />
        </div>
      </FilterGroup>
      <FilterGroup title="Afișare">
        <FilterToggle on={cardMode === 'detailed'} onClick={() => setCardMode(cardMode === 'detailed' ? 'compact' : 'detailed')} title="Carduri detaliate" desc="Arată și 1/X/2 și explicația selecției. Oprit = carduri mai scurte." />
      </FilterGroup>
    </div>
  );
  const advanced = [
    group !== 'all' ? { k: 'piață', t: g.label, x: () => setGroup('all') } : null,
    minP !== 0.5 ? { k: 'șansă', t: minP <= 0 ? 'orice șansă' : `șansă ≥ ${Math.round(minP * 100)}%`, x: () => setMinP(0.5) } : null,
    minOdds !== settingsMin ? { k: 'min', t: `cotă ≥ ${minOdds.toFixed(2)}`, x: () => setMinOdds(settingsMin) } : null,
    maxOdds < 10 ? { k: 'max', t: `cotă ≤ ${maxOdds.toFixed(2)}`, x: () => setMaxOdds(10) } : null,
    onlyValue ? { k: 'val', t: 'cu valoare', x: () => setOnlyValue(false) } : null,
    onlyRec ? { k: 'rec', t: 'recomandate', x: () => setOnlyRec(false) } : null,
    goal !== 'off' ? { k: 'goal', t: goal === 'o15' ? 'goluri sigure: peste 1,5' : goal === 'ht' ? 'goluri sigure: pauză' : 'goluri sigure', x: () => setGoal('off') } : null,
    onlySafe ? { k: 'safe', t: 'sigure', x: () => setOnlySafe(false) } : null,
    onlySbBeats ? { k: 'sb', t: 'Superbet plătește mai bine', x: () => setOnlySbBeats(false) } : null,
    !onlyWithOdds ? { k: 'odds', t: 'și fără cotă', x: () => setOnlyWithOdds(true) } : null,
    showCheap ? { k: 'cheap', t: `și cote sub ${settingsMin.toFixed(2)}`, x: () => setShowCheap(false) } : null,
    grades.length ? { k: 'gr', t: `încredere ${grades.join('')}`, x: () => setGrades([]) } : null,
    league ? { k: 'lg', t: league, x: () => setLeague('') } : null,
    status !== 'all' ? { k: 'st', t: status === 'upcoming' ? 'nejucate' : 'terminate', x: () => setStatus('all') } : null,
    slot !== 'all' ? { k: 'ora', t: slot === 'am' ? 'înainte de 12' : slot === 'pm' ? '12–18' : 'după 18', x: () => setSlot('all') } : null,
  ].filter((v): v is { k: string; t: string; x: () => void } => !!v);

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="eyebrow">{isAll ? 'Toate zilele' : longDay(date)}</div>
          <h1>Predicții</h1>
        </div>
        <Segmented value={view} onChange={setView} size="sm" className="shrink-0" options={[{ value: 'match', label: 'Meciuri' }, { value: 'flat', label: 'Listă' }]} />
      </div>

      <div className="filter-bar sticky top-0 z-20 -mx-4 border-b px-4 py-2">
        <div className="-mx-4 flex items-center gap-1.5 overflow-x-auto px-4 scrollbar-none" role="group" aria-label="Alege ziua">
          <button aria-pressed={isAll} onClick={() => setDate(ALL)}
            className={cn('press flex shrink-0 flex-col', collapsed ? 'min-h-[32px] rounded-xl px-2.5' : 'min-h-[42px]', ' items-center justify-center rounded-2xl border px-3 leading-tight transition-colors', isAll ? 'pill-on' : 'bg-card hover:border-primary/40')}>
            {collapsed ? <span className="text-xs font-bold">Toate</span> : <><span className={cn('text-[11px] font-semibold uppercase tracking-wide', isAll ? 'text-primary-foreground/85' : 'text-muted-foreground')}>Toate</span>
            <span className="text-sm font-bold">zilele</span></>}
          </button>
          {strip.map((d) => { const on = !isAll && d === date; const [top, bottom] = dayPill(d, today); return (
            <button key={d} aria-pressed={on} onClick={() => setDate(d)}
              className={cn('flex shrink-0 flex-col', collapsed ? 'min-h-[32px] min-w-[44px] rounded-xl px-2' : 'min-h-[42px] min-w-[54px]', ' items-center justify-center rounded-2xl border px-2.5 leading-tight transition-colors', on ? 'pill-on' : 'bg-card hover:border-primary/40', !available.has(d) && !on && 'opacity-50')}>
              {!collapsed && <span className={cn('text-[11px] font-semibold uppercase tracking-wide', on ? 'text-primary-foreground/85' : 'text-muted-foreground')}>{top}</span>}
              <span className={cn('font-bold tabular-nums', collapsed ? 'text-xs' : 'text-sm')}>{collapsed ? top : bottom}</span>
            </button>); })}
          {collapsed ? <div className="sticky -right-4 ml-auto flex shrink-0 gap-1.5 bg-background py-0.5 pl-2 pr-0">
            <button className="btn btn-outline h-8 w-8 shrink-0 rounded-xl p-0" aria-label="Caută" onClick={() => searchRef.current?.focus()}><Search className="h-4 w-4" /></button>
            <button className="btn btn-outline relative h-8 w-8 shrink-0 rounded-xl p-0" aria-label="Filtre" onClick={() => setSheet(true)}><SlidersHorizontal className="h-4 w-4" />{nActive > 0 && <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] text-primary-foreground">{nActive}</span>}</button>
          </div> : <label className="flex min-h-[42px] shrink-0 cursor-pointer items-center gap-1 rounded-2xl border bg-card px-2.5"><CalendarDays className="h-4 w-4 text-muted-foreground" />
            <input type="date" aria-label="Alege data" className="w-[112px] bg-transparent text-xs outline-none" value={isAll ? '' : date} onChange={(e) => e.target.value && setDate(e.target.value)} />
          </label>}
        </div>
      </div>
      <div className="pt-1">
        {!collapsed && <><Segmented value={ssMode ? 'ss' : 'all'} onChange={(v) => setSsMode(v === 'ss')} className="mb-2 w-full" options={[{ value: 'all', label: 'Toate predicțiile' }, { value: 'ss', label: 'Stil Supersocial' }]} />
        {!ssMode && <div className="flex items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <input ref={searchRef} className="input rounded-xl pl-9" aria-label="Caută echipă sau ligă" placeholder="Caută echipă, ligă…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select aria-label="Ligă" className="input hidden w-auto rounded-xl md:block" value={league} onChange={(e) => setLeague(e.target.value)}>
            <option value="">Toate ligile ({leagues.length})</option>
            {leagues.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <select className="input w-[5.75rem] shrink-0 rounded-xl px-2 md:w-auto" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sortare">
            <option value="time">Oră</option><option value="p">Șansă</option><option value="ev">Valoare</option><option value="conf">Încredere</option><option value="safety">Siguranță</option>
          </select>
          <button className="btn btn-outline relative h-11 shrink-0 rounded-xl px-3" onClick={() => setSheet(true)} aria-label="Filtre"><SlidersHorizontal className="h-4 w-4" /><span className="hidden min-[400px]:inline">Filtre</span>{nActive > 0 && <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">{nActive}</span>}</button>
        </div>}
        {!ssMode && advanced.length > 0 && <div className="mt-2 flex gap-1.5 overflow-x-auto scrollbar-none">
          {advanced.map((a) => <button key={a.k} type="button" className="chip chip-on shrink-0" onClick={a.x}>{a.t} ×</button>)}
        </div>}
        </>}
      </div>
      <Sheet open={sheet} onClose={closeSheet} title="Filtre" subtitle={`${filtered.length} meciuri · ${nPred} selecții · se actualizează imediat`}
        footer={<div className="flex gap-2"><button className="btn btn-outline min-h-11 flex-1" onClick={reset}>Resetează tot</button><button className="btn btn-primary min-h-11 flex-1" onClick={closeSheet}>Gata · {nPred}</button></div>}>
        {filterBody}
      </Sheet>

      {day.data?._source === 'legacy' && <Notice tone="warn">Pipeline-ul nou nu a publicat încă <code>api/days/{date}.json</code>; afișez predicțiile din fișierele vechi (v2). Cotele lipsă apar ca „fără cotă” și nu intră în bilete.</Notice>}

      {ssMode && <p className="text-xs text-muted-foreground">Cornere, reprize și intervale de goluri, cu prețul Superbet. Oferta Superbet se citește pentru azi și mâine; alege ziua de sus.</p>}
      {!ssMode && matches.length > 0 && (
        <div className="grid grid-cols-4 gap-2" role="group" aria-label="Filtre rapide">
          {[
            { k: 'Încă de jucat', v: hud.open, on: status === 'upcoming', x: () => setStatus(status === 'upcoming' ? 'all' : 'upcoming') },
            { k: 'Șansă 80%+', v: hud.p80, on: minP >= 0.8, x: () => setMinP(minP >= 0.8 ? 0.5 : 0.8) },
            { k: 'Cu valoare', v: hud.value, on: onlyValue, x: () => setOnlyValue(!onlyValue) },
            { k: 'Recomandate', v: hud.rec, on: onlyRec, x: () => setOnlyRec(!onlyRec) },
          ].map((c) => (
            <button key={c.k} type="button" aria-pressed={c.on} onClick={c.x} className={cn('pred-hud press', c.on && 'pred-hud-on')}>
              <span className="num text-[20px] font-extrabold leading-none">{c.v}</span>
              <span className="text-[10px] font-bold leading-tight text-muted-foreground">{c.k}</span>
            </button>
          ))}
        </div>
      )}
      {!ssMode && hiddenCheap > 0 && (
        <Notice>
          Încă <b>{hiddenCheap}</b> {hiddenCheap === 1 ? 'meci are' : 'meciuri au'} selecții de șansă mare, dar cu cota sub {settingsMin.toFixed(2)} (cota minimă din Setări).{' '}
          <button type="button" className="font-bold text-primary underline" onClick={() => setShowCheap(true)}>Arată-le</button>
        </Notice>
      )}
      {!ssMode && <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
        <span><b className="text-foreground">{filtered.length}</b> {filtered.length === 1 ? 'meci' : 'meciuri'} · <b className="text-foreground">{nRec}</b> recomandate</span>
        <InfoTip text={`Recomandat = șansă ≥ ${REC.minP * 100}%, valoare pozitivă, cotă ${REC.minOdds}–${REC.maxOdds} și încredere mare sau bună.`} label="Ce înseamnă recomandat?" />
        {!isAll && day.data?.generated_at && <time dateTime={day.data.generated_at} className="text-[11px]">Ziua publicată {roDateTime(day.data.generated_at)}</time>}
        {nActive > 0 && <button type="button" className="ml-auto min-h-11 font-semibold text-primary" onClick={reset}>Resetează ({nActive})</button>}
      </div>}

      {ssMode ? <SupersocialList day={isAll ? null : date} today={today} /> : loadingList ? <Loading /> : !matches.length ? (
        <Empty title="Nu există meciuri publicate pentru această zi" icon={<CalendarDays className="h-6 w-6" />}>Alege altă zi. Programul se publică pe ±7 zile.</Empty>
      ) : !filtered.length ? (
        <Empty title={goal !== 'off' ? 'Nimic în banda asta' : 'Niciun rezultat cu filtrele curente'}>
          {goal !== 'off' ? (
            <p className="text-sm text-muted-foreground">
              {goal !== 'o15' && goalScan.htSeen === 0 ? 'Peste 0,5 la pauză nu e încă în predicțiile publicate. ' : ''}
              {goalScan.cheap > 0 ? `${goalScan.cheap} meciuri au cotă Superbet sub prag, deși șansa e mare. ` : ''}
              {goalScan.low > 0 ? `${goalScan.low} au cota bună, dar șansa e sub prag. ` : ''}
              Mai bine pauză decât un preț prea mic.
            </p>
          ) : <button type="button" className="btn btn-outline mt-1 min-h-11" onClick={reset}>Resetează filtrele</button>}
        </Empty>
      ) : view === 'match' ? (
        <div className="stagger grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {filtered.slice(0, limit).map(({ m, ps }, i, arr) => (
            <Fragment key={m.id}>
              {isAll && sort === 'time' && (i === 0 || roDay(arr[i - 1].m.kickoff_utc) !== roDay(m.kickoff_utc)) && <DayHeader d={roDay(m.kickoff_utc)} today={today} />}
              <MatchCard m={m} focus={ps} />
            </Fragment>
          ))}
        </div>
      ) : (
        <div className="card divide-y px-3">
          {flat.slice(0, limit * 2).map(({ m, p }, i, arr) => (
            <Fragment key={`${m.id}-${p.id}`}>
              {isAll && sort === 'time' && (i === 0 || roDay(arr[i - 1].m.kickoff_utc) !== roDay(m.kickoff_utc)) && <div className="py-2 text-xs font-extrabold uppercase tracking-wide text-primary">{longDay(roDay(m.kickoff_utc))}</div>}
              <PredLine m={m} p={p} showMatch />
            </Fragment>
          ))}
        </div>
      )}
      {(view === 'match' ? filtered.length > limit : flat.length > limit * 2) && (
        <LoadMore key={limit} onMore={() => setLimit((l) => l + 16)} />
      )}
      <p className="text-center text-[11px] text-muted-foreground">Toate orele sunt în ora României. Datele zilei {roDay(day.data?.generated_at ?? '') ? `generate ${new Date(day.data!.generated_at!).toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest' })}` : ''}</p>
    </div>
  );
}
