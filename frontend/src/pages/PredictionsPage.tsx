import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { SlidersHorizontal, Search, CalendarDays, ListChecks } from 'lucide-react';
import { useDay } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadDayIndex } from '@/lib/data';
import { useStore } from '@/lib/store';
import { addDays, dayLabel, todayRo, longDay, roDay } from '@/lib/format';
import { MARKET_GROUPS, isFinished, isLive } from '@/lib/markets';
import { Segmented, Loading, Empty, Notice, Badge } from '@/components/kit';
import { MatchCard, PredLine } from '@/components/MatchCard';
import type { Match, Prediction } from '@/lib/types';
import { cn } from '@/lib/utils';

type Sort = 'time' | 'p' | 'ev' | 'conf';
type View = 'match' | 'flat';
type Status = 'all' | 'upcoming' | 'live' | 'done';
type Slot = 'all' | 'am' | 'pm' | 'eve';

const hourRo = (iso: string) => Number(new Intl.DateTimeFormat('ro-RO', { timeZone: 'Europe/Bucharest', hour: '2-digit', hour12: false }).format(new Date(iso)));

export default function PredictionsPage() {
  const [sp, setSp] = useSearchParams();
  const today = todayRo();
  const date = sp.get('zi') || today;
  const setDate = (d: string) => { sp.set('zi', d); setSp(sp, { replace: true }); };
  const settingsMin = useStore((s) => s.settings.minOdds);
  const index = useAsync(() => loadDayIndex(settingsMin), [settingsMin]);
  const day = useDay(date);

  const [group, setGroup] = useState('all');
  const [minP, setMinP] = useState(0.5);
  const [minOdds, setMinOdds] = useState(settingsMin);
  const [maxOdds, setMaxOdds] = useState(10);
  const [onlyValue, setOnlyValue] = useState(false);
  const [onlyWithOdds, setOnlyWithOdds] = useState(false);
  const [grades, setGrades] = useState<string[]>([]);
  const [league, setLeague] = useState('');
  const [status, setStatus] = useState<Status>('all');
  const [slot, setSlot] = useState<Slot>('all');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<Sort>('time');
  const [view, setView] = useState<View>('match');
  const [limit, setLimit] = useState(40);
  const [showFilters, setShowFilters] = useState(() => typeof window === 'undefined' || window.innerWidth >= 768);

  const strip = useMemo(() => {
    const base = [-1, 0, 1, 2, 3, 4, 5, 6, 7].map((i) => addDays(today, i));
    return base;
  }, [today]);
  const available = new Set(index.data?.days ?? []);

  const matches = day.data?.matches ?? [];
  const leagues = useMemo(() => [...new Set(matches.map((m) => m.league.name))].sort((a, b) => a.localeCompare(b, 'ro')), [matches]);
  const g = MARKET_GROUPS.find((x) => x.id === group) ?? MARKET_GROUPS[0];

  const passP = (p: Prediction) =>
    g.match(p) && p.p >= minP &&
    (p.odds == null ? !onlyWithOdds && !onlyValue && minOdds <= settingsMin : p.odds >= Math.max(minOdds, settingsMin) && p.odds <= maxOdds) &&
    (!onlyValue || !!p.value) &&
    (!grades.length || (p.grade != null && grades.includes(p.grade)));

  const passM = (m: Match) => {
    if (league && m.league.name !== league) return false;
    if (q && !`${m.home.name} ${m.away.name} ${m.league.name}`.toLowerCase().includes(q.toLowerCase())) return false;
    if (status === 'upcoming' && m.status !== 'notstarted') return false;
    if (status === 'live' && !isLive(m.status)) return false;
    if (status === 'done' && !isFinished(m.status)) return false;
    if (slot !== 'all') { const h = hourRo(m.kickoff_utc); if (slot === 'am' && h >= 12) return false; if (slot === 'pm' && (h < 12 || h >= 18)) return false; if (slot === 'eve' && h < 18) return false; }
    return true;
  };

  const sortP = (a: Prediction, b: Prediction) => sort === 'ev' ? (b.ev ?? -9) - (a.ev ?? -9) : sort === 'conf' ? (b.confidence ?? b.p * 100) - (a.confidence ?? a.p * 100) : b.p - a.p;
  const filtered = useMemo(() => {
    const out: Array<{ m: Match; ps: Prediction[] }> = [];
    for (const m of matches) {
      if (!passM(m)) continue;
      const ps = m.predictions.filter(passP).sort(sort === 'time' ? (a, b) => Number(!!b.is_pick) - Number(!!a.is_pick) || Number(b.odds != null) - Number(a.odds != null) || b.p - a.p : sortP);
      const noFilter = group === 'all' && minP <= 0.5 && !onlyValue && !grades.length && !onlyWithOdds;
      if (!ps.length && !(noFilter && !m.predictions.length)) continue;
      out.push({ m, ps });
    }
    const key = (x: { m: Match; ps: Prediction[] }) => x.ps[0];
    if (sort === 'time') out.sort((a, b) => a.m.kickoff_utc.localeCompare(b.m.kickoff_utc));
    else out.sort((a, b) => { const pa = key(a), pb = key(b); if (!pa) return 1; if (!pb) return -1; return sortP(pa, pb); });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matches, group, minP, minOdds, maxOdds, onlyValue, onlyWithOdds, grades, league, status, slot, q, sort, settingsMin]);

  const flat = useMemo(() => filtered.flatMap(({ m, ps }) => ps.map((p) => ({ m, p }))).sort((a, b) => sort === 'time' ? a.m.kickoff_utc.localeCompare(b.m.kickoff_utc) : sortP(a.p, b.p)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filtered, sort]);
  const nPred = flat.length;
  const nValue = flat.filter((x) => x.p.value).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold"><ListChecks className="h-5 w-5 text-primary" />Predicțiile zilei</h1>
          <p className="text-sm capitalize text-muted-foreground">{longDay(date)} · ora României</p>
        </div>
        <Segmented value={view} onChange={setView} size="sm" options={[{ value: 'match', label: 'Pe meci' }, { value: 'flat', label: 'Listă selecții' }]} />
      </div>

      <div className="-mx-3 flex gap-1.5 overflow-x-auto px-3 pb-1 scrollbar-none">
        {strip.map((d) => (
          <button key={d} onClick={() => setDate(d)} className={cn('chip shrink-0', d === date && 'chip-on', !available.has(d) && d !== date && 'opacity-50')}>
            {dayLabel(d)}
          </button>
        ))}
        <label className="chip shrink-0 cursor-pointer"><CalendarDays className="h-3.5 w-3.5" />
          <input type="date" className="w-[110px] bg-transparent text-xs outline-none" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </label>
      </div>

      <div className="card p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[180px] flex-1">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <input className="input pl-8" placeholder="Caută echipă sau ligă…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input w-auto" value={league} onChange={(e) => setLeague(e.target.value)}>
            <option value="">Toate ligile ({leagues.length})</option>
            {leagues.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <select className="input w-auto" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="time">Sortare: oră</option><option value="p">Probabilitate</option><option value="ev">EV (valoare)</option><option value="conf">Încredere</option>
          </select>
          <button className={cn('btn btn-outline', showFilters && 'bg-accent')} onClick={() => setShowFilters(!showFilters)}><SlidersHorizontal className="h-4 w-4" />Filtre</button>
        </div>
        {showFilters && (
          <div className="mt-3 space-y-3">
            <div className="flex flex-wrap gap-1.5">
              {MARKET_GROUPS.map((m) => <button key={m.id} className={cn('chip', group === m.id && 'chip-on')} onClick={() => setGroup(m.id)}>{m.label}</button>)}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="text-xs text-muted-foreground">Probabilitate minimă: <b className="text-foreground">{Math.round(minP * 100)}%</b>
                <input type="range" min={0.3} max={0.95} step={0.05} value={minP} onChange={(e) => setMinP(Number(e.target.value))} className="w-full" />
              </label>
              <label className="text-xs text-muted-foreground">Cotă minimă: <b className="text-foreground">{minOdds.toFixed(2)}</b>
                <input type="range" min={settingsMin} max={3} step={0.05} value={minOdds} onChange={(e) => setMinOdds(Number(e.target.value))} className="w-full" />
              </label>
              <label className="text-xs text-muted-foreground">Cotă maximă: <b className="text-foreground">{maxOdds >= 10 ? 'fără limită' : maxOdds.toFixed(2)}</b>
                <input type="range" min={1.3} max={10} step={0.1} value={maxOdds} onChange={(e) => setMaxOdds(Number(e.target.value))} className="w-full" />
              </label>
              <div className="text-xs text-muted-foreground">Grad
                <div className="mt-1 flex gap-1">{['A', 'B', 'C', 'D'].map((x) => <button key={x} className={cn('chip', grades.includes(x) && 'chip-on')} onClick={() => setGrades(grades.includes(x) ? grades.filter((y) => y !== x) : [...grades, x])}>{x}</button>)}</div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Segmented size="sm" value={status} onChange={setStatus} options={[{ value: 'all', label: 'Toate' }, { value: 'upcoming', label: 'Nejucate' }, { value: 'live', label: 'Live' }, { value: 'done', label: 'Terminate' }]} />
              <Segmented size="sm" value={slot} onChange={setSlot} options={[{ value: 'all', label: 'Orice oră' }, { value: 'am', label: '< 12:00' }, { value: 'pm', label: '12–18' }, { value: 'eve', label: '> 18:00' }]} />
              <button className={cn('chip', onlyValue && 'chip-on')} onClick={() => setOnlyValue(!onlyValue)}>Doar valoare (EV &gt; 0)</button>
              <button className={cn('chip', onlyWithOdds && 'chip-on')} onClick={() => setOnlyWithOdds(!onlyWithOdds)}>Doar cu cotă</button>
            </div>
          </div>
        )}
      </div>

      {day.data?._source === 'legacy' && <Notice tone="warn">Pipeline-ul nou nu a publicat încă <code>api/days/{date}.json</code>; afișez predicțiile din fișierele vechi (v2). Cotele lipsă apar ca „fără cotă” și nu intră în bilete.</Notice>}

      <div className="flex flex-wrap gap-2 text-xs">
        <Badge tone="outline">{filtered.length} meciuri</Badge>
        <Badge tone="outline">{nPred} predicții</Badge>
        <Badge tone="win">{nValue} cu valoare</Badge>
        <span className="text-muted-foreground">cotă minimă globală {settingsMin.toFixed(2)}</span>
      </div>

      {day.loading ? <Loading /> : !matches.length ? (
        <Empty title="Nu există meciuri publicate pentru această zi" icon={<CalendarDays className="h-6 w-6" />}>Alege altă zi. Programul se publică pe ±7 zile.</Empty>
      ) : !filtered.length ? (
        <Empty title="Niciun rezultat cu filtrele curente">Scade probabilitatea minimă sau alege „Toate” la piață.</Empty>
      ) : view === 'match' ? (
        <div className="grid gap-3 md:grid-cols-2">
          {filtered.slice(0, limit).map(({ m, ps }) => <MatchCard key={m.id} m={m} focus={ps} />)}
        </div>
      ) : (
        <div className="card divide-y px-3">
          {flat.slice(0, limit * 2).map(({ m, p }) => <PredLine key={`${m.id}-${p.id}`} m={m} p={p} showMatch />)}
        </div>
      )}
      {(view === 'match' ? filtered.length > limit : flat.length > limit * 2) && (
        <div className="text-center"><button className="btn btn-outline" onClick={() => setLimit(limit + 40)}>Arată mai multe</button></div>
      )}
      <p className="text-center text-[11px] text-muted-foreground">Toate orele sunt în ora României. Datele zilei {roDay(day.data?.generated_at ?? '') ? `generate ${new Date(day.data!.generated_at!).toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest' })}` : ''}</p>
    </div>
  );
}
