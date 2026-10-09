import { useMemo, useState } from 'react';
import { BarChart3, Download, Lightbulb, Brain, Search } from 'lucide-react';
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell, ComposedChart, Area, ReferenceLine, ScatterChart, Scatter, ZAxis, Legend,
} from 'recharts';
import { useAsync } from '@/lib/fetcher';
import { loadStats, loadJournalRows, loadTicketsHistory, loadTickets, loadPyramid } from '@/lib/data';
import { TicketSection, sourceLabel, pyramidDaysSummary } from '@/components/StatsSections';
import { useStore } from '@/lib/store';
import { useSettledTickets } from '@/lib/hooks';
import { addDays, todayRo, pct, signed, num, monthLabel, odds as fo } from '@/lib/format';
import { block, series, groups, calibration, equity, recommendations, oddsBand, simulatePyramid } from '@/lib/analytics';
import { marketTitle } from '@/lib/markets';
import { Card, Loading, Empty, Segmented, Stat, Badge, ResultBadge, Notice } from '@/components/kit';
import type { JournalRow, StatBlock, Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';
import { STATS_SINCE } from '@/lib/rules';


type Tab = 'sumar' | 'zi' | 'luna' | 'eveniment' | 'calibrare' | 'bilete' | 'piramida' | 'robot';
type Period = '7' | '30' | '90' | 'all' | 'custom';
const tip = { contentStyle: { background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', fontSize: 12, borderRadius: 8 } };

function BlockTable({ rows, title }: { rows: StatBlock[]; title: string }) {
  if (!rows.length) return null;
  return (
    <Card className="overflow-hidden">
      <h3 className="p-3 text-sm font-semibold">{title}</h3>
      <div className="overflow-x-auto"><table className="w-full text-sm">
        <thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">Grup</th><th className="text-right">n</th><th className="text-right">Câștig</th><th className="text-right">Cotă medie</th><th className="text-right">Profit (u)</th><th className="px-3 text-right">ROI</th></tr></thead>
        <tbody>{rows.slice(0, 25).map((b) => (
          <tr key={b.key} className="border-t"><td className="max-w-[200px] truncate px-3 py-1.5">{b.name ?? b.key}</td><td className="text-right">{b.n}</td><td className="text-right">{pct(b.win_rate)}</td><td className="text-right">{fo(b.avg_odds)}</td>
            <td className={cn('text-right', b.profit >= 0 ? 'text-win' : 'text-loss')}>{signed(b.profit, 2)}</td><td className={cn('px-3 text-right font-semibold', (b.roi_pct ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{signed(b.roi_pct, 1, '%')}</td></tr>
        ))}</tbody></table></div>
    </Card>
  );
}

function Heatmap({ rows }: { rows: StatBlock[] }) {
  const t = todayRo();
  const days = Array.from({ length: 56 }, (_, i) => addDays(t, i - 55));
  const map = new Map(rows.map((r) => [r.key!, r]));
  return (
    <div className="grid grid-cols-7 gap-1 sm:grid-cols-14">
      {days.map((d) => { const r = map.get(d); const p = r?.profit ?? 0; const a = Math.min(1, Math.abs(p) / 5);
        return <div key={d} title={`${d}: ${r ? `${r.n} selecții, profit ${p.toFixed(2)}u` : 'fără date'}`} className="aspect-square rounded" style={{ background: !r ? 'hsl(var(--muted))' : p >= 0 ? `rgba(16,185,129,${0.2 + a * 0.8})` : `rgba(244,63,94,${0.2 + a * 0.8})` }} />; })}
    </div>
  );
}

function download(name: string, text: string, type: string) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export default function StatsPage() {
  const minOdds = useStore((s) => s.settings.minOdds);
  const stats = useAsync(loadStats, []);
  const journal = useAsync(() => loadJournalRows(minOdds, 60), [minOdds]);
  const myTickets = useStore((s) => s.myTickets);
  const robotLogAll = useStore((s) => s.robotLog);
  const pyramidLogAll = useStore((s) => s.pyramidLog);
  // doar Robotul 3.0, de la STATS_SINCE (fără istoricul vechi)
  const robotLog = useMemo(() => Object.fromEntries(Object.entries(robotLogAll).filter(([d]) => d >= STATS_SINCE)), [robotLogAll]);
  const pyramidLog = useMemo(() => Object.fromEntries(Object.entries(pyramidLogAll).filter(([d]) => d >= STATS_SINCE)), [pyramidLogAll]);
  const withdrawals = useStore((s) => s.withdrawals);
  const robotArchive = useStore((s) => s.robotArchive);
  const apiHist = useAsync(async () => {
    const [h, t, pyr] = await Promise.all([loadTicketsHistory(), loadTickets(todayRo()), loadPyramid()]);
    return { tickets: [...(t?.tickets ?? []), ...h], pyramid: pyr };
  }, []);
  const rules = useStore((s) => s.settings.pyramid);
  const [tab, setTab] = useState<Tab>('sumar');
  const [period, setPeriod] = useState<Period>('all');
  const [from, setFrom] = useState(() => { const d = addDays(todayRo(), -30); return d < STATS_SINCE ? STATS_SINCE : d; });
  const [to, setTo] = useState(todayRo());
  const [market, setMarket] = useState('');
  const [league, setLeague] = useState('');
  const [band, setBand] = useState('');
  const [pMin, setPMin] = useState(0);
  const [q, setQ] = useState('');

  const all = journal.data?.rows ?? [];
  const rows = useMemo(() => {
    const t = todayRo();
    const lo = period === 'custom' ? from : period === 'all' ? '0000' : addDays(t, -Number(period));
    const hi = period === 'custom' ? to : '9999';
    return all.filter((r) => r.date >= lo && r.date <= hi && (!market || r.market === market) && (!league || r.league === league) && (!band || oddsBand(r.odds) === band) && (r.p == null ? pMin === 0 : r.p >= pMin));
  }, [all, period, from, to, market, league, band, pMin]);
  const settled = rows.filter((r) => r.result !== 'pending');
  const overall = block(rows);
  const daily = useMemo(() => series(rows, 'day'), [rows]);
  const monthly = useMemo(() => series(rows, 'month'), [rows]);
  const eq = useMemo(() => equity(rows), [rows]);
  const byMarket = useMemo(() => groups(rows, (r) => r.market, marketTitle), [rows]);
  const byLeague = useMemo(() => groups(rows, (r) => r.league), [rows]);
  const byBand = useMemo(() => groups(rows, (r) => oddsBand(r.odds)).sort((a, b) => a.key!.localeCompare(b.key!)), [rows]);
  const bySource = useMemo(() => groups(rows, (r) => r.source ?? '—'), [rows]);
  const cal = useMemo(() => stats.data?.calibration ?? calibration(settled, (r) => r.market), [stats.data, settled]);
  const calAll = useMemo(() => calibration(settled)[0], [settled]);

  const allTickets: Ticket[] = useMemo(() => [...myTickets, ...Object.values(robotLog).flat()], [myTickets, robotLog]);
  const settledTickets = useSettledTickets(allTickets);
  const pyrSim = useMemo(() => simulatePyramid(Object.values(pyramidLog), rules, withdrawals), [pyramidLog, rules, withdrawals]);
  // ── Bilete acumulator: pipeline (server) + generate în aplicație (arhivă) + manuale; doar Robot 3.0 din STATS_SINCE
  const accaRaw: Ticket[] = useMemo(() => {
    const map = new Map<string, Ticket>();
    for (const t of apiHist.data?.tickets ?? []) if (t.kind?.startsWith('acca_') && (t.date ?? '') >= STATS_SINCE) map.set(`api-${t.id}`, t);
    for (const t of robotArchive) if ((t.date ?? '') >= STATS_SINCE && t.kind?.startsWith('acca_')) map.set(String(t.id), t);
    for (const t of myTickets) { if (t.followed || (t.created_by && t.created_by !== 'user')) continue; const d = t.date ?? t.created_at?.slice(0, 10) ?? ''; if (d >= STATS_SINCE) map.set(`my-${t.id}`, { ...t, date: d, created_by: 'user' }); }
    return [...map.values()];
  }, [apiHist.data, robotArchive, myTickets]);
  const accaSettled = useSettledTickets(accaRaw);
  // ── Piramidă: tichetele oficiale (principal) + propunerile locale pentru zilele fără date oficiale
  const pyrRaw: Ticket[] = useMemo(() => {
    const map = new Map<string, Ticket>();
    for (const t of apiHist.data?.tickets ?? []) if (t.kind === 'pyramid' && (t.variant ?? 'principal') === 'principal' && (t.date ?? '') >= STATS_SINCE) map.set(t.date!, t);
    const main = apiHist.data?.pyramid?.today?.main; if (main && (main.date ?? '') >= STATS_SINCE) map.set(main.date!, main);
    for (const r of Object.values(pyramidLog)) if (r.status === 'pick' && r.legs?.length && !map.has(r.date)) map.set(r.date, { id: `local-pyr-${r.date}`, kind: 'pyramid', date: r.date, total_odds: r.odds ?? 0, legs: r.legs, status: r.result === 'won' || r.result === 'lost' || r.result === 'void' ? r.result : 'pending', created_by: 'robot', variant_label: 'Principal' });
    return [...map.values()];
  }, [apiHist.data, pyramidLog]);
  const pyrSettled = useSettledTickets(pyrRaw);
  const pyrDays = useMemo(() => {
    const rows = new Map<string, { date: string; status: string }>();
    for (const r of apiHist.data?.pyramid?.history ?? []) if (r.date >= STATS_SINCE) rows.set(r.date, r);
    for (const r of Object.values(pyramidLog)) if (!rows.has(r.date)) rows.set(r.date, r);
    return pyramidDaysSummary([...rows.values()] as never);
  }, [apiHist.data, pyramidLog]);

  const recs = useMemo(() => {
    const local = recommendations(settled, { tickets: settledTickets.tickets, withdrawals, pyramidRuns: pyrSim.runs.length - 1 });
    return [...(stats.data?.summary?.recommendations ?? []), ...local];
  }, [settled, settledTickets.tickets, withdrawals, pyrSim.runs.length, stats.data]);

  const markets = [...new Set(all.map((r) => r.market))].sort();
  const leagues = [...new Set(all.map((r) => r.league ?? '—'))].sort((a, b) => a.localeCompare(b, 'ro'));
  const events = useMemo(() => {
    const g = new Map<number, JournalRow[]>();
    for (const r of rows) if (!q || `${r.match} ${r.league}`.toLowerCase().includes(q.toLowerCase())) g.set(r.match_id, [...(g.get(r.match_id) ?? []), r]);
    return [...g.values()].sort((a, b) => b[0].date.localeCompare(a[0].date)).slice(0, 80);
  }, [rows, q]);

  const exportCsv = () => {
    const head = 'zi,meci,liga,piata,selectie,cota,probabilitate,rezultat,profit,sursa,scor';
    const lines = rows.map((r) => [r.date, r.match, r.league, r.market, r.label, r.odds, r.p ?? '', r.result, r.profit ?? '', r.source ?? '', r.score ?? ''].map((x) => `"${String(x).replace(/"/g, '""')}"`).join(','));
    download(`betpredict-statistici-${todayRo()}.csv`, [head, ...lines].join('\n'), 'text/csv');
  };

  const official = stats.data?.summary;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="flex items-center gap-2"><BarChart3 className="h-5 w-5 text-primary" />Statistici</h1>
          <p className="text-sm text-muted-foreground">Toate predicțiile afișate sunt salvate automat și decontate după meci. ROI la miză de 1 unitate pe selecție.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-outline" onClick={exportCsv} disabled={!rows.length}><Download className="h-4 w-4" />CSV</button>
          <button className="btn btn-outline" onClick={() => download(`betpredict-statistici-${todayRo()}.json`, JSON.stringify(rows, null, 1), 'application/json')} disabled={!rows.length}><Download className="h-4 w-4" />JSON</button>
        </div>
      </div>

      <Segmented value={tab} onChange={setTab} className="w-full" options={[
        { value: 'sumar', label: 'Predicții' }, { value: 'zi', label: 'Pe zi' }, { value: 'luna', label: 'Pe lună' }, { value: 'eveniment', label: 'Pe eveniment' },
        { value: 'bilete', label: 'Bilete' }, { value: 'piramida', label: 'Piramidă' }, { value: 'calibrare', label: 'Calibrare' }, { value: 'robot', label: 'Robotul' },
      ]} />

      {['sumar', 'zi', 'luna', 'eveniment', 'calibrare'].includes(tab) && <Card className="flex flex-wrap items-end gap-2 p-3">
        <Segmented size="sm" value={period} onChange={setPeriod} options={[{ value: '7', label: '7 zile' }, { value: '30', label: '30 zile' }, { value: '90', label: '90 zile' }, { value: 'all', label: 'Tot' }, { value: 'custom', label: 'Interval' }]} />
        {period === 'custom' && <><input type="date" className="input w-auto" value={from} onChange={(e) => setFrom(e.target.value)} /><input type="date" className="input w-auto" value={to} onChange={(e) => setTo(e.target.value)} /></>}
        <select className="input w-auto" value={market} onChange={(e) => setMarket(e.target.value)}><option value="">Toate piețele</option>{markets.map((m) => <option key={m} value={m}>{marketTitle(m)}</option>)}</select>
        <select className="input w-auto max-w-[180px]" value={league} onChange={(e) => setLeague(e.target.value)}><option value="">Toate ligile</option>{leagues.map((l) => <option key={l} value={l}>{l}</option>)}</select>
        <select className="input w-auto" value={band} onChange={(e) => setBand(e.target.value)}><option value="">Orice cotă</option>{['1.00–1.30', '1.30–1.50', '1.50–1.80', '1.80–2.20', '2.20–3.00', '3.00+'].map((b) => <option key={b}>{b}</option>)}</select>
        <label className="text-xs text-muted-foreground">Prob. ≥ {Math.round(pMin * 100)}%<input type="range" min={0} max={0.9} step={0.05} value={pMin} onChange={(e) => setPMin(Number(e.target.value))} className="block w-28" /></label>
      </Card>}

      <Notice>Se numără <b>doar predicțiile publicate de Robotul 3.0</b> începând cu {STATS_SINCE.split('-').reverse().join('.')}. Istoricul vechi/importat (v2) este exclus.</Notice>

      {journal.loading ? <Loading /> : (
        <>
          {tab === 'sumar' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
                <Stat label="Selecții decontate" value={overall.n} sub={`${overall.pending} în așteptare`} />
                <Stat label="Rată de câștig" value={pct(overall.win_rate, 1)} sub={`${overall.won}V / ${overall.lost}Î${overall.void ? ` / ${overall.void} anulate` : ''}`} />
                <Stat label="ROI" value={signed(overall.roi_pct, 1, '%')} tone={(overall.roi_pct ?? 0) >= 0 ? 'win' : 'loss'} />
                <Stat label="Profit" value={`${signed(overall.profit, 2)} u`} tone={overall.profit >= 0 ? 'win' : 'loss'} />
                <Stat label="Cotă medie" value={fo(overall.avg_odds)} sub={`prob. medie ${pct(overall.avg_p)}`} />
                <Stat label="Brier" value={num(overall.brier, 3)} sub="mai mic = mai bine" />
              </div>
              {official && <Notice>Sumar oficial pipeline: {official.overall.n} selecții, rată {pct(official.overall.win_rate, 1)}, ROI {signed(official.overall.roi_pct, 1, '%')}{official.recommended?.n ? ` · recomandate: ${official.recommended.n}, ROI ${signed(official.recommended.roi_pct, 1, '%')}` : ''}.</Notice>}
              <div className="grid gap-4 lg:grid-cols-2">
                <Card className="p-4"><h3 className="mb-2 text-sm font-semibold">Profit cumulat (equity) și drawdown</h3>
                  {eq.length < 2 ? <p className="text-sm text-muted-foreground">Date insuficiente.</p> : <div className="h-56 md:h-64"><ResponsiveContainer><ComposedChart data={eq}><CartesianGrid strokeDasharray="3 3" opacity={0.2} /><XAxis dataKey="key" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><Tooltip {...tip} /><ReferenceLine y={0} stroke="#888" /><Area dataKey="dd" name="drawdown" fill="#f43f5e33" stroke="#f43f5e" /><Line dataKey="cum" name="profit cumulat" stroke="#10b981" dot={false} strokeWidth={2} /></ComposedChart></ResponsiveContainer></div>}
                </Card>
                <Card className="p-4"><h3 className="mb-2 text-sm font-semibold">ROI pe piață</h3>
                  <div className="h-56 md:h-64"><ResponsiveContainer><BarChart data={byMarket.filter((b) => b.n >= 3)} layout="vertical" margin={{ left: 0, right: 8 }}><CartesianGrid strokeDasharray="3 3" opacity={0.2} /><XAxis type="number" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} width={84} /><Tooltip {...tip} formatter={(v: number) => `${v.toFixed(1)}%`} /><ReferenceLine x={0} stroke="#888" /><Bar dataKey="roi_pct" name="ROI">{byMarket.filter((b) => b.n >= 3).map((b) => <Cell key={b.key} fill={(b.roi_pct ?? 0) >= 0 ? '#10b981' : '#f43f5e'} />)}</Bar></BarChart></ResponsiveContainer></div>
                </Card>
                <Card className="p-4"><h3 className="mb-2 text-sm font-semibold">Distribuția cotelor (rată de câștig și ROI pe interval)</h3>
                  <div className="h-56 md:h-64"><ResponsiveContainer><ComposedChart data={byBand.map((b) => ({ ...b, wr: (b.win_rate ?? 0) * 100 }))}><CartesianGrid strokeDasharray="3 3" opacity={0.2} /><XAxis dataKey="key" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><YAxis yAxisId="l" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><YAxis yAxisId="r" orientation="right" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 11 }} /><Bar yAxisId="l" dataKey="n" name="selecții" fill="#6366f1" /><Line yAxisId="r" dataKey="roi_pct" name="ROI %" stroke="#f59e0b" /><Line yAxisId="r" dataKey="wr" name="câștig %" stroke="#10b981" /></ComposedChart></ResponsiveContainer></div>
                </Card>
                <Card className="p-4">
                  <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Lightbulb className="h-4 w-4 text-warn" />Recomandări de îmbunătățire</h3>
                  <ul className="space-y-2">{recs.slice(0, 10).map((r, i) => (
                    <li key={i} className={cn('rounded-lg border px-3 py-2 text-sm', r.severity === 'critical' ? 'border-rose-500/40 bg-loss' : r.severity === 'warn' ? 'border-amber-500/40 bg-warn' : 'bg-muted/40')}>{r.text}</li>
                  ))}</ul>
                </Card>
              </div>
              <div className="grid gap-4 lg:grid-cols-2"><BlockTable rows={byLeague} title="Pe ligă" /><BlockTable rows={bySource} title="Pe sursă / strategie" /></div>
            </div>
          )}

          {tab === 'zi' && (
            <div className="space-y-4">
              <Card className="p-4"><h3 className="mb-2 text-sm font-semibold">Calendar ultimele 8 săptămâni (verde = profit, roșu = pierdere)</h3><Heatmap rows={daily} /></Card>
              <Card className="p-4"><h3 className="mb-2 text-sm font-semibold">Profit pe zi (unități)</h3>
                <div className="h-56 md:h-64"><ResponsiveContainer><BarChart data={daily.slice(-60)}><CartesianGrid strokeDasharray="3 3" opacity={0.2} /><XAxis dataKey="key" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><Tooltip {...tip} /><ReferenceLine y={0} stroke="#888" /><Bar dataKey="profit" name="profit">{daily.slice(-60).map((d) => <Cell key={d.key} fill={d.profit >= 0 ? '#10b981' : '#f43f5e'} />)}</Bar></BarChart></ResponsiveContainer></div>
              </Card>
              <BlockTable rows={[...daily].reverse()} title="Tabel pe zile" />
            </div>
          )}

          {tab === 'luna' && (
            <div className="space-y-4">
              <Card className="p-4"><h3 className="mb-2 text-sm font-semibold">ROI și rata de câștig pe lună</h3>
                <div className="h-64"><ResponsiveContainer><ComposedChart data={monthly.map((m) => ({ ...m, label: monthLabel(m.key), wr: (m.win_rate ?? 0) * 100 }))}><CartesianGrid strokeDasharray="3 3" opacity={0.2} /><XAxis dataKey="label" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><YAxis yAxisId="l" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><YAxis yAxisId="r" orientation="right" domain={[0, 100]} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 11 }} /><ReferenceLine yAxisId="l" y={0} stroke="#888" />
                  <Bar yAxisId="l" dataKey="roi_pct" name="ROI %">{monthly.map((m) => <Cell key={m.key} fill={(m.roi_pct ?? 0) >= 0 ? '#10b981' : '#f43f5e'} />)}</Bar><Line yAxisId="r" dataKey="wr" name="câștig %" stroke="#6366f1" /></ComposedChart></ResponsiveContainer></div>
              </Card>
              <BlockTable rows={[...monthly].reverse().map((m) => ({ ...m, name: monthLabel(m.key) }))} title="Tabel pe luni" />
            </div>
          )}

          {tab === 'eveniment' && (
            <div className="space-y-3">
              <div className="relative"><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><input className="input pl-8" placeholder="Caută meci sau ligă…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
              {!events.length ? <Empty title="Nicio selecție în perioada aleasă" /> : events.map((ev) => {
                const b = block(ev);
                return (
                  <Card key={ev[0].match_id} className="p-3">
                    <div className="flex flex-wrap items-center gap-2"><b className="text-sm">{ev[0].match}</b><span className="text-xs text-muted-foreground">{ev[0].date} · {ev[0].league}</span>{ev[0].score && <Badge tone="outline">scor {ev[0].score}</Badge>}
                      <span className={cn('ml-auto text-sm font-semibold', b.profit >= 0 ? 'text-win' : 'text-loss')}>{signed(b.profit, 2)} u</span></div>
                    <ul className="mt-1 divide-y text-sm">{ev.map((r, i) => <li key={i} className="flex items-center gap-2 py-1"><span className="flex-1">{r.label}</span><span className="text-xs text-muted-foreground">{r.p != null ? pct(r.p) : ''}</span><span className="w-12 text-right">{fo(r.odds)}</span><ResultBadge r={r.result} /></li>)}</ul>
                  </Card>
                );
              })}
            </div>
          )}

          {tab === 'calibrare' && (
            <div className="space-y-4">
              <Card className="p-4">
                <h3 className="mb-1 text-sm font-semibold">Diagrama de calibrare — prezis vs. real</h3>
                <p className="mb-2 text-xs text-muted-foreground">Punctele pe diagonală = probabilități corecte. Sub diagonală = Robotul supraestimează.</p>
                {!calAll ? <p className="text-sm text-muted-foreground">Date insuficiente.</p> : (
                  <div className="h-72"><ResponsiveContainer><ScatterChart margin={{ left: 0 }}><CartesianGrid strokeDasharray="3 3" opacity={0.2} /><XAxis type="number" dataKey="p_avg" name="prezis" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><YAxis type="number" dataKey="hit_rate" name="real" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><ZAxis dataKey="n" range={[40, 400]} /><Tooltip {...tip} formatter={(v: number, n: string) => (n === 'n' ? v : `${(v * 100).toFixed(1)}%`)} />
                    <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#888" strokeDasharray="4 4" /><Scatter data={calAll.bins} fill="#10b981" /></ScatterChart></ResponsiveContainer></div>
                )}
              </Card>
              <Card className="overflow-hidden"><h3 className="p-3 text-sm font-semibold">Calibrare pe piață (ECE)</h3>
                <table className="w-full text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">Piață</th><th className="text-right">n</th><th className="text-right">ECE</th><th className="px-3 text-right">Stare</th></tr></thead>
                  <tbody>{cal.map((c) => <tr key={c.key} className="border-t"><td className="px-3 py-1.5">{marketTitle(c.key)}</td><td className="text-right">{c.n}</td><td className="text-right">{num(c.ece, 3)}</td><td className="px-3 text-right"><Badge tone={c.n < 20 ? 'muted' : c.healthy ? 'win' : 'loss'}>{c.n < 20 ? 'eșantion mic' : c.healthy ? 'sănătoasă' : 'necalibrată'}</Badge></td></tr>)}</tbody></table>
              </Card>
            </div>
          )}

          {tab === 'bilete' && (
            <TicketSection tickets={accaSettled.tickets} empty="Încă nu există bilete acumulator salvate (Robot 3.0)"
              groupTitle="Pe tip de bilet · variantă · sursă"
              groupKey={(t) => `${t.kind.startsWith('acca_') ? `~${t.kind.slice(5)}` : t.kind} · ${t.variant_label ?? t.variant ?? '—'} · ${sourceLabel(t)}`}
              extra={official?.tickets?.length ? <BlockTable title="Bilete Robot (pipeline, decontate pe server)" rows={official.tickets.filter((t) => t.kind.startsWith('acca_')).map((t) => ({ key: `${t.kind} · ${t.variant ?? ''}`, n: t.n, won: t.won, lost: t.lost, win_rate: t.won + t.lost ? t.won / (t.won + t.lost) : null, roi_pct: t.roi_pct, profit: t.profit }))} /> : null} />
          )}

          {tab === 'piramida' && (
            <TicketSection tickets={pyrSettled.tickets} empty="Încă nu există propuneri de piramidă salvate (Robot 3.0)"
              groupTitle="Pe număr de selecții" groupKey={(t) => `${t.legs.length} ${t.legs.length === 1 ? 'meci' : 'meciuri'}`}
              extra={<div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
                <Stat label="Zile urmărite" value={pyrDays.days} sub={`${pyrDays.picks} cu pariu · ${pyrDays.noBet} „AZI NU”`} />
                <Stat label="Run-uri (simulare)" value={pyrSim.runs.length} sub={`cel mai bun pas: ${Math.max(0, ...pyrSim.runs.map((r) => r.steps))}`} />
                <Stat label="Pași câștigați" value={pyrSim.steps.filter((x) => x.result === 'won').length} sub={`${pyrSim.steps.filter((x) => x.result === 'lost').length} pierduți`} />
                <Stat label="Total retras" value={`${pyrSim.totalWithdrawn.toFixed(2)} lei`} tone={pyrSim.totalWithdrawn > 0 ? 'win' : undefined} />
              </div>} />
          )}

          {tab === 'robot' && (
            <div className="space-y-4">
              {!stats.data?.learning ? (
                <Empty title="Raportul de învățare nu e publicat încă" icon={<Brain className="h-6 w-6" />}>
                  Robotul se reantrenează săptămânal (luni). Raportul (<code>api/stats/learning.json</code>) arată ponderile pe piață, piețele excluse și testul walk-forward. Până atunci, recomandările de mai jos sunt calculate în aplicație din rezultate.
                </Empty>
              ) : (
                <>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Stat label="Model activ" value={stats.data.learning.model?.version ?? '—'} sub={stats.data.learning.model?.trained_at ? `antrenat ${stats.data.learning.model.trained_at.slice(0, 10)}` : ''} />
                    <Stat label="Meciuri în antrenare" value={stats.data.learning.model?.matches?.toLocaleString('ro-RO') ?? '—'} />
                    <Stat label="Piețe excluse din bilete" value={stats.data.learning.params?.excluded_markets?.length ?? 0} sub={(stats.data.learning.params?.excluded_markets ?? []).map(marketTitle).join(', ')} />
                  </div>
                  {stats.data.learning.walk_forward?.length ? (
                    <Card className="p-4"><h3 className="mb-2 text-sm font-semibold">Walk-forward: LogLoss model vs. bază (mai mic = mai bine)</h3>
                      <div className="h-56 md:h-64"><ResponsiveContainer><LineChart data={stats.data.learning.walk_forward}><CartesianGrid strokeDasharray="3 3" opacity={0.2} /><XAxis dataKey="fold" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} domain={['auto', 'auto']} /><Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 11 }} />
                        <Line dataKey="logloss_1x2" name="1X2 model" stroke="#10b981" /><Line dataKey="baseline_1x2" name="1X2 bază" stroke="#10b981" strokeDasharray="4 4" /><Line dataKey="logloss_ou25" name="O/U 2.5 model" stroke="#6366f1" /><Line dataKey="baseline_ou25" name="O/U 2.5 bază" stroke="#6366f1" strokeDasharray="4 4" /></LineChart></ResponsiveContainer></div>
                    </Card>
                  ) : null}
                  <Card className="overflow-hidden"><h3 className="p-3 text-sm font-semibold">Jurnal de învățare</h3>
                    <ul className="divide-y text-sm">{(stats.data.learning.log ?? []).slice(0, 40).map((l, i) => <li key={i} className="px-3 py-2"><div className="flex gap-2"><Badge tone="primary">{l.change_type}</Badge>{l.market && <span>{marketTitle(l.market)}</span>}<span className="ml-auto text-xs text-muted-foreground">{l.run_at?.slice(0, 10)}</span></div><div className="text-xs text-muted-foreground">{String(l.before ?? '')} → {String(l.after ?? '')}</div></li>)}</ul>
                  </Card>
                </>
              )}
              <Card className="p-4"><h3 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Lightbulb className="h-4 w-4 text-warn" />Tipare detectate în rezultate</h3>
                <ul className="space-y-2">{recs.map((r, i) => <li key={i} className="rounded-lg bg-muted/40 px-3 py-2 text-sm">{r.text}</li>)}</ul>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
}
