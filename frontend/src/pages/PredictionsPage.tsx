import { SupersocialList } from '@/components/SupersocialList';
import { useCardMode, setCardMode } from '@/lib/cardMode';
import { Fragment, useCallback, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { SlidersHorizontal, Search, CalendarDays } from 'lucide-react';
import { useDay, useDays } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadDayIndex } from '@/lib/data';
import { useStore } from '@/lib/store';
import { addDays, todayRo, longDay, roDay, roDateTime } from '@/lib/format';
import { MARKET_GROUPS, isFinished, isStarted } from '@/lib/markets';
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
  const [grades, setGrades] = useState<string[]>([]);
  const [league, setLeague] = useState('');
  const [status, setStatus] = useState<Status>('all');
  const [slot, setSlot] = useState<Slot>('all');
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

  const passP = (p: Prediction) =>
    g.match(p) && p.p >= minP &&
    (p.odds == null ? !onlyWithOdds && !onlyValue && minOdds <= settingsMin : p.odds >= Math.max(minOdds, settingsMin) && p.odds <= maxOdds) &&
    (!onlyValue || !!p.value) &&
    (!onlySbBeats || ((sbEdge(p) ?? -1) >= 0.02 && (sbEdge(p) ?? 1) <= 0.3)) && // >30% = aproape sigur linie/piață nepotrivită
    (!onlyRec || isRecommended(p)) &&
    (!onlySafe || isHighSafety(p)) &&
    (!grades.length || (p.grade != null && grades.includes(p.grade)));

  const passM = (m: Match) => {
    if (league && m.league.name !== league) return false;
    if (q && !`${m.home.name} ${m.away.name} ${m.league.name}`.toLowerCase().includes(q.toLowerCase())) return false;
    if (status === 'upcoming' && m.status !== 'notstarted') return false;
    if (status === 'done' && !isFinished(m.status)) return false;
    if (slot !== 'all') { const h = hourRo(m.kickoff_utc); if (slot === 'am' && h >= 12) return false; if (slot === 'pm' && (h < 12 || h >= 18)) return false; if (slot === 'eve' && h < 18) return false; }
    return true;
  };

  const sortP = (a: Prediction, b: Prediction) => onlySbBeats ? (sbEdge(b) ?? -1) - (sbEdge(a) ?? -1) : Number(b.odds != null) - Number(a.odds != null) || (sort === 'safety' ? safetyOf(b) - safetyOf(a) : sort === 'ev' ? (b.ev ?? -9) - (a.ev ?? -9) : sort === 'conf' ? (b.confidence ?? b.p * 100) - (a.confidence ?? a.p * 100) : b.p - a.p);
  const filtered = useMemo(() => {
    const out: Array<{ m: Match; ps: Prediction[] }> = [];
    for (const m of matches) {
      if (!passM(m)) continue;
      const ps = m.predictions.filter(passP).sort(sort === 'time' && !onlySbBeats ? (a, b) => Number(isRecommended(b)) - Number(isRecommended(a)) || Number(!!b.is_pick) - Number(!!a.is_pick) || Number(b.odds != null) - Number(a.odds != null) || b.p - a.p : sortP);
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
  }, [matches, isAll, group, minP, minOdds, maxOdds, onlyValue, onlyRec, onlySafe, onlySbBeats, onlyWithOdds, grades, league, status, slot, q, sort, settingsMin]);
  const flat = useMemo(() => filtered.flatMap(({ m, ps }) => ps.map((p) => ({ m, p }))).sort((a, b) => sort === 'time' && !onlySbBeats ? Number(b.p.odds != null) - Number(a.p.odds != null) || a.m.kickoff_utc.localeCompare(b.m.kickoff_utc) : sortP(a.p, b.p)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filtered, sort]);
  const nPred = flat.length;
  const nRec = flat.filter((x) => isRecommended(x.p)).length;
  const nActive = [group !== 'all', minP !== 0.5, minOdds !== settingsMin, maxOdds < 10, onlyValue, onlyRec, onlySafe, onlySbBeats, !onlyWithOdds, grades.length > 0, !!league, status !== 'all', slot !== 'all'].filter(Boolean).length;
  const reset = () => { setGroup('all'); setMinP(0.5); setMinOdds(settingsMin); setMaxOdds(10); setOnlyValue(false); setOnlyRec(false); setOnlySafe(false); setOnlySbBeats(false); setOnlyWithOdds(true); setGrades([]); setLeague(''); setStatus('all'); setSlot('all'); };

  const filterBody = (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">Se aplică imediat. Închide panoul când lista arată bine.</p>
      <div>
        <div className="mb-1.5 text-xs font-semibold text-muted-foreground">Piață</div>
        <div className="flex flex-wrap gap-1.5">
          {MARKET_GROUPS.map((m) => <button key={m.id} className={cn('chip', group === m.id && 'chip-on')} onClick={() => setGroup(m.id)}>{m.label}</button>)}
        </div>
      </div>
      <div>
        <div className="mb-1.5 text-xs font-semibold text-muted-foreground">Valoare</div>
        <button className={cn('chip', onlyValue && 'chip-on')} onClick={() => setOnlyValue(!onlyValue)}>Doar cu valoare</button>
      </div>
      <div>
        <div className="mb-1.5 text-xs font-semibold text-muted-foreground">Șansă și cote</div>
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
      </div>
      <div className="text-xs text-muted-foreground">Încredere
        <div className="mt-1.5 flex flex-wrap gap-1.5">{['A', 'B', 'C', 'D'].map((x) => <button key={x} aria-pressed={grades.includes(x)} className={cn('chip justify-center', grades.includes(x) && 'chip-on')} onClick={() => setGrades(grades.includes(x) ? grades.filter((y) => y !== x) : [...grades, x])}>{confidence(x)!.short}</button>)}</div>
      </div>
      <div>
        <div className="mb-1.5 text-xs font-semibold text-muted-foreground">Ligă</div>
        <select aria-label="Ligă" className="input min-h-11" value={league} onChange={(e) => setLeague(e.target.value)}>
          <option value="">Toate ligile ({leagues.length})</option>
          {leagues.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>
      <div>
        <div className="mb-1.5 text-xs font-semibold text-muted-foreground">Stare și oră</div>
        <div className="flex flex-col gap-2">
          <Segmented size="sm" value={status} onChange={setStatus} options={[{ value: 'all', label: 'Toate' }, { value: 'upcoming', label: 'Nejucate' }, { value: 'done', label: 'Terminate' }]} />
          <Segmented size="sm" value={slot} onChange={setSlot} options={[{ value: 'all', label: 'Orice oră' }, { value: 'am', label: '< 12' }, { value: 'pm', label: '12–18' }, { value: 'eve', label: '> 18' }]} />
        </div>
      </div>
    </div>
  );
  const advanced = [
    group !== 'all' ? { k: 'piață', t: g.label, x: () => setGroup('all') } : null,
    minP !== 0.5 ? { k: 'șansă', t: minP <= 0 ? 'orice șansă' : `șansă ≥ ${Math.round(minP * 100)}%`, x: () => setMinP(0.5) } : null,
    minOdds !== settingsMin ? { k: 'min', t: `cotă ≥ ${minOdds.toFixed(2)}`, x: () => setMinOdds(settingsMin) } : null,
    maxOdds < 10 ? { k: 'max', t: `cotă ≤ ${maxOdds.toFixed(2)}`, x: () => setMaxOdds(10) } : null,
    onlyValue ? { k: 'val', t: 'cu valoare', x: () => setOnlyValue(false) } : null,
    onlyRec ? { k: 'rec', t: 'recomandate', x: () => setOnlyRec(false) } : null,
    onlySafe ? { k: 'safe', t: 'sigure', x: () => setOnlySafe(false) } : null,
    onlySbBeats ? { k: 'sb', t: 'Superbet mai bun', x: () => setOnlySbBeats(false) } : null,
    !onlyWithOdds ? { k: 'odds', t: 'și fără cotă', x: () => setOnlyWithOdds(true) } : null,
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
        {!collapsed && <><div className="flex items-center gap-2">
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
          <button className="btn btn-outline relative h-11 w-11 rounded-xl p-0" onClick={() => setSheet(true)} aria-label="Filtre"><SlidersHorizontal className="h-4 w-4" />{nActive > 0 && <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">{nActive}</span>}</button>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <button className={cn('chip shrink-0', cardMode === 'detailed' && 'chip-on')} aria-pressed={cardMode === 'detailed'} onClick={() => setCardMode(cardMode === 'detailed' ? 'compact' : 'detailed')}>Detaliat</button>
          <button className={cn('chip shrink-0', ssMode && 'chip-on')} aria-pressed={ssMode} onClick={() => setSsMode(!ssMode)}>Supersocial</button>
          <button className={cn('chip shrink-0', onlyRec && 'chip-on')} aria-pressed={onlyRec} onClick={() => setOnlyRec(!onlyRec)}>Recomandate</button>
          <button className={cn('chip shrink-0', onlyWithOdds && 'chip-on')} aria-pressed={onlyWithOdds} onClick={() => setOnlyWithOdds(!onlyWithOdds)}>Cu cotă</button>
          <button className={cn('chip shrink-0', onlySafe && 'chip-on')} aria-pressed={onlySafe} onClick={() => setOnlySafe(!onlySafe)}>Sigure</button>
          <button className={cn('chip shrink-0', onlySbBeats && 'chip-on')} aria-pressed={onlySbBeats} onClick={() => setOnlySbBeats(!onlySbBeats)}>Superbet mai bun</button>
        </div>
        {advanced.length > 0 && <div className="mt-2 flex gap-1.5 overflow-x-auto scrollbar-none">
          {advanced.map((a) => <button key={a.k} type="button" className="chip chip-on shrink-0" onClick={a.x}>{a.t} ×</button>)}
        </div>}
        </>}
      </div>
      <Sheet open={sheet} onClose={closeSheet} title="Filtre" subtitle={`${filtered.length} meciuri · ${nPred} selecții · se actualizează imediat`}
        footer={<div className="flex gap-2"><button className="btn btn-outline min-h-11 flex-1" onClick={reset}>Resetează tot</button><button className="btn btn-primary min-h-11 flex-1" onClick={closeSheet}>Gata · {nPred}</button></div>}>
        {filterBody}
      </Sheet>

      {day.data?._source === 'legacy' && <Notice tone="warn">Pipeline-ul nou nu a publicat încă <code>api/days/{date}.json</code>; afișez predicțiile din fișierele vechi (v2). Cotele lipsă apar ca „fără cotă” și nu intră în bilete.</Notice>}

      {ssMode && <Notice>Stil Supersocial e lista de azi: cornere, reprize, intervale. Ziua și filtrele de deasupra nu o schimbă.</Notice>}
      {!ssMode && <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
        <span><b className="text-foreground">{filtered.length}</b> meciuri · <b className="text-foreground">{nRec}</b> recomandate</span>
        <InfoTip text={`Recomandat = șansă ≥ ${REC.minP * 100}%, valoare pozitivă, cotă ${REC.minOdds}–${REC.maxOdds} și încredere mare sau bună.`} label="Ce înseamnă recomandat?" />
        {!isAll && day.data?.generated_at && <time dateTime={day.data.generated_at} className="text-[11px]">Ziua publicată {roDateTime(day.data.generated_at)}</time>}
        {nActive > 0 && <button type="button" className="ml-auto min-h-11 font-semibold text-primary" onClick={reset}>Resetează ({nActive})</button>}
      </div>}

      {ssMode ? <SupersocialList /> : loadingList ? <Loading /> : !matches.length ? (
        <Empty title="Nu există meciuri publicate pentru această zi" icon={<CalendarDays className="h-6 w-6" />}>Alege altă zi. Programul se publică pe ±7 zile.</Empty>
      ) : !filtered.length ? (
        <Empty title="Niciun rezultat cu filtrele curente"><button type="button" className="btn btn-outline mt-1 min-h-11" onClick={reset}>Resetează filtrele</button></Empty>
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
