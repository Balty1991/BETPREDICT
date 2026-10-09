import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { Bot, RefreshCw, Wand2, Ticket as TicketIcon, Triangle, ListChecks, History, Info, Star } from 'lucide-react';
import { useDays, useSettledTickets, usePersistMySettlement } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadTickets, loadTicketsHistory } from '@/lib/data';
import { useStore, actions } from '@/lib/store';
import { addDays, todayRo, odds as fo, pct } from '@/lib/format';
import { buildPool, generateAccumulators, beamSearch, makeTicket, TARGETS, VARIANTS, pyramidSelect, type Candidate } from '@/lib/robot';
import { Card, Segmented, Loading, Empty, Notice, Stat, SectionTitle } from '@/components/kit';
import { TicketCard } from '@/components/TicketCard';
import type { Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { PredLine } from '@/components/MatchCard';
import { isRecommended, REC } from '@/lib/rules';

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
    <Card className="p-4">
      <h3 className="mb-3 flex items-center gap-2 font-semibold"><Wand2 className="h-4 w-4 text-primary" />Generator cu regulile tale</h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="text-xs text-muted-foreground">Cotă țintă<input type="number" min={1.5} step={1} className="input mt-1" value={target} onChange={(e) => setTarget(Math.max(1.5, Number(e.target.value) || 2))} /></label>
        <label className="text-xs text-muted-foreground">Min. meciuri<input type="number" min={1} max={20} className="input mt-1" value={nMin} onChange={(e) => setNMin(Number(e.target.value) || 1)} /></label>
        <label className="text-xs text-muted-foreground">Max. meciuri<input type="number" min={1} max={20} className="input mt-1" value={nMax} onChange={(e) => setNMax(Number(e.target.value) || 1)} /></label>
        <label className="text-xs text-muted-foreground">Piețe<select className="input mt-1" value={markets} onChange={(e) => setMarkets(e.target.value as 'all')}><option value="all">Toate</option><option value="goals">Doar goluri</option><option value="results">Doar rezultat (1X2/DC/DNB)</option></select></label>
        <label className="text-xs text-muted-foreground">Prob. minimă / selecție: <b className="text-foreground">{Math.round(minP * 100)}%</b><input type="range" min={0.4} max={0.9} step={0.05} className="mt-2 w-full" value={minP} onChange={(e) => setMinP(Number(e.target.value))} /></label>
      </div>
      <button className="btn btn-primary mt-3" onClick={run}><Bot className="h-4 w-4" />Generează</button>
      {err && <p className="mt-2 text-sm text-warn">{err}</p>}
      {res && <div className="mt-3"><TicketCard t={res} /></div>}
    </Card>
  );
}

export default function HomePage() {
  const today = todayRo();
  const [win, setWin] = useState<Win>('today');
  const dates = useMemo(() => (win === 'today' ? [today] : win === '48h' ? [today, addDays(today, 1)] : [today, addDays(today, 1), addDays(today, 2)]), [win, today]);
  const days = useDays(dates);
  const apiTickets = useAsync(() => loadTickets(today), [today]);
  const history = useAsync(loadTicketsHistory, []);
  const settings = useStore((s) => s.settings);
  const robotLog = useStore((s) => s.robotLog);
  const myTickets = useStore((s) => s.myTickets);
  const [target, setTarget] = useState<number>(50);
  const [local, setLocal] = useState<Ticket[] | null>(null);

  const pool = useMemo(() => (days.data ? buildPool(days.data.filter(Boolean) as never, { minOdds: settings.minOdds, allowEstimated: settings.allowEstimatedOdds }) : []), [days.data, settings.minOdds, settings.allowEstimatedOdds]);

  // Generare automată (când serverul n-a publicat biletele zilei) + salvare automată locală.
  useEffect(() => {
    if (!days.data || apiTickets.loading || apiTickets.data) return;
    const logged = robotLog[today];
    if (logged?.length && win === 'today') { setLocal(logged); return; }
    if (!settings.autoTickets && win === 'today') { setLocal(logged ?? []); return; }
    const t = generateAccumulators(pool, today);
    setLocal(t);
    if (win === 'today' && t.length) actions.logRobotTickets(today, t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days.data, apiTickets.loading, apiTickets.data, pool]);

  const regenerate = () => {
    const prev = new Set((local ?? []).flatMap((t) => t.legs.map((l) => String(l.prediction_id))));
    const ban = new Set([...prev].filter(() => Math.random() < 0.35));
    const t = generateAccumulators(pool, today, { seedBan: ban });
    setLocal(t);
    if (t.length) { actions.logRobotTickets(today, t, true); toast.success(`Robotul a generat ${t.length} bilete noi`); }
    else toast.error('Nu sunt destule selecții eligibile pentru bilete noi.');
  };

  const tickets = local ?? apiTickets.data?.tickets ?? [];
  const byTarget = tickets.filter((t) => (t.target_odds ?? 0) === target || t.kind === `acca_${target}`);
  const settledToday = useSettledTickets(tickets);
  const settledMap = new Map(settledToday.tickets.map((t) => [t.id, t]));

  const mySettled = useSettledTickets(myTickets);
  usePersistMySettlement(mySettled.tickets, myTickets);
  const active = mySettled.tickets.filter((t) => t.status === 'pending' || !t.status);
  const done = mySettled.tickets.filter((t) => t.status && t.status !== 'pending').slice(0, 10);

  const pastRobot = useMemo(() => {
    const api = history.data ?? [];
    if (api.length) return api.slice(0, 12);
    return Object.entries(robotLog).filter(([d]) => d < today).sort((a, b) => b[0].localeCompare(a[0])).flatMap(([, ts]) => ts).slice(0, 12);
  }, [history.data, robotLog, today]);
  const pastSettled = useSettledTickets(pastRobot);

  const allToday = days.data?.[0]?.matches ?? [];
  const nPred = allToday.reduce((a, m) => a + m.predictions.length, 0);
  const recToday = useMemo(() => allToday.filter((m) => m.status === 'notstarted').flatMap((m) => m.predictions.filter(isRecommended).map((p) => ({ m, p })))
    .sort((a, b) => b.p.p - a.p.p).filter((x, i, arr) => arr.findIndex((y) => y.m.id === x.m.id) === i), [allToday]);
  const pyr = useMemo(() => (days.data ? pyramidSelect(buildPool([days.data[0]].filter(Boolean) as never, { minOdds: settings.minOdds, allowEstimated: false }), today) : null), [days.data, settings.minOdds, today]);

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
        <Stat label="Meciuri azi" value={allToday.length || '—'} sub={<Link to="/predictii" className="text-primary hover:underline">vezi predicțiile →</Link>} />
        <Stat label="Predicții publicate" value={nPred || '—'} sub={`${recToday.length} meciuri cu recomandare`} />
        <Stat label="Selecții eligibile bilete" value={pool.length || '—'} sub={`cotă ≥ ${settings.minOdds.toFixed(2)}, cote ${settings.allowEstimatedOdds ? 'reale + estimate' : 'reale'}`} />
        <Link to="/piramida" className="card block p-3 hover:bg-accent/30 md:p-4">
          <div className="label flex items-center gap-1"><Triangle className="h-3.5 w-3.5" />Piramida azi</div>
          {!pyr ? <div className="mt-1 text-xl font-bold">—</div> : pyr.status === 'pick' && pyr.main ? (
            <><div className="mt-0.5 text-xl font-bold text-primary">{fo(pyr.main.total_odds)}</div><div className="text-xs text-muted-foreground">{pyr.main.legs.length} meciuri · p ≈ {pct(pyr.main.p_ticket)}</div></>
          ) : <><div className="mt-0.5 text-xl font-bold text-warn">AZI NU</div><div className="text-xs text-muted-foreground">pauză recomandată</div></>}
        </Link>
      </section>

      <section>
        <SectionTitle icon={<Star className="h-5 w-5 text-primary" />} title="Recomandările zilei"
          subtitle={`Conservator: p ≥ ${REC.minP * 100}%, EV > 0, cotă ${REC.minOdds}–${REC.maxOdds}, grad A/B. Cel mult una pe meci.`} />
        {recToday.length ? (
          <div className="card divide-y px-3">{recToday.slice(0, 8).map(({ m, p }) => <PredLine key={`${m.id}-${p.id}`} m={m} p={p} showMatch />)}</div>
        ) : <Notice>Azi nu există selecții care să treacă pragurile conservatoare. Mai bine pauză decât risc.</Notice>}
        {recToday.length > 8 && <Link to="/predictii" className="btn btn-outline mt-2 w-full">Toate cele {recToday.length} recomandări</Link>}
      </section>

      <section>
        <SectionTitle icon={<Bot className="h-5 w-5 text-primary" />} title="Biletele Robotului"
          subtitle={apiTickets.data ? 'Generate de pipeline la 03:15 (ora României), decontate automat.' : 'Generate în aplicație din predicțiile publicate și salvate automat pe acest dispozitiv.'}
          right={<button className="btn btn-outline" onClick={regenerate} disabled={!pool.length}><RefreshCw className="h-4 w-4" />Generează din nou</button>} />
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Segmented value={target} onChange={setTarget} options={TARGETS.map((t) => ({ value: t.target, label: t.target === 500 ? 'Cotă 500+' : `Cotă ~${t.target}` }))} />
          {!apiTickets.data && <Segmented size="sm" value={win} onChange={setWin} options={[{ value: 'today', label: 'Doar azi' }, { value: '48h', label: 'Azi + mâine' }, { value: '72h', label: '3 zile' }]} />}
        </div>
        <Notice><Info className="mr-1 inline h-3.5 w-3.5" />Șansă realistă pentru cota ~{target}: <b>{TARGETS.find((t) => t.target === target)?.realistic}</b>. Sunt „loterie cu fundament”, nu bilete sigure — mize mici și fixe.</Notice>
        <div className="mt-3">
          {days.loading || apiTickets.loading ? <Loading text="Robotul analizează meciurile…" /> : !byTarget.length ? (
            <Empty title="Niciun bilet pentru această țintă" icon={<TicketIcon className="h-6 w-6" />}>
              {pool.length < 6 ? `Sunt doar ${pool.length} selecții cu cotă reală ≥ ${settings.minOdds.toFixed(2)}. Extinde fereastra la „Azi + mâine” sau activează cotele estimate în Setări.` : 'Nu există o combinație care să atingă ținta cu regulile de diversificare. Încearcă „Azi + mâine”.'}
            </Empty>
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">{byTarget.map((t) => <TicketCard key={t.id} t={settledMap.get(t.id) ?? t} compact={false} />)}</div>
          )}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">Variante: {VARIANTS.map((v) => `${v.label} — ${v.describe}`).join(' · ')}</p>
      </section>

      <ManualGenerator pool={pool} date={today} />

      <section>
        <SectionTitle icon={<ListChecks className="h-5 w-5 text-primary" />} title="Biletele mele" subtitle="Bilete salvate sau construite manual. Rezultatele se actualizează automat după fiecare meci." />
        {!active.length && !done.length ? (
          <Empty title="Nu ai bilete salvate">Salvează un bilet al Robotului sau construiește unul din <Link to="/predictii" className="text-primary underline">Predicții</Link> cu butonul „+”.</Empty>
        ) : (
          <div className="space-y-4">
            {active.length > 0 && <div><h3 className="mb-2 text-sm font-semibold text-muted-foreground">În curs ({active.length})</h3><div className="grid gap-3 lg:grid-cols-2">{active.map((t) => <TicketCard key={t.id} t={t} saved compact onRemove={() => actions.removeTicket(t.id)} />)}</div></div>}
            {done.length > 0 && <div><h3 className="mb-2 text-sm font-semibold text-muted-foreground">Decontate recent</h3><div className="grid gap-3 lg:grid-cols-2">{done.map((t) => <TicketCard key={t.id} t={t} saved compact onRemove={() => actions.removeTicket(t.id)} />)}</div></div>}
          </div>
        )}
      </section>

      {pastSettled.tickets.length > 0 && (
        <section>
          <SectionTitle icon={<History className="h-5 w-5 text-primary" />} title="Biletele Robotului din zilele trecute" subtitle="Cu rezultatele decontate automat." />
          <div className="grid gap-3 lg:grid-cols-2">{pastSettled.tickets.map((t) => <TicketCard key={t.id} t={t} compact />)}</div>
        </section>
      )}
      <p className={cn('text-center text-[11px] text-muted-foreground')}>Probabilitatea biletului = produsul probabilităților (trase ușor spre piață) cu penalizare pentru selecții din aceeași ligă.</p>
    </div>
  );
}
