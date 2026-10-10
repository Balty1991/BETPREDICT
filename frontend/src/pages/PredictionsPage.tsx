import { Fragment, useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { SlidersHorizontal, Search, CalendarDays } from 'lucide-react';
import { useDay, useDays } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadDayIndex } from '@/lib/data';
import { useStore } from '@/lib/store';
import { addDays, todayRo, longDay, roDay } from '@/lib/format';
import { MARKET_GROUPS, isFinished } from '@/lib/markets';
import { Segmented, Loading, Empty, Notice, Sheet, InfoTip } from '@/components/kit';
import { confidence, isHighSafety, safetyOf } from '@/lib/ui';
import { isRecommended, REC } from '@/lib/rules';
import { MatchCard, PredLine } from '@/components/MatchCard';
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
  const [onlyWithOdds, setOnlyWithOdds] = useState(true); // implicit: doar selecții cu cotă reală
  const [grades, setGrades] = useState<string[]>([]);
  const [league, setLeague] = useState('');
  const [status, setStatus] = useState<Status>('all');
  const [slot, setSlot] = useState<Slot>('all');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<Sort>('time');
  const [view, setView] = useState<View>('match');
  const [limit, setLimit] = useState(12);
  const [sheet, setSheet] = useState(false);
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

  const sortP = (a: Prediction, b: Prediction) => Number(b.odds != null) - Number(a.odds != null) || (sort === 'safety' ? safetyOf(b) - safetyOf(a) : sort === 'ev' ? (b.ev ?? -9) - (a.ev ?? -9) : sort === 'conf' ? (b.confidence ?? b.p * 100) - (a.confidence ?? a.p * 100) : b.p - a.p);
  const filtered = useMemo(() => {
    const out: Array<{ m: Match; ps: Prediction[] }> = [];
    for (const m of matches) {
      if (!passM(m)) continue;
      const ps = m.predictions.filter(passP).sort(sort === 'time' ? (a, b) => Number(isRecommended(b)) - Number(isRecommended(a)) || Number(!!b.is_pick) - Number(!!a.is_pick) || Number(b.odds != null) - Number(a.odds != null) || b.p - a.p : sortP);
      const noFilter = group === 'all' && minP <= 0.5 && !onlyValue && !onlyRec && !onlySafe && !grades.length;
      if (!ps.length && !(noFilter && q && !m.predictions.length)) continue;
      out.push({ m, ps });
    }
    const key = (x: { m: Match; ps: Prediction[] }) => x.ps[0];
    const hasOdds = (x: { ps: Prediction[] }) => Number(x.ps[0]?.odds != null);
    if (sort === 'time') out.sort((a, b) => (isAll ? roDay(a.m.kickoff_utc).localeCompare(roDay(b.m.kickoff_utc)) : 0) || hasOdds(b) - hasOdds(a) || Number(isFinished(a.m.status)) - Number(isFinished(b.m.status)) || a.m.kickoff_utc.localeCompare(b.m.kickoff_utc));
    else out.sort((a, b) => { const pa = key(a), pb = key(b); if (!pa) return 1; if (!pb) return -1; return sortP(pa, pb); });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matches, isAll, group, minP, minOdds, maxOdds, onlyValue, onlyRec, onlySafe, onlyWithOdds, grades, league, status, slot, q, sort, settingsMin]);
  const nValue = useMemo(() => filtered.reduce((a, x) => a + x.ps.filter((p) => p.odds != null && (p.ev ?? -1) > 0).length, 0), [filtered]);

  const flat = useMemo(() => filtered.flatMap(({ m, ps }) => ps.map((p) => ({ m, p }))).sort((a, b) => sort === 'time' ? Number(b.p.odds != null) - Number(a.p.odds != null) || a.m.kickoff_utc.localeCompare(b.m.kickoff_utc) : sortP(a.p, b.p)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filtered, sort]);
  const nPred = flat.length;
  const nRec = flat.filter((x) => isRecommended(x.p)).length;
  const nActive = [group !== 'all', minP !== 0.5, minOdds !== settingsMin, maxOdds < 10, onlyValue, onlyRec, onlySafe, !onlyWithOdds, grades.length > 0, !!league, status !== 'all', slot !== 'all'].filter(Boolean).length;
  const reset = () => { setGroup('all'); setMinP(0.5); setMinOdds(settingsMin); setMaxOdds(10); setOnlyValue(false); setOnlyRec(false); setOnlySafe(false); setOnlyWithOdds(true); setGrades([]); setLeague(''); setStatus('all'); setSlot('all'); };

  const filterBody = (
    <div className="space-y-4 md:space-y-3">
      <div>
        <div className="mb-1.5 text-xs font-semibold text-muted-foreground md:hidden">Piață</div>
        <div className="flex flex-wrap gap-1.5">
          {MARKET_GROUPS.map((m) => <button key={m.id} className={cn('chip', group === m.id && 'chip-on')} onClick={() => setGroup(m.id)}>{m.label}</button>)}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <button className={cn('chip', onlyRec && 'chip-on')} onClick={() => setOnlyRec(!onlyRec)} title={`Șansă ≥ ${REC.minP * 100}%, valoare pozitivă, cotă ${REC.minOdds}–${REC.maxOdds}, încredere mare/bună`}>Doar recomandate</button>
        <button className={cn('chip', onlyValue && 'chip-on')} onClick={() => setOnlyValue(!onlyValue)}>Doar cu valoare</button>
        <button className={cn('chip', onlyWithOdds && 'chip-on')} onClick={() => setOnlyWithOdds(!onlyWithOdds)}>Doar cu cotă</button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-xs text-muted-foreground">Șansă minimă: <b className="text-foreground">{Math.round(minP * 100)}%</b>
          <input type="range" min={0.3} max={0.95} step={0.05} value={minP} onChange={(e) => setMinP(Number(e.target.value))} className="w-full" />
        </label>
        <label className="text-xs text-muted-foreground">Cotă minimă: <b className="text-foreground">{minOdds.toFixed(2)}</b>
          <input type="range" min={settingsMin} max={3} step={0.05} value={minOdds} onChange={(e) => setMinOdds(Number(e.target.value))} className="w-full" />
        </label>
        <label className="text-xs text-muted-foreground">Cotă maximă: <b className="text-foreground">{maxOdds >= 10 ? 'fără limită' : maxOdds.toFixed(2)}</b>
          <input type="range" min={1.3} max={10} step={0.1} value={maxOdds} onChange={(e) => setMaxOdds(Number(e.target.value))} className="w-full" />
        </label>
        <div className="text-xs text-muted-foreground">Încredere
          <div className="mt-1 flex flex-wrap gap-1.5">{['A', 'B', 'C', 'D'].map((x) => <button key={x} aria-pressed={grades.includes(x)} className={cn('chip justify-center', grades.includes(x) && 'chip-on')} onClick={() => setGrades(grades.includes(x) ? grades.filter((y) => y !== x) : [...grades, x])}>{confidence(x)!.short}</button>)}</div>
        </div>
      </div>
      <select aria-label="Ligă" className="input" value={league} onChange={(e) => setLeague(e.target.value)}>
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
      <section className="page-hero">
        <div className="relative flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="eyebrow">{isAll ? 'Toate zilele' : longDay(date)} · ora României</div>
            <h1>Predicții</h1>
          </div>
          <Segmented value={view} onChange={setView} size="sm" options={[{ value: 'match', label: 'Pe meci' }, { value: 'flat', label: 'Listă selecții' }]} />
        </div>
        <div className="relative mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="kpi"><div className="text-[11px] text-muted-foreground">Meciuri</div><div className="num text-xl font-extrabold">{filtered.length}<span className="text-xs text-muted-foreground">/{matches.length}</span></div></div>
          <div className="kpi"><div className="text-[11px] text-muted-foreground">Recomandate</div><div className="num text-xl font-extrabold text-primary">{nRec}</div></div>
          <div className="kpi"><div className="text-[11px] text-muted-foreground">Cu valoare (EV&gt;0)</div><div className="num text-xl font-extrabold">{nValue}</div></div>
          <div className="kpi"><div className="text-[11px] text-muted-foreground">Selecții afișate</div><div className="num text-xl font-extrabold">{nPred}</div></div>
        </div>
      </section>

      <div className="filter-bar sticky top-0 z-20 -mx-4 border-b px-4 pb-2 pt-2">
        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-2 scrollbar-none" role="group" aria-label="Alege ziua">
          <button aria-pressed={isAll} onClick={() => setDate(ALL)}
            className={cn('press flex min-h-[48px] shrink-0 flex-col items-center justify-center rounded-2xl border px-3 leading-tight transition-colors', isAll ? 'pill-on' : 'bg-card/70 hover:border-primary/40')}>
            <span className={cn('text-[11px] font-semibold uppercase tracking-wide', isAll ? 'text-primary-foreground/85' : 'text-muted-foreground')}>Toate</span>
            <span className="text-sm font-bold">zilele</span>
          </button>
          {strip.map((d) => { const on = !isAll && d === date; const [top, bottom] = dayPill(d, today); return (
            <button key={d} aria-pressed={on} onClick={() => setDate(d)}
              className={cn('flex min-h-[48px] min-w-[56px] shrink-0 flex-col items-center justify-center rounded-2xl border px-2.5 leading-tight transition-colors', on ? 'pill-on' : 'bg-card/70 hover:border-primary/40', !available.has(d) && !on && 'opacity-50')}>
              <span className={cn('text-[11px] font-semibold uppercase tracking-wide', on ? 'text-primary-foreground/85' : 'text-muted-foreground')}>{top}</span>
              <span className="text-sm font-bold tabular-nums">{bottom}</span>
            </button>); })}
          <label className="flex min-h-[48px] shrink-0 cursor-pointer items-center gap-1 rounded-2xl border bg-card px-2.5"><CalendarDays className="h-4 w-4 text-muted-foreground" />
            <input type="date" aria-label="Alege data" className="w-[112px] bg-transparent text-xs outline-none" value={isAll ? '' : date} onChange={(e) => e.target.value && setDate(e.target.value)} />
          </label>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <input className="input rounded-xl pl-9" aria-label="Caută echipă sau ligă" placeholder="Caută echipă, ligă…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select aria-label="Ligă" className="input hidden w-auto rounded-xl md:block" value={league} onChange={(e) => setLeague(e.target.value)}>
            <option value="">Toate ligile ({leagues.length})</option>
            {leagues.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <select className="input w-[120px] rounded-xl md:w-auto" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sortare">
            <option value="time">Oră</option><option value="p">Șansă</option><option value="ev">Valoare</option><option value="conf">Încredere</option><option value="safety">Siguranță</option>
          </select>
          <button className="btn btn-outline relative h-11 w-11 rounded-xl p-0" onClick={() => setSheet(true)} aria-label="Filtre"><SlidersHorizontal className="h-4 w-4" />{nActive > 0 && <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">{nActive}</span>}</button>
        </div>
        <div className="mt-2 flex gap-1.5 overflow-x-auto scrollbar-none">
          <button className={cn('chip shrink-0', onlyRec && 'chip-on')} aria-pressed={onlyRec} onClick={() => setOnlyRec(!onlyRec)}>★ Recomandate</button>
          <button className={cn('chip shrink-0', onlyWithOdds && 'chip-on')} aria-pressed={onlyWithOdds} onClick={() => setOnlyWithOdds(!onlyWithOdds)}>Doar cu cotă</button>
          <button className={cn('chip shrink-0', onlySafe && 'chip-on')} aria-pressed={onlySafe} onClick={() => setOnlySafe(!onlySafe)} title="Șansă ≥ 60% și încredere bună/mare">🛡 Siguranță mare</button>
          {MARKET_GROUPS.slice(0, 7).map((m) => <button key={m.id} className={cn('chip shrink-0', group === m.id && 'chip-on')} onClick={() => setGroup(m.id)}>{m.label}</button>)}
        </div>
      </div>
      <Sheet open={sheet} onClose={closeSheet} title="Filtre" subtitle={`${filtered.length} meciuri · ${nPred} selecții`}>
        {filterBody}
        <div className="sticky bottom-0 mt-4 flex gap-2 bg-card pt-2"><button className="btn btn-outline flex-1" onClick={reset}>Resetează</button><button className="btn btn-primary flex-1" onClick={closeSheet}>Arată {nPred} selecții</button></div>
      </Sheet>

      {day.data?._source === 'legacy' && <Notice tone="warn">Pipeline-ul nou nu a publicat încă <code>api/days/{date}.json</code>; afișez predicțiile din fișierele vechi (v2). Cotele lipsă apar ca „fără cotă” și nu intră în bilete.</Notice>}

      <div className="flex items-center gap-1 text-sm text-muted-foreground">
        <span><b className="text-foreground">{filtered.length}</b> meciuri · <b className="text-foreground">{nRec}</b> recomandate</span>
        <InfoTip text={`Recomandat = șansă ≥ ${REC.minP * 100}%, valoare pozitivă, cotă ${REC.minOdds}–${REC.maxOdds} și încredere mare sau bună.`} label="Ce înseamnă recomandat?" />
      </div>

      {loadingList ? <Loading /> : !matches.length ? (
        <Empty title="Nu există meciuri publicate pentru această zi" icon={<CalendarDays className="h-6 w-6" />}>Alege altă zi. Programul se publică pe ±7 zile.</Empty>
      ) : !filtered.length ? (
        <Empty title="Niciun rezultat cu filtrele curente">Scade probabilitatea minimă sau alege „Toate” la piață.</Empty>
      ) : view === 'match' ? (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
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
