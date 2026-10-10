import { Carousel } from '@/components/Carousel';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { Bot, RefreshCw, Wand2, Ticket as TicketIcon, Triangle, ListChecks, History, Star, ChevronRight, Crosshair, Wallet, Blocks, LineChart } from 'lucide-react';
import { useDays, useSettledTickets, usePersistMySettlement } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadTickets, loadTicketsHistory, loadPyramid } from '@/lib/data';
import { useStore, actions } from '@/lib/store';
import { addDays, todayRo, odds as fo, pct, longDay, roTime, roDay } from '@/lib/format';
import { evAdj, buildPool, generateAccumulators, generateSafeTickets, isSafeTicket, beamSearch, makeTicket, TARGETS, pyramidSelect, type Candidate } from '@/lib/robot';
import { Segmented, Empty, Notice, SectionTitle, Skeleton, TeamLogo, ProbRing, ConfidenceChip, InfoTip, SafetyMeter } from '@/components/kit';
import { HorizonTickets } from '@/components/HorizonTickets';
import { Deferred } from '@/components/Deferred';
import { TicketCard } from '@/components/TicketCard';
import type { Ticket, Match, Prediction } from '@/lib/types';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { PredLine, OddsButton } from '@/components/MatchCard';
import { pickHint } from '@/lib/markets';
import { HELP, valueInfo } from '@/lib/ui';
import { isRecommended } from '@/lib/rules';

type Win = 'today' | '48h' | '72h';

function ManualGenerator({ pool, date }: { pool: Candidate[]; date: string }) {
  const [target, setTarget] = useState(20);
  const [nMin, setNMin] = useState(3);
  const [nMax, setNMax] = useState(8);
  const [markets, setMarkets] = useState<'all' | 'goals' | 'results'>('all');
  const [minP, setMinP] = useState(0.55);
  const [res, setRes] = useState<Ticket | null>(null);
  const [err, setErr] = useState('');
  const run = () => {
    const f = pool.filter((c) => c.pAdj >= minP * 0.9 && (markets === 'all' || (markets === 'goals' ? ['over_under', 'btts'].includes(c.p.market) : ['1x2', 'double_chance', 'draw_no_bet'].includes(c.p.market))));
    const legs = beamSearch(f, { min: target * 0.85, max: target * 1.25, nMin, nMax }, (c) => -c.lp / c.lo, new Set());
    if (!legs) { setRes(null); setErr('Nu am găsit o combinație cu aceste reguli. Mărește numărul de meciuri sau scade probabilitatea minimă.'); return; }
    setErr('');
    setRes(makeTicket(legs, { kind: 'manual_robot', variant: 'personalizat', variant_label: `Personalizat ~${target}`, target, date, created_by: 'robot', reasons: [`Reguli: ${nMin}–${nMax} meciuri, p ≥ ${Math.round(minP * 100)}%, ${markets === 'all' ? 'toate piețele' : markets === 'goals' ? 'doar goluri' : 'doar rezultat'}`] }));
  };
  return (
    <details className="card group p-4">
      <summary className="flex min-h-[44px] cursor-pointer list-none items-center gap-2 font-bold"><Wand2 className="h-4 w-4 text-primary" />Generator cu regulile tale<ChevronRight className="ml-auto h-4 w-4 text-muted-foreground transition-transform group-open:rotate-90" /></summary>
      <div className="mt-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="text-xs text-muted-foreground">Cotă țintă<input type="number" min={1.5} step={1} className="input mt-1" value={target} onChange={(e) => setTarget(Math.max(1.5, Number(e.target.value) || 2))} /></label>
        <label className="text-xs text-muted-foreground">Min. meciuri<input type="number" min={1} max={20} className="input mt-1" value={nMin} onChange={(e) => setNMin(Number(e.target.value) || 1)} /></label>
        <label className="text-xs text-muted-foreground">Max. meciuri<input type="number" min={1} max={20} className="input mt-1" value={nMax} onChange={(e) => setNMax(Number(e.target.value) || 1)} /></label>
        <label className="text-xs text-muted-foreground">Piețe<select className="input mt-1" value={markets} onChange={(e) => setMarkets(e.target.value as 'all')}><option value="all">Toate</option><option value="goals">Doar goluri</option><option value="results">Doar rezultat (1X2/DC/DNB)</option></select></label>
        <label className="text-xs text-muted-foreground">Șansă minimă / selecție: <b className="text-foreground">{Math.round(minP * 100)}%</b><input type="range" min={0.4} max={0.9} step={0.05} className="mt-2 w-full" value={minP} onChange={(e) => setMinP(Number(e.target.value))} /></label>
      </div>
      <button className="btn btn-primary mt-3" onClick={run}><Bot className="h-4 w-4" />Generează</button>
      {err && <p className="mt-2 text-sm text-warn">{err}</p>}
      {res && <div className="mt-3"><TicketCard t={res} /></div>}
      </div>
    </details>
  );
}

function HeroPick({ m, p }: { m: Match; p: Prediction }) {
  const v = valueInfo(p.ev);
  return (
    <article className="hero relative overflow-hidden rounded-3xl border p-4 shadow-lg">
      <Link to={`/meci/${m.id}?zi=${roDay(m.kickoff_utc)}`} className="block">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <TeamLogo src={m.league.logo} name={m.league.name} size={16} />
          <span className="min-w-0 flex-1 truncate">{m.league.country ? `${m.league.country} · ` : ''}{m.league.name}</span>
          <span className="rounded-full bg-card/70 px-2.5 py-0.5 text-sm font-bold tabular-nums text-foreground">{roTime(m.kickoff_utc)}</span>
        </div>
        <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-center">
          <div className="flex min-w-0 flex-col items-center gap-1.5"><TeamLogo src={m.home.logo} name={m.home.name} size={40} /><span className="line-clamp-2 text-sm font-bold leading-tight">{m.home.name}</span></div>
          <span className="text-xs font-semibold text-muted-foreground">vs</span>
          <div className="flex min-w-0 flex-col items-center gap-1.5"><TeamLogo src={m.away.logo} name={m.away.name} size={40} /><span className="line-clamp-2 text-sm font-bold leading-tight">{m.away.name}</span></div>
        </div>
      </Link>
      <div className="mt-4 flex items-center gap-3 rounded-2xl bg-card/80 p-3 backdrop-blur">
        <ProbRing p={p.p} size={54} stroke={5} label="Șansă" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><span className="text-xl font-extrabold leading-tight">{p.label}</span><ConfidenceChip grade={p.grade} compact /></div>
          <div className="truncate text-xs text-muted-foreground">{pickHint(p.market, p.line, p.selection, m.home.name, m.away.name)}</div>
          {v && <div className="mt-0.5 flex items-center text-xs text-muted-foreground">Valoare <b className={v.tone === 'win' ? 'ml-1 text-win' : 'ml-1 text-foreground'}>{v.text}</b><InfoTip text={HELP.value} label="Ce înseamnă valoarea?" /></div>}
          <SafetyMeter p={p} className="mt-2" />
        </div>
        <OddsButton m={m} p={p} />
      </div>
    </article>
  );
}

export default function HomePage() {
  const today = todayRo();
  const [win, setWin] = useState<Win>('today');
  const dates = useMemo(() => (win === 'today' ? [today] : win === '48h' ? [today, addDays(today, 1)] : [today, addDays(today, 1), addDays(today, 2)]), [win, today]);
  const days = useDays(dates);
  const apiTickets = useAsync(() => loadTickets(today), [today]);
  const history = useAsync(loadTicketsHistory, []);
  const apiPyr = useAsync(loadPyramid, []);
  const settings = useStore((s) => s.settings);
  const robotLog = useStore((s) => s.robotLog);
  const myTickets = useStore((s) => s.myTickets);
  const [local, setLocal] = useState<Ticket[] | null>(null);
  const [showAllRec, setShowAllRec] = useState(false);

  const pool = useMemo(() => (days.data ? buildPool(days.data.filter(Boolean) as never, { minOdds: settings.minOdds, allowEstimated: settings.allowEstimatedOdds }) : []), [days.data, settings.minOdds, settings.allowEstimatedOdds]);
  const safePool = useMemo(() => (days.data ? buildPool(days.data.filter(Boolean) as never, { minOdds: settings.minOdds, allowEstimated: false, includeUnhealthy: true }) : []), [days.data, settings.minOdds]);

  // Generare automată (când serverul n-a publicat biletele zilei) + salvare automată locală.
  useEffect(() => {
    if (!days.data || apiTickets.loading || apiTickets.data) return;
    const logged = robotLog[today];
    if (logged?.length && win === 'today') { setLocal(logged); return; }
    if (!settings.autoTickets && win === 'today') { setLocal(logged ?? []); return; }
    const t = [...generateSafeTickets(safePool, today), ...generateAccumulators(pool, today)];
    setLocal(t);
    if (win === 'today' && t.length) actions.logRobotTickets(today, t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days.data, apiTickets.loading, apiTickets.data, pool]);

  const regenerate = () => {
    const prev = new Set((local ?? []).flatMap((t) => t.legs.map((l) => String(l.prediction_id))));
    const ban = new Set([...prev].filter(() => Math.random() < 0.35));
    const acc = generateAccumulators(pool, today, { seedBan: ban });
    const t = [...generateSafeTickets(safePool, today, ban), ...acc];
    setLocal(t);
    if (acc.length) { actions.logRobotTickets(today, t, true); toast.success(`Robotul a generat ${acc.length} bilete noi cu valoare`); }
    else if (t.length) { actions.logRobotTickets(today, t, true); toast.message('Am reîmprospătat biletele sigure', { description: 'Azi nu există combinații noi cu valoare pozitivă la cotele mari — mai bine fără bilet decât unul în pierdere.' }); }
    else toast.message('Azi nu am găsit combinații noi cu valoare', { description: 'Biletele afișate rămân cele mai bune variante. Revino mai târziu — cotele se actualizează din oră în oră.' });
  };

  const tickets = (local ?? apiTickets.data?.tickets ?? []).filter((t) => t.variant !== 'multi_zi');
  const settledToday = useSettledTickets(tickets);
  const settledMap = new Map(settledToday.tickets.map((t) => [t.id, t]));

  const mySettled = useSettledTickets(myTickets);
  usePersistMySettlement(mySettled.tickets, myTickets);
  const active = mySettled.tickets.filter((t) => t.status === 'pending' || !t.status);
  const done = mySettled.tickets.filter((t) => t.status && t.status !== 'pending').slice(0, 10);

  const pastRobot = useMemo(() => {
    const api = (history.data ?? []).filter((t) => (t.date ?? '') < today);
    if (api.length) return api.slice(0, 12);
    return Object.entries(robotLog).filter(([d]) => d < today).sort((a, b) => b[0].localeCompare(a[0])).flatMap(([, ts]) => ts).slice(0, 12);
  }, [history.data, robotLog, today]);
  const pastSettled = useSettledTickets(pastRobot);

  const allToday = days.data?.[0]?.matches ?? [];
  const recToday = useMemo(() => allToday.filter((m) => m.status === 'notstarted').flatMap((m) => m.predictions.filter(isRecommended).map((p) => ({ m, p })))
    .sort((a, b) => b.p.p - a.p.p).filter((x, i, arr) => arr.findIndex((y) => y.m.id === x.m.id) === i), [allToday]);
  // piramida: datele publicate de pipeline (p, EV, miză); calcul local doar dacă lipsesc
  const pubPyr = apiPyr.data?.date === today ? apiPyr.data.today : null;
  const localPyr = useMemo(() => (pubPyr || apiPyr.loading ? null : days.data ? pyramidSelect(buildPool([days.data[0]].filter(Boolean) as never, { minOdds: settings.minOdds, allowEstimated: false }), today) : null), [days.data, settings.minOdds, today, pubPyr, apiPyr.loading]);
  const pyr = pubPyr ?? localPyr;
  const pyrStake = pubPyr?.main?.stake_units;

  const hero = recToday[0] ?? null;
  const ticketsByTarget = TARGETS.map((tg) => ({ tg, list: tickets.filter((t) => (t.target_odds ?? 0) === tg.target || t.kind === `acca_${tg.target}`) }));
  // ordinea: bilete de valoare/dublu (pariuri reale) → sigure (informativ) → loterie pe niveluri (~50 … ~2000)
  const rank = (t: (typeof tickets)[number]) => (t.kind === 'acca_value' ? 0 : t.kind === 'acca_double' ? 1 : isSafeTicket(t) ? 2 : 3);
  const orderedTickets = [...tickets].sort((a, b) => rank(a) - rank(b) || (a.target_odds ?? a.total_odds) - (b.target_odds ?? b.total_odds));
  const emptyTiers = ticketsByTarget.filter((x) => !x.list.length).map((x) => x.tg);
  const evPool = pool.filter((c) => !c.estimated && (c.p.grade === 'A' || c.p.grade === 'B') && evAdj(c) > 0).length;

  return (
    <div className="space-y-8">
      <section aria-labelledby="hero-title">
        <div className="mb-3 flex items-end justify-between gap-3">
          <div>
            <div className="eyebrow">{longDay(today)}</div>
            <h1 id="hero-title">Pontul zilei</h1>
          </div>
          <Link to="/predictii" className="text-sm font-semibold text-primary hover:underline">{allToday.length ? `${allToday.length} meciuri` : 'Meciuri'} →</Link>
        </div>
        {days.loading ? <Skeleton className="h-[282px] w-full rounded-3xl" /> : hero ? <HeroPick m={hero.m} p={hero.p} /> : (
          <div className="hero rounded-3xl border p-5">
            <div className="text-lg font-bold">Azi nu există un pont suficient de sigur</div>
            <p className="mt-1 text-sm text-muted-foreground">Nicio selecție nu trece pragurile prudente (șansă ≥ 60%, cotă 1.15–2.20, încredere mare/bună, valoare pozitivă). O zi de pauză e tot o decizie bună.</p>
          </div>
        )}
      </section>
      <nav aria-label="Instrumente pro" className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { to: '/edge', icon: <Crosshair className="h-5 w-5" />, t: 'Edge Board', d: 'EV × siguranță' },
          { to: '/edge?tab=banca', icon: <Wallet className="h-5 w-5" />, t: 'Banca', d: 'Kelly · expunere' },
          { to: '/builder', icon: <Blocks className="h-5 w-5" />, t: 'Bet Builder', d: 'experimental' },
          { to: '/statistici?tab=pro', icon: <LineChart className="h-5 w-5" />, t: 'Statistici Pro', d: 'bancă · CLV · calibrare' },
        ].map((x) => (
          <Link key={x.to} to={x.to} className="tile press card flex items-center gap-3 p-3.5 hover:border-primary/40">
            <span className="tile-icon grid h-10 w-10 shrink-0 place-items-center rounded-xl text-primary">{x.icon}</span>
            <span className="min-w-0"><span className="block truncate text-sm font-extrabold">{x.t}</span><span className="block truncate text-[11px] text-muted-foreground">{x.d}</span></span>
          </Link>
        ))}
      </nav>


      <Link to="/piramida" className="card card-hover flex items-center gap-3 p-4">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-info text-info"><Triangle className="h-5 w-5" /></span>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-bold">Piramida 2.00</div>
          <div className="min-h-[32px] text-xs text-muted-foreground">
            {!pyr ? 'Se încarcă…' : pyr.status === 'pick' && pyr.main
              ? `Azi: ${pyr.main.legs.length} ${pyr.main.legs.length === 1 ? 'meci' : 'meciuri'} · șansă ${pct(pyr.main.p_ticket)}${pyrStake != null ? ` · miză ${pyrStake}u` : ''}`
              : 'Azi: pauză — nicio combinație destul de bună'}
          </div>
        </div>
        {pyr?.status === 'pick' && pyr.main ? <div className="text-right"><div className="text-[11px] text-muted-foreground">cotă</div><div className="text-xl font-extrabold tabular-nums text-primary">{fo(pyr.main.total_odds)}</div></div>
          : pyr ? <span className="rounded-full bg-warn px-2.5 py-1 text-xs font-bold text-warn">AZI NU</span> : null}
        <ChevronRight className="h-5 w-5 text-muted-foreground" />
      </Link>

      <section aria-labelledby="tickets-title">
        <div className="mb-3 flex items-end justify-between gap-3">
          <div>
            <h2 id="tickets-title">Biletele Robotului</h2>
            <p className="text-xs text-muted-foreground">Bilete sigure (cote ~2/3/5) + bilete de valoare. Miza: 1u = 1% din bancă.</p>
          </div>
          <button className="btn btn-ghost h-10 w-10 shrink-0 p-0" onClick={regenerate} disabled={!pool.length} aria-label="Generează din nou biletele" title="Generează din nou"><RefreshCw className="h-4 w-4" /></button>
        </div>
        {days.loading || apiTickets.loading ? <div className="snap-row">{[0, 1].map((i) => <Skeleton key={i} className="h-[300px] w-[85%] max-w-[360px] shrink-0 rounded-2xl" />)}</div> : (
          <Carousel grid label="Bilete" className="items-start">
            {orderedTickets.map((t) => (
              <div key={t.id} className="w-[86%] max-w-[380px] shrink-0"><TicketCard t={settledMap.get(t.id) ?? t} compact /></div>
            ))}
          </Carousel>
        )}
        {!days.loading && !apiTickets.loading && emptyTiers.length > 0 && (
          <p className="card mt-3 flex items-start gap-2.5 p-3 text-xs text-muted-foreground">
            <TicketIcon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span><b className="text-foreground">Azi fără bilet la cota {emptyTiers.map((t) => `~${t.target}`).join(' / ')}</b> — doar {evPool} {evPool === 1 ? 'selecție are' : 'selecții au'} valoare pozitivă azi. Mai bine fără bilet decât unul în pierdere; vezi mai jos biletele pe 7 zile.</span>
          </p>
        )}
        {!apiTickets.data && <div className="mt-2"><Segmented size="sm" value={win} onChange={setWin} options={[{ value: 'today', label: 'Doar azi' }, { value: '48h', label: 'Azi + mâine' }, { value: '72h', label: '3 zile' }]} /></div>}
      </section>

      <Deferred minHeight={120}><HorizonTickets today={today} /></Deferred>

      <section aria-labelledby="rec-title">
        <div className="mb-2 flex items-end justify-between gap-3">
          <div>
            <h2 id="rec-title" className="flex items-center gap-1.5"><Star className="h-4 w-4 fill-current text-primary" />Recomandările zilei</h2>
            <p className="text-xs text-muted-foreground">Selecții prudente, cel mult una pe meci.</p>
          </div>
          {recToday.length > 5 && (
            <button type="button" className="text-sm font-semibold text-primary hover:underline" onClick={() => setShowAllRec((v) => !v)}>
              {showAllRec ? 'Mai puține' : `Toate (${recToday.length}) →`}
            </button>
          )}
        </div>
        {days.loading ? (
          <div className="card divide-y px-4" aria-busy="true">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="py-2.5"><Skeleton className="h-[52px] w-full" /></div>)}</div>
        ) : recToday.length > 1 ? (
          <div className="card divide-y px-4">{(showAllRec ? recToday.slice(1) : recToday.slice(1, 6)).map(({ m, p }) => <PredLine key={`${m.id}-${p.id}`} m={m} p={p} showMatch />)}</div>
        ) : <Notice>{hero ? 'Pontul zilei de mai sus este singura selecție care trece pragurile prudente azi.' : 'Azi nu există selecții care să treacă pragurile prudente. Mai bine pauză decât risc.'}</Notice>}
        {recToday.length > 5 && showAllRec && <p className="mt-2 text-center text-xs text-muted-foreground"><Link to="/predictii" className="font-semibold text-primary">Deschide lista completă în Predicții</Link></p>}
      </section>

      <section>
        <SectionTitle icon={<ListChecks className="h-5 w-5 text-primary" />} title="Biletele mele" subtitle="Bilete salvate sau construite manual. Rezultatele se actualizează automat după fiecare meci." />
        {!active.length && !done.length ? (
          <Empty title="Nu ai bilete salvate">Salvează un bilet al Robotului sau construiește unul din <Link to="/predictii" className="text-primary underline">Predicții</Link>, atingând cotele care îți plac.</Empty>
        ) : (
          <div className="space-y-4">
            {active.length > 0 && <div><h2 className="mb-2 text-sm font-semibold text-muted-foreground">În curs ({active.length})</h2><div className="grid gap-3 lg:grid-cols-2">{active.map((t) => <TicketCard key={t.id} t={t} saved compact onRemove={() => actions.removeTicket(t.id)} />)}</div></div>}
            {done.length > 0 && <div><h2 className="mb-2 text-sm font-semibold text-muted-foreground">Decontate recent</h2><div className="grid gap-3 lg:grid-cols-2">{done.map((t) => <TicketCard key={t.id} t={t} saved compact onRemove={() => actions.removeTicket(t.id)} />)}</div></div>}
          </div>
        )}
      </section>

      <ManualGenerator pool={pool} date={today} />

      {pastSettled.tickets.length > 0 && (
        <section>
          <SectionTitle icon={<History className="h-5 w-5 text-primary" />} title="Biletele Robotului din zilele trecute" subtitle="Cu rezultatele decontate automat." />
          <Carousel grid label="Bilete trecute">{pastSettled.tickets.map((t) => <div key={t.id} className="w-[86%] max-w-[380px] shrink-0"><TicketCard t={t} compact /></div>)}</Carousel>
        </section>
      )}
      <p className={cn('text-center text-[11px] text-muted-foreground')}>Șansa unui bilet = produsul șanselor prudente ale selecțiilor, cu penalizare pentru meciuri din aceeași ligă.</p>
    </div>
  );
}
