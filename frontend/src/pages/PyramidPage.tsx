import { useEffect, useMemo, useState } from 'react';
import { Triangle, Ban, Wallet, ArrowDownToLine, Settings2 } from 'lucide-react';
import { LazyChart } from '@/components/LazyChart';
import { useSettledTickets } from '@/lib/hooks';
import { useAsync } from '@/lib/fetcher';
import { loadPyramid, legacyPyramidHistory, loadDay } from '@/lib/data';
import { useStore, actions } from '@/lib/store';
import { todayRo, lei, odds as fo, pct, dayLabel } from '@/lib/format';
import { buildPool, pyramidSelect } from '@/lib/robot';
import { simulatePyramid } from '@/lib/analytics';
import { Card, Loading, Stat, SectionTitle, Badge, Notice } from '@/components/kit';
import { TicketCard } from '@/components/TicketCard';
import { Deferred } from '@/components/Deferred';
import type { PyramidHistoryRow, Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

export default function PyramidPage() {
  const today = todayRo();
  const api = useAsync(loadPyramid, []);
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
  const theoretical = [1, 2, 3, 4, 5, 6, 7, 8].map((k) => ({ k, p: Math.pow(pickToday?.p_ticket ?? 0.52, k) }));

  const withdraw = () => {
    if (!(wAmount > 0)) return;
    if (wAmount > sim.bank) { toast.error(`Poți retrage maxim ${lei(sim.bank)}`); return; }
    actions.addWithdrawal({ date: today, amount: wAmount });
    toast.success(`Retras ${lei(wAmount)} din piramidă`);
    setWAmount(0);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2"><Triangle className="h-5 w-5 text-primary" />Piramida 2.00</h1>
        <p className="text-sm text-muted-foreground">Zilnic, 1–4 meciuri cu cota totală 1.85–2.20. Reinvestire totală, retrageri parțiale, iar când nu există o combinație bună — pauză.</p>
      </div>

      <section>
        <SectionTitle title="Propunerea zilei" subtitle={api.data ? 'Din pipeline (03:15, ora României)' : 'Calculată din predicțiile zilei; salvată automat în istoricul local'} />
        {api.loading || (needLocal && day.loading) ? <Loading /> : !proposal ? <Notice>Nu există date pentru azi.</Notice> : proposal.status === 'no_bet' ? (
          <Card className="flex items-start gap-3 border-amber-500/40 p-4">
            <Ban className="h-8 w-8 shrink-0 text-warn" />
            <div><div className="text-lg font-bold text-warn">AZI NU — pauză</div><p className="text-sm text-muted-foreground">{proposal.reason}</p><p className="mt-1 text-xs text-muted-foreground">O zi fără pariu nu strică piramida. Un pas forțat o poate termina.</p></div>
          </Card>
        ) : (
          <div className="space-y-3">
            {proposal.main && <TicketCard t={proposal.main} />}
            {proposal.alternatives?.length ? <div><h2 className="mb-2 text-sm font-semibold text-muted-foreground">Alternative</h2><div className="grid gap-3 lg:grid-cols-2">{proposal.alternatives.map((t) => <TicketCard key={t.id} t={t} compact />)}</div></div> : null}
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
              <R.AreaChart data={chart}><R.CartesianGrid strokeDasharray="3 3" opacity={0.2} /><R.XAxis dataKey="key" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', fontSize: 12 }} /><R.Legend wrapperStyle={{ fontSize: 12 }} />
                <R.Area type="monotone" dataKey="bancă" stroke="#10b981" fill="#10b98133" /><R.Area type="monotone" dataKey="retras" stroke="#6366f1" fill="#6366f133" />
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
      </Deferred>
      {!api.data && <Notice>Istoricul combină tracker-ul vechi (paper, cote ~1.30/pas) cu propunerile salvate local. După publicarea <code>api/pyramid/state.json</code>, istoricul oficial îl înlocuiește.</Notice>}
    </div>
  );
}
