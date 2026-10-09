import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { SlidersHorizontal, Search, CalendarDays, ListChecks } from 'lucide-react';
import { useDay } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadDayIndex } from '@/lib/data';
import { useStore } from '@/lib/store';
import { addDays, dayLabel, todayRo, longDay, roDay } from '@/lib/format';
import { MARKET_GROUPS, isFinished } from '@/lib/markets';
import { Segmented, Loading, Empty, Notice, Badge, BottomSheet } from '@/components/kit';
import { isRecommended, REC } from '@/lib/rules';
import { MatchCard, PredLine } from '@/components/MatchCard';
import type { Match, Prediction } from '@/lib/types';
import { cn } from '@/lib/utils';

type Sort = 'time' | 'p' | 'ev' | 'conf';
type View = 'match' | 'flat';
type Status = 'all' | 'upcoming' | 'done';
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
  const [onlyRec, setOnlyRec] = useState(false);
  const [onlyWithOdds, setOnlyWithOdds] = useState(false);
  const [grades, setGrades] = useState<string[]>([]);
  const [league, setLeague] = useState('');
  const [status, setStatus] = useState<Status>('all');
  const [slot, setSlot] = useState<Slot>('all');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<Sort>('time');
  const [view, setView] = useState<View>('match');
  const [limit, setLimit] = useState(40);
  const [sheet, setSheet] = useState(false);

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
    (!onlyRec || isRecommended(p)) &&
    (!grades.length || (p.grade != null && grades.includes(p.grade)));

  const passM = (m: Match) => {
    if (league && m.league.name !== league) return false;
    if (q && !`${m.home.name} ${m.away.name} ${m.league.name}`.toLowerCase().includes(q.toLowerCase())) return false;
    if (status === 'upcoming' && m.status !== 'notstarted') return false;
    if (status === 'done' && !isFinished(m.status)) return false;
    if (slot !== 'all') { const h = hourRo(m.kickoff_utc); if (slot === 'am' && h >= 12) return false; if (slot === 'pm' && (h < 12 || h >= 18)) return false; if (slot === 'eve' && h < 18) return false; }
    return true;
  };

  const sortP = (a: Prediction, b: Prediction) => sort === 'ev' ? (b.ev ?? -9) - (a.ev ?? -9) : sort === 'conf' ? (b.confidence ?? b.p * 100) - (a.confidence ?? a.p * 100) : b.p - a.p;
  const filtered = useMemo(() => {
    const out: Array<{ m: Match; ps: Prediction[] }> = [];
    for (const m of matches) {
      if (!passM(m)) continue;
      const ps = m.predictions.filter(passP).sort(sort === 'time' ? (a, b) => Number(isRecommended(b)) - Number(isRecommended(a)) || Number(!!b.is_pick) - Number(!!a.is_pick) || Number(b.odds != null) - Number(a.odds != null) || b.p - a.p : sortP);
      const noFilter = group === 'all' && minP <= 0.5 && !onlyValue && !onlyRec && !grades.length && !onlyWithOdds;
      if (!ps.length && !(noFilter && q && !m.predictions.length)) continue;
      out.push({ m, ps });
    }
    const key = (x: { m: Match; ps: Prediction[] }) => x.ps[0];
    if (sort === 'time') out.sort((a, b) => Number(isFinished(a.m.status)) - Number(isFinished(b.m.status)) || a.m.kickoff_utc.localeCompare(b.m.kickoff_utc));
    else out.sort((a, b) => { const pa = key(a), pb = key(b); if (!pa) return 1; if (!pb) return -1; return sortP(pa, pb); });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matches, group, minP, minOdds, maxOdds, onlyValue, onlyRec, onlyWithOdds, grades, league, status, slot, q, sort, settingsMin]);

  const flat = useMemo(() => filtered.flatMap(({ m, ps }) => ps.map((p) => ({ m, p }))).sort((a, b) => sort === 'time' ? a.m.kickoff_utc.localeCompare(b.m.kickoff_utc) : sortP(a.p, b.p)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filtered, sort]);
  const nPred = flat.length;
  const nRec = flat.filter((x) => isRecommended(x.p)).length;
  const nActive = [group !== 'all', minP !== 0.5, minOdds !== settingsMin, maxOdds < 10, onlyValue, onlyRec, onlyWithOdds, grades.length > 0, !!league, status !== 'all', slot !== 'all'].filter(Boolean).length;
  const reset = () => { setGroup('all'); setMinP(0.5); setMinOdds(settingsMin); setMaxOdds(10); setOnlyValue(false); setOnlyRec(false); setOnlyWithOdds(false); setGrades([]); setLeague(''); setStatus('all'); setSlot('all'); };

  const filterBody = (
    <div className="space-y-4 md:space-y-3">
      <div>
        <div className="mb-1.5 text-xs font-semibold text-muted-foreground md:hidden">Piață</div>
        <div className="flex flex-wrap gap-1.5">
          {MARKET_GROUPS.map((m) => <button key={m.id} className={cn('chip', group === m.id && 'chip-on')} onClick={() => setGroup(m.id)}>{m.label}</button>)}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <button className={cn('chip', onlyRec && 'chip-on')} onClick={() => setOnlyRec(!onlyRec)} title={`p ≥ ${REC.minP * 100}%, EV > 0, cotă ${REC.minOdds}–${REC.maxOdds}, grad A/B`}>Doar recomandate</button>
        <button className={cn('chip', onlyValue && 'chip-on')} onClick={() => setOnlyValue(!onlyValue)}>Doar EV &gt; 0</button>
        <button className={cn('chip', onlyWithOdds && 'chip-on')} onClick={() => setOnlyWithOdds(!onlyWithOdds)}>Doar cu cotă</button>
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
          <div className="mt-1 flex gap-1.5">{['A', 'B', 'C', 'D'].map((x) => <button key={x} className={cn('chip min-w-[44px] justify-center', grades.includes(x) && 'chip-on')} onClick={() => setGrades(grades.includes(x) ? grades.filter((y) => y !== x) : [...grades, x])}>{x}</button>)}</div>
        </div>
      </div>
      <select aria-label="Ligă" className="input md:hidden" value={league} onChange={(e) => setLeague(e.target.value)}>
        <option value="">Toate ligile ({leagues.length})</option>
        {leagues.map((l) => <option key={l} value={l}>{l}</option>)}
      </select>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented size="sm" value={status} onChange={setStatus} options={[{ value: 'all', label: 'Toate' }, { value: 'upcoming', label: 'Nejucate' }, { value: 'done', label: 'Terminate' }]} />
        <Segmented size="sm" value={slot} onChange={setSlot} options={[{ value: 'all', label: 'Orice oră' }, { value: 'am', label: '< 12' }, { value: 'pm', label: '12–18' }, { value: 'eve', label: '> 18' }]} />
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="flex items-center gap-2"><ListChecks className="h-5 w-5 text-primary" />Predicțiile zilei</h1>
          <p className="text-sm capitalize text-muted-foreground">{longDay(date)} · ora României</p>
        </div>
        <Segmented value={view} onChange={setView} size="sm" options={[{ value: 'match', label: 'Pe meci' }, { value: 'flat', label: 'Listă selecții' }]} />
      </div>

      <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 scrollbar-none md:mx-0 md:px-0">
        {strip.map((d) => (
          <button key={d} onClick={() => setDate(d)} className={cn('chip shrink-0', d === date && 'chip-on', !available.has(d) && d !== date && 'opacity-50')}>
            {dayLabel(d)}
          </button>
        ))}
        <label className="chip shrink-0 cursor-pointer"><CalendarDays className="h-3.5 w-3.5" />
          <input type="date" aria-label="Alege data" className="w-[110px] bg-transparent text-xs outline-none" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </label>
      </div>

      <div className="sticky top-14 z-20 -mx-4 border-b bg-background/95 px-4 py-2 backdrop-blur md:static md:mx-0 md:border-0 md:bg-transparent md:p-0">
        <div className="card flex items-center gap-2 border-0 bg-transparent p-0 shadow-none md:border md:bg-card md:p-3 md:shadow-sm">
          <div className="relative min-w-0 flex-1">
            <Search className="absolute left-2.5 top-3 h-4 w-4 text-muted-foreground" />
            <input className="input pl-8" aria-label="Caută echipă sau ligă" placeholder="Caută echipă sau ligă…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select aria-label="Ligă" className="input hidden w-auto md:block" value={league} onChange={(e) => setLeague(e.target.value)}>
            <option value="">Toate ligile ({leagues.length})</option>
            {leagues.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <select className="input w-[112px] md:w-auto" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sortare">
            <option value="time">Oră</option><option value="p">Probabilitate</option><option value="ev">EV</option><option value="conf">Încredere</option>
          </select>
          <button className="btn btn-outline relative md:hidden" onClick={() => setSheet(true)} aria-label="Filtre"><SlidersHorizontal className="h-4 w-4" />{nActive > 0 && <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">{nActive}</span>}</button>
        </div>
        <div className="mt-2 flex gap-1.5 overflow-x-auto scrollbar-none md:hidden">
          <button className={cn('chip shrink-0', onlyRec && 'chip-on')} onClick={() => setOnlyRec(!onlyRec)}>Recomandate</button>
          {MARKET_GROUPS.slice(0, 6).map((m) => <button key={m.id} className={cn('chip shrink-0', group === m.id && 'chip-on')} onClick={() => setGroup(m.id)}>{m.label}</button>)}
        </div>
      </div>
      <div className="card hidden p-3 md:block">{filterBody}</div>
      <BottomSheet open={sheet} onClose={() => setSheet(false)} title="Filtre"
        footer={<div className="flex gap-2"><button className="btn btn-outline flex-1" onClick={reset}>Resetează</button><button className="btn btn-primary flex-1" onClick={() => setSheet(false)}>Arată {nPred} predicții</button></div>}>
        {filterBody}
      </BottomSheet>

      {day.data?._source === 'legacy' && <Notice tone="warn">Pipeline-ul nou nu a publicat încă <code>api/days/{date}.json</code>; afișez predicțiile din fișierele vechi (v2). Cotele lipsă apar ca „fără cotă” și nu intră în bilete.</Notice>}

      <div className="flex flex-wrap gap-2 text-xs">
        <Badge tone="outline">{filtered.length} meciuri</Badge>
        <Badge tone="outline">{nPred} predicții</Badge>
        <Badge tone="win" title={`p ≥ ${REC.minP * 100}%, EV > 0, cotă ${REC.minOdds}–${REC.maxOdds}, grad A/B`}>{nRec} recomandate</Badge>
        <span className="hidden text-muted-foreground sm:inline">recomandat = p ≥ {REC.minP * 100}%, EV &gt; 0, cotă {REC.minOdds}–{REC.maxOdds}, grad A/B</span>
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
        <div className="text-center"><button className="btn btn-outline w-full md:w-auto" onClick={() => setLimit(limit + 40)}>Arată mai multe</button></div>
      )}
      <p className="text-center text-[11px] text-muted-foreground">Toate orele sunt în ora României. Datele zilei {roDay(day.data?.generated_at ?? '') ? `generate ${new Date(day.data!.generated_at!).toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest' })}` : ''}</p>
    </div>
  );
}
