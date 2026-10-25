import { YourStake } from '@/components/YourStake';
import { weekSpent } from '@/lib/stake';
import { tip, activeDot } from '@/lib/chart';
import { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { ActionCard } from '@/components/PyramidAction';
import { Ban, Wallet, ArrowDownToLine, Settings2 } from 'lucide-react';
import { LazyChart } from '@/components/LazyChart';
import { useSettledTickets } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadPyramid, legacyPyramidHistory, loadDay, loadPyramidGrid } from '@/lib/data';
import type { PyramidGrid } from '@/components/Pyramid140View';
const GridCard = lazy(() => import('@/components/Pyramid140View').then((m) => ({ default: m.GridCard })));
import { useStore, actions } from '@/lib/store';
import { todayRo, lei, odds as fo, pct, dayLabel, roDateTime } from '@/lib/format';
import { buildPool, pyramidSelect } from '@/lib/robot';
import { simulatePyramid } from '@/lib/analytics';
import { Card, Loading, Stat, SectionTitle, Badge, Notice, PriceNote } from '@/components/kit';
const Pyramid140View = lazy(() => import('@/components/Pyramid140View'));
import { TicketCard, isLostTicket } from '@/components/TicketCard';
import { Deferred } from '@/components/Deferred';
import type { PyramidHistoryRow, Ticket } from '@/lib/types';
import type { PyrAction } from '@/components/PyramidAction';
import { cn } from '@/lib/utils';
import { PyrSelector } from '@/components/PyrSelector';
import { toast } from 'sonner';

export default function PyramidPage() {
  const [sp] = useSearchParams();
  const [track, setTrack] = useState<'2.00' | '1.20' | '1.40' | '1.60' | 'boost' | 'mici' | 'r5' | 'r10'>(() => { const q = sp.get('p'); return q === 'boost' ? 'boost' : q === '140' ? '1.40' : q === '120' ? '1.20' : q === '160' ? '1.60' : q === '200' ? '2.00' : q === 'r5' ? 'r5' : q === 'r10' ? 'r10' : q === 'mici' ? 'mici' : 'boost'; });
  return (
    <div className="space-y-4">
      <PyrSelector value={track} onChange={setTrack} />
      {(track === 'mici' || track === 'r5' || track === 'r10') && <PyrBudgetNote risk={track !== 'mici'} />}
      {track === '2.00' && <p className="card p-3 text-xs text-muted-foreground">Doar informativă: rămâne urmărită și decontată, ca să vedem dacă își revine.</p>}
      {(track === 'r5' || track === 'r10') && <p className="card p-3 text-xs text-muted-foreground"><b>Reguli noi din 25.10.</b> Cu 5–12 selecții la 1.15–1.40 a ieșit 1/8 (~5) și 0/8 (~10): marja casei se plătea la fiecare selecție. Acum: 2–4 selecții, cota ≥ 1.40 pe selecție, EV realist ≥ −3%, fără meciuri de noapte (00:00–07:00). Istoricul vechi rămâne în statistici. Pentru serii lungi: Piramida 1.20 și 1.40.</p>}
      {track === '2.00' ? <Pyramid200 /> : <Suspense fallback={<Loading />}><Pyramid140View key={track} track={track} /></Suspense>}
    </div>
  );
}

function Pyramid200() {
  const today = todayRo();
  const api = useAsync(loadPyramid, []);
  const grid = useAsync(loadPyramidGrid, []);
  const settings = useStore((s) => s.settings);
  // fallback local doar dacă pipeline-ul n-a publicat piramida (altfel nu descărcăm ziua întreagă / istoricul vechi)
  const needLocal = !api.loading && !api.data;
  const day = useAsync(() => (needLocal ? loadDay(today, settings.minOdds) : Promise.resolve(null)), [needLocal, today, settings.minOdds]);
  const legacyHist = useAsync(() => (needLocal ? legacyPyramidHistory() : Promise.resolve(null)), [needLocal]);
  const [histLimit, setHistLimit] = useState(30);
  const rules = settings.pyramid;
  const pyramidLog = useStore((s) => s.pyramidLog);
  const withdrawals = useStore((s) => s.withdrawals);
  const [wAmount, setWAmount] = useState<number>(0);
  const [showRules, setShowRules] = useState(false);

  const local = useMemo(() => {
    if (!day.data) return null;
    const pool = buildPool([day.data], { minOdds: settings.minOdds, allowEstimated: false });
    return pyramidSelect(pool, today, { band: api.data?.rules.band ?? [1.85, 2.2], maxLegs: api.data?.rules.max_legs ?? 4, minP: api.data?.rules.min_p ?? 0.5, minEv: api.data?.rules.min_ev ?? 0 });
  }, [day.data, settings.minOdds, today, api.data]);

  const proposal = api.data?.date === today && api.data?.today ? { ...api.data.today, main: api.data.today.main ?? null, alternatives: api.data.today.alternatives ?? [] } : local;

  // salvare automată a propunerii zilei (pentru istoricul local)
  useEffect(() => {
    if (!proposal || api.data) return;
    if (pyramidLog[today]) return;
    actions.logPyramid(today, proposal.status === 'pick' && proposal.main
      ? { date: today, status: 'pick', odds: proposal.main.total_odds, p: proposal.main.p_ticket, result: 'pending', label: proposal.main.legs.map((l) => `${l.home}–${l.away} ${l.label}`).join(' + '), legs: proposal.main.legs }
      : { date: today, status: 'no_bet', label: proposal.reason });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposal, api.data]);

  // decontarea propunerilor locale
  const logTickets: Ticket[] = useMemo(() => Object.values(pyramidLog).filter((r) => r.status === 'pick' && r.legs?.length).map((r) => ({ id: `pyr-${r.date}`, kind: 'pyramid', date: r.date, total_odds: r.odds ?? 0, legs: r.legs!, status: r.result === 'won' || r.result === 'lost' ? (r.result as 'won') : 'pending' })), [pyramidLog]);
  const settledLog = useSettledTickets(logTickets);
  useEffect(() => {
    for (const t of settledLog.tickets) {
      const row = pyramidLog[t.date!];
      if (row && t.status && t.status !== 'pending' && row.result !== t.status) actions.logPyramid(t.date!, { ...row, result: t.status === 'void' ? 'void' : t.status, legs: t.legs }, true);
    }
  }, [settledLog.tickets, pyramidLog]);

  const history: PyramidHistoryRow[] = useMemo(() => {
    if (api.data?.history?.length) return api.data.history;
    const map = new Map<string, PyramidHistoryRow>();
    for (const h of legacyHist.data?.history ?? []) if (h.date) map.set(h.date, h);
    for (const r of Object.values(pyramidLog)) map.set(r.date, r);
    return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [api.data, legacyHist.data, pyramidLog]);

  const sim = useMemo(() => simulatePyramid(history, rules, withdrawals), [history, rules, withdrawals]);
  const chart = sim.steps.filter((s) => s.status === 'pick').map((s) => ({ key: s.date, bancă: Math.round(s.bankAfter * 100) / 100, retras: Math.round(s.cumWithdrawn * 100) / 100 }));
  const pickToday = proposal?.status === 'pick' ? proposal.main : null;
  const nSteps = Math.min(9, Math.max(1, Number((api.data?.rules as { max_steps?: number } | undefined)?.max_steps) || 7));
  const theoretical = Array.from({ length: nSteps }, (_, i) => i + 1).map((k) => ({ k, p: Math.pow(pickToday?.p_ticket ?? 0.52, k) }));

  const withdraw = () => {
    if (!(wAmount > 0)) return;
    if (wAmount > sim.bank) { toast.error(`Poți retrage maxim ${lei(sim.bank)}`); return; }
    actions.addWithdrawal({ date: today, amount: wAmount });
    toast.success(`Retras ${lei(wAmount)} din piramidă`);
    setWAmount(0);
  };

  return (
    <div className="space-y-5">
      <section className="page-hero">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="eyebrow">Un bilet pe zi · cotă ~2.00</div>
            <h1 className="text-[22px] leading-tight">Piramida 2.00</h1>
          </div>
          <div className="slip-odds shrink-0 rounded-2xl px-3 py-2 text-center">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-primary-foreground/75">Azi</div>
            <div className="num text-[28px] font-extrabold leading-none text-primary-foreground">{pickToday ? fo(pickToday.total_odds) : 'Pauză'}</div>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center" aria-label="Ce faci azi">
          <div className="pyr-tile pyr-a rounded-xl bg-[hsl(var(--elevated))] px-1.5 py-2"><div className="text-[10px] font-bold uppercase text-muted-foreground">Treapta</div><div className="num mt-0.5 whitespace-nowrap text-base font-extrabold">{sim.step + 1}</div></div>
          <div className="pyr-tile pyr-b rounded-xl bg-[hsl(var(--elevated))] px-1.5 py-2"><div className="text-[10px] font-bold uppercase text-muted-foreground">Miza</div><div className="num mt-0.5 whitespace-nowrap text-base font-extrabold">{pickToday ? lei(sim.bank) : '—'}</div>{pickToday && <YourStake bank={sim.bank} />}</div>
          <div className="pyr-tile pyr-c rounded-xl bg-[hsl(var(--elevated))] px-1.5 py-2"><div className="text-[10px] font-bold uppercase text-muted-foreground">Dacă intră</div><div className={cn('num mt-0.5 whitespace-nowrap text-base font-extrabold', pickToday ? 'text-win' : 'text-muted-foreground')}>{pickToday ? lei(sim.bank * pickToday.total_odds) : 'pauză'}</div></div>
        </div>
        <ol className="relative mt-5 grid items-end gap-1.5" style={{ gridTemplateColumns: `repeat(${nSteps}, minmax(0, 1fr))` }} aria-label="Treptele piramidei">
          {theoretical.map(({ k, p }) => {
            const on = k === sim.step + 1, done = k <= sim.step;
            return (
              <li key={k} className="flex flex-col items-center gap-1">
                <span className="num text-[10px] text-muted-foreground">{pct(p)}</span>
                <span className={cn('pyr-step w-full rounded-t-lg', done ? 'pyr-done' : on ? 'pyr-on' : '')} style={{ height: `${14 + k * 9}px` }} />
                <span className={cn('num text-[11px] font-bold', on ? 'text-primary' : 'text-muted-foreground')}>{k}</span>
              </li>
            );
          })}
        </ol>
      </section>

      <ActionCard a={(api.data as { action?: PyrAction } | null)?.action} />
      <section>
        <SectionTitle title="Biletul de azi" subtitle={api.data ? `Generat automat${(api.data as { today?: { main?: { created_at?: string } }; generated_at?: string }).today?.main?.created_at || (api.data as { generated_at?: string }).generated_at ? ` la ${roDateTime((api.data as { today?: { main?: { created_at?: string } }; generated_at?: string }).today?.main?.created_at || (api.data as { generated_at?: string }).generated_at)}` : ''} (ora României)` : 'Calculat din predicțiile zilei și salvat automat'} />
        {api.loading || (needLocal && day.loading) ? <Loading /> : !proposal ? <Notice>Nu există date pentru azi.</Notice> : proposal.status === 'no_bet' ? (
          <Card className="flex items-start gap-3 border-amber-500/40 p-4">
            <Ban className="h-8 w-8 shrink-0 text-warn" />
            <div><div className="text-lg font-bold text-warn">AZI NU — pauză</div><p className="text-sm text-muted-foreground">{proposal.reason}</p><p className="mt-1 text-xs text-muted-foreground">O zi fără pariu nu strică piramida. Un pas forțat o poate termina.</p></div>
          </Card>
        ) : (
          <div className="space-y-3">
            {proposal.main && (isLostTicket(proposal.main) ? <Notice>Biletul de azi a pierdut. Rezultatul e în Statistici; mâine piramida reîncepe de la treapta 1.</Notice> : <><PriceNote ev={proposal.main.ev} /><TicketCard t={proposal.main} /></>)}
          </div>
        )}
      </section>

      <Deferred minHeight={900}>
      <section>
        <SectionTitle icon={<Wallet className="h-5 w-5 text-primary" />} title="Banca mea (simulare cu regulile tale)" right={<button className="btn btn-outline" onClick={() => setShowRules(!showRules)}><Settings2 className="h-4 w-4" />Reguli</button>} />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Sold curent (miza de azi)" value={lei(sim.bank)} sub={pickToday ? `dacă intră: ${lei(sim.bank * pickToday.total_odds)}` : 'pauză azi'} />
          <Stat label="Pas curent" value={sim.step} sub={`run #${sim.run}`} />
          <Stat label="Total retras (profit păstrat)" value={lei(sim.totalWithdrawn)} tone={sim.totalWithdrawn > 0 ? 'win' : undefined} />
          <Stat label="Rezultat net" value={lei(sim.totalWithdrawn + sim.bank - rules.startBank * sim.run)} tone={sim.totalWithdrawn + sim.bank - rules.startBank * sim.run >= 0 ? 'win' : 'loss'} sub={`${sim.run} run-uri × ${lei(rules.startBank)} investiți`} />
        </div>
        <Card className="mt-3 flex flex-wrap items-end gap-2 p-3">
          <label className="text-xs text-muted-foreground">Retragere manuală (lei)<input type="number" min={0} className="input mt-1 w-36" value={wAmount || ''} onChange={(e) => setWAmount(Number(e.target.value))} /></label>
          <button className="btn btn-primary" onClick={withdraw}><ArrowDownToLine className="h-4 w-4" />Retrage acum</button>
          <button className="btn btn-outline" onClick={() => setWAmount(Math.round(sim.bank * 0.5 * 100) / 100)}>50% din sold</button>
          {withdrawals.length > 0 && <div className="ml-auto text-xs text-muted-foreground">Retrageri manuale: {withdrawals.map((w, i) => <button key={i} className="ml-1 underline" title="Șterge" onClick={() => actions.removeWithdrawal(i)}>{dayLabel(w.date)} {lei(w.amount)}</button>)}</div>}
        </Card>
        {showRules && (
          <Card className="mt-3 grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-5">
            <label className="text-xs text-muted-foreground">Banca de start (lei)<input type="number" className="input mt-1" value={rules.startBank} onChange={(e) => actions.setPyramidRules({ startBank: Math.max(1, Number(e.target.value) || 1) })} /></label>
            <label className="text-xs text-muted-foreground">Retrage după pașii<input className="input mt-1" value={rules.withdrawSteps.join(',')} onChange={(e) => actions.setPyramidRules({ withdrawSteps: e.target.value.split(',').map((x) => Number(x.trim())).filter((x) => x > 0) })} /></label>
            <label className="text-xs text-muted-foreground">Procent retras la pas: {Math.round(rules.withdrawPct * 100)}%<input type="range" min={0} max={0.8} step={0.05} className="mt-2 w-full" value={rules.withdrawPct} onChange={(e) => actions.setPyramidRules({ withdrawPct: Number(e.target.value) })} /></label>
            <label className="text-xs text-muted-foreground">Țintă (× banca de start)<input type="number" className="input mt-1" value={rules.targetMultiple} onChange={(e) => actions.setPyramidRules({ targetMultiple: Math.max(2, Number(e.target.value) || 8) })} /></label>
            <label className="text-xs text-muted-foreground">Retras la țintă: {Math.round(rules.targetWithdrawPct * 100)}%<input type="range" min={0} max={1} step={0.05} className="mt-2 w-full" value={rules.targetWithdrawPct} onChange={(e) => actions.setPyramidRules({ targetWithdrawPct: Number(e.target.value) })} /></label>
          </Card>
        )}
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="p-4 lg:col-span-2">
          <h2 className="mb-2 font-semibold">Evoluția băncii și a retragerilor</h2>
          {chart.length < 2 ? <p className="text-sm text-muted-foreground">Graficul apare după primii pași decontați.</p> : (
            <LazyChart className="h-64">{(R) => <R.ResponsiveContainer>
              <R.AreaChart data={chart}><R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} /><R.XAxis dataKey="key" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.Tooltip {...tip} /><R.Legend wrapperStyle={{ fontSize: 12 }} />
                <R.Area activeDot={activeDot} type="monotone" dataKey="bancă" stroke="#2ee6a6" fill="#2ee6a633" /><R.Area activeDot={activeDot} type="monotone" dataKey="retras" stroke="#a78bfa" fill="#a78bfa33" />
              </R.AreaChart></R.ResponsiveContainer>}</LazyChart>
          )}
        </Card>
        <Card className="p-4">
          <h2 className="mb-2 font-semibold">Șansa de a ajunge la pasul k</h2>
          <table className="w-full text-sm"><thead><tr className="text-xs text-muted-foreground"><th className="text-left">Pas</th><th className="text-right">Teoretic</th><th className="text-right">Real (istoric)</th></tr></thead>
            <tbody>{theoretical.map(({ k, p }) => { const r = (api.data?.reach_probability ?? []).find((x) => x.step === k)?.p ?? sim.reach.find((x) => x.step === k)?.p; return (
              <tr key={k} className="border-t"><td className="py-1">{k}</td><td className="text-right">{pct(p, 1)}</td><td className="text-right">{r != null ? pct(r, 0) : '—'}</td></tr>); })}</tbody></table>
          <p className="mt-2 text-[11px] text-muted-foreground">Teoretic cu p={pct(pickToday?.p_ticket ?? 0.52)} pe pas. Retragerea parțială e singura parte care face strategia sustenabilă.</p>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <h2 className="p-3 font-semibold">Istoric zile</h2>
          <div className="max-h-96 overflow-y-auto">
            <table className="w-full text-sm"><thead className="sticky top-0 bg-card text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">Zi</th><th className="text-left">Selecție</th><th className="text-right">Cotă</th><th className="px-3 text-right">Rezultat</th></tr></thead>
              <tbody>{[...sim.steps].reverse().slice(0, histLimit).map((s, i) => (
                <tr key={i} className="border-t"><td className="px-3 py-1.5 text-xs">{s.date}</td><td className="max-w-[180px] truncate text-xs text-muted-foreground" title={s.label}>{s.label ?? (s.status === 'no_bet' ? 'AZI NU' : '—')}</td><td className="text-right">{fo(s.odds)}</td>
                  <td className="px-3 text-right"><Badge tone={s.result === 'won' ? 'win' : s.result === 'lost' ? 'loss' : s.result === 'pauză' ? 'warn' : 'muted'}>{s.result === 'won' ? `câștigat · pas ${s.step}` : s.result === 'lost' ? 'pierdut' : s.result}</Badge></td></tr>
              ))}</tbody></table>
            {sim.steps.length > histLimit && <div className="p-2 text-center"><button className="btn btn-outline w-full" onClick={() => setHistLimit(histLimit + 60)}>Arată mai multe zile</button></div>}
          </div>
        </Card>
        <Card className="overflow-hidden">
          <h2 className="p-3 font-semibold">Run-uri</h2>
          <div className="max-h-96 overflow-y-auto">
            <table className="w-full text-sm"><thead className="sticky top-0 bg-card text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">#</th><th className="text-left">Perioadă</th><th className="text-right">Pași</th><th className="text-right">Max</th><th className="px-3 text-right">Retras</th></tr></thead>
              <tbody>{sim.runs.map((r) => (
                <tr key={r.run} className="border-t"><td className="px-3 py-1.5">{r.run}</td><td className="text-xs text-muted-foreground">{r.start} → {r.end ?? 'acum'}</td><td className="text-right">{r.steps}</td><td className="text-right">{lei(r.maxBank)}</td><td className={cn('px-3 text-right', r.withdrawn > 0 && 'text-win')}>{lei(r.withdrawn)}</td></tr>
              ))}</tbody></table>
          </div>
        </Card>
      </section>
        <Suspense fallback={null}><GridCard grid={grid.data as PyramidGrid | null} /></Suspense>
      </Deferred>
      {!api.data && <Notice>Istoricul combină tracker-ul vechi (paper, cote ~1.30/pas) cu propunerile salvate local. După publicarea <code>api/pyramid/state.json</code>, istoricul oficial îl înlocuiește.</Notice>}
    </div>
  );
}

function PyrBudgetNote({ risk = false }: { risk?: boolean }) {
  const budget = useStore((s) => s.settings.weeklyBudget ?? 50);
  const spent = useStore((s) => weekSpent(s.myTickets, new Date(), s.settings.weeklyBudget ?? 50));
  if (!budget) return null;
  const left = Math.max(0, Math.round((budget - spent) * 100) / 100);
  const base = risk ? Math.min(2, Math.max(1, Math.round(budget / 50 * 2))) : Math.max(1, Math.round(5 * Math.max(0.2, budget / 50)));
  const start = Math.min(base, Math.floor(left));
  return (
    <p className="card p-3 text-xs">
      {start >= 1
        ? <>Miză la start: <b className="text-primary">{start} lei</b> · apoi rulezi câștigul pe trepte. Din bugetul săptămânii mai ai <b>{lei(left)}</b> (din {lei(budget)}).</>
        : <>Bugetul săptămânii e folosit: ai pus {lei(spent)} din {lei(budget)} pe biletele marcate „jucat”. Piramida pornește din nou de luni.</>}
    </p>
  );
}
