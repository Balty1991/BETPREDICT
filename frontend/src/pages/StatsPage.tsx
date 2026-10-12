import { BuilderStats } from '@/components/BuilderStats';
import { PontStats } from '@/components/PontStats';
import { tip, activeDot } from '@/lib/chart';
import { useCallback, useMemo, useState } from 'react';
import { Download, Lightbulb, Search, SlidersHorizontal } from 'lucide-react';
import { LazyChart } from '@/components/LazyChart';
import { useAsync } from '@/lib/fetcher';
import { loadStats, loadJournalRows, loadTicketsHistory, loadTickets, loadPyramid } from '@/lib/data';
import { ProStats } from '@/components/ProStats';
import { RobotPanel } from '@/components/RobotPanel';
import { LabPanel } from '@/components/LabPanel';
import { BoostsPanel } from '@/components/BoostsPanel';
import { ClvCard, WeeklyPanel } from '@/components/WeeklyPanel';
import { StilLiveCard } from '@/components/LabPanel';
import { Pyramid140Stats } from '@/components/Pyramid140View';
import { TicketSection, TypeCards, ticketType, pyramidDaysSummary } from '@/components/StatsSections';
import { useStore } from '@/lib/store';
import { useSettledTickets } from '@/lib/hooks';
import { addDays, todayRo, pct, signed, num, monthLabel, odds as fo } from '@/lib/format';
import { block, series, groups, calibration, equity, recommendations, oddsBand, simulatePyramid } from '@/lib/analytics';
import { marketTitle } from '@/lib/markets';
import { Card, Loading, Empty, Segmented, Stat, Badge, ResultBadge, Notice, Sheet } from '@/components/kit';
import type { JournalRow, StatBlock, Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';
import { STATS_SINCE } from '@/lib/rules';


type Tab = 'pro' | 'sumar' | 'zi' | 'luna' | 'eveniment' | 'calibrare' | 'bilete' | 'piramida' | 'robot' | 'raport' | 'laborator' | 'bb' | 'boosts';
type Period = '7' | '30' | '90' | 'all' | 'custom';

const STAT_GROUPS: Array<{ id: string; label: string; hint: string; tabs: Array<{ value: Tab; label: string }> }> = [
  { id: 'rezultate', label: 'Rezultate', hint: 'Ce ar fi ieșit la 1 unitate pe fiecare predicție publicată. Verde = profit, roșu = pierdere.', tabs: [
    { value: 'sumar', label: 'Sumar' }, { value: 'zi', label: 'Pe zi' }, { value: 'luna', label: 'Pe lună' }, { value: 'eveniment', label: 'Pe meci' },
  ] },
  { id: 'bilete', label: 'Bilete', hint: 'Biletele jucate de Robot, piramida și cotele mărite. Se decontează singure, după fluierul final.', tabs: [
    { value: 'bilete', label: 'Toate' }, { value: 'piramida', label: 'Piramidă' }, { value: 'bb', label: 'Bet Builder' }, { value: 'boosts', label: 'Cote mărite' },
  ] },
  { id: 'model', label: 'Model', hint: 'Cât de corect e șansa scrisă de Robot, nu cât a câștigat un bilet. Doar Superbet, fără pariuri live.', tabs: [
    { value: 'pro', label: 'Pro' }, { value: 'calibrare', label: 'Calibrare' }, { value: 'robot', label: 'Robotul' }, { value: 'raport', label: 'Săptămâna' }, { value: 'laborator', label: 'Laborator' },
  ] },
];
const TAB_RE = '(?:pro|sumar|zi|luna|eveniment|calibrare|bilete|piramida|robot|raport|bb|laborator|boosts)';

function BlockTable({ rows, title }: { rows: StatBlock[]; title: string }) {
  if (!rows.length) return null;
  return (
    <Card className="overflow-hidden">
      <h2 className="p-3 text-sm font-semibold">{title}</h2>
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
  const journal = useAsync(() => loadJournalRows(minOdds, 400), [minOdds]);
  const myTickets = useStore((s) => s.myTickets);
  const robotLogAll = useStore((s) => s.robotLog);
  const pyramidLogAll = useStore((s) => s.pyramidLog);
  const [pyrTrack, setPyrTrack] = useState<'2.00' | '1.40' | 'mici'>('2.00');
  // doar Robotul 3.0, de la STATS_SINCE (fără istoricul vechi)
  const robotLog = useMemo(() => Object.fromEntries(Object.entries(robotLogAll).filter(([d]) => d >= STATS_SINCE)), [robotLogAll]);
  const pyramidLog = useMemo(() => Object.fromEntries(Object.entries(pyramidLogAll).filter(([d]) => d >= STATS_SINCE)), [pyramidLogAll]);
  const withdrawals = useStore((s) => s.withdrawals);
  const robotArchive = useStore((s) => s.robotArchive);

  const rules = useStore((s) => s.settings.pyramid);
  const [tab, setTab] = useState<Tab>(() => { const m = typeof window !== 'undefined' ? window.location.hash.match(new RegExp(`[?&]tab=(${TAB_RE})\\b`)) : null; return (m?.[1] as Tab) ?? 'sumar'; });
  const apiHist = useAsync(async () => {
    if (tab !== 'bilete' && tab !== 'piramida' && tab !== 'sumar') return null; // istoricul biletelor: sumar + bilete + piramidă
    const [h, t, pyr] = await Promise.all([loadTicketsHistory(), loadTickets(todayRo()), loadPyramid()]);
    return { tickets: [...(t?.tickets ?? []), ...h], pyramid: pyr };
  }, [tab === 'bilete' || tab === 'piramida' || tab === 'sumar']);
  const [period, setPeriod] = useState<Period>('all');
  const [from, setFrom] = useState(() => { const d = addDays(todayRo(), -30); return d < STATS_SINCE ? STATS_SINCE : d; });
  const [to, setTo] = useState(todayRo());
  const [market, setMarket] = useState('');
  const [league, setLeague] = useState('');
  const [band, setBand] = useState('');
  const [pMin, setPMin] = useState(0);
  const [q, setQ] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const closeFilters = useCallback(() => setFiltersOpen(false), []);
  const nF = [market, league, band].filter(Boolean).length + (pMin > 0 ? 1 : 0);

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
  const eq = useMemo(() => {
    // profit cumulat + ROI cumulat (profit / miză totală, 1u pe selecție cu cotă)
    const base = equity(rows);
    const staked = new Map<string, number>();
    for (const r of rows) if (r.result !== 'pending' && r.profit != null && r.odds) staked.set(r.date, (staked.get(r.date) ?? 0) + 1);
    const cumSt = base.reduce<number[]>((acc, d) => { acc.push((acc[acc.length - 1] ?? 0) + (staked.get(d.key) ?? 0)); return acc; }, []);
    return base.map((d, i) => { const st = cumSt[i]; return { ...d, roi: st ? Math.round((d.cum / st) * 1000) / 10 : 0 }; });
  }, [rows]);
  const [eqMode, setEqMode] = useState<'cum' | 'roi'>('cum');
  const [mkMode, setMkMode] = useState<'roi' | 'wr'>('roi');
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
      <div className="flex items-start justify-between gap-2">
        <div>
          <h1>Statistici</h1>
          <p className="text-sm text-muted-foreground">Trei zone: Rezultate, Bilete și Model. Profitul e la 1 unitate pe selecție, doar cote Superbet. Pariurile live nu se folosesc.</p>
        </div>
        <div className="flex shrink-0 gap-1">
          <button className="btn btn-outline h-11 w-11 p-0" onClick={exportCsv} disabled={!rows.length} aria-label="Descarcă CSV" title="Descarcă CSV"><Download className="h-4 w-4" /></button>
          <button className="btn btn-outline h-11 px-2.5 text-xs" onClick={() => download(`betpredict-statistici-${todayRo()}.json`, JSON.stringify(rows, null, 1), 'application/json')} disabled={!rows.length} aria-label="Descarcă JSON">JSON</button>
        </div>
      </div>

      <div className="space-y-2">
        <Segmented value={STAT_GROUPS.find((g) => g.tabs.some((t) => t.value === tab))!.id} onChange={(id) => setTab(STAT_GROUPS.find((g) => g.id === id)!.tabs[0].value)} className="w-full" options={STAT_GROUPS.map((g) => ({ value: g.id, label: g.label }))} />
        <Segmented size="sm" value={tab} onChange={setTab} className="w-full" options={STAT_GROUPS.find((g) => g.tabs.some((t) => t.value === tab))!.tabs} />
        <p className="text-xs text-muted-foreground">{STAT_GROUPS.find((g) => g.tabs.some((t) => t.value === tab))!.hint}</p>
      </div>

      {['sumar', 'pro', 'zi', 'luna', 'eveniment', 'calibrare'].includes(tab) && (
        <div className="flex items-center gap-2">
          <Segmented size="sm" value={period} onChange={setPeriod} options={[{ value: '7', label: '7 zile' }, { value: '30', label: '30 zile' }, { value: '90', label: '90 zile' }, { value: 'all', label: 'Tot' }, { value: 'custom', label: 'Interval' }]} />
          <button className="btn btn-outline relative ml-auto h-11 shrink-0 px-3" onClick={() => setFiltersOpen(true)}><SlidersHorizontal className="h-4 w-4" />Filtre{nF > 0 && <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">{nF}</span>}</button>
        </div>
      )}
      {period === 'custom' && <div className="flex gap-2"><input type="date" aria-label="De la" className="input" value={from} onChange={(e) => setFrom(e.target.value)} /><input type="date" aria-label="Până la" className="input" value={to} onChange={(e) => setTo(e.target.value)} /></div>}
      <Sheet open={filtersOpen} onClose={closeFilters} title="Filtre statistici">
        <div className="space-y-3">
          <select aria-label="Piață" className="input" value={market} onChange={(e) => setMarket(e.target.value)}><option value="">Toate piețele</option>{markets.map((m) => <option key={m} value={m}>{marketTitle(m)}</option>)}</select>
          <select aria-label="Ligă" className="input" value={league} onChange={(e) => setLeague(e.target.value)}><option value="">Toate ligile</option>{leagues.map((l) => <option key={l} value={l}>{l}</option>)}</select>
          <select aria-label="Interval de cotă" className="input" value={band} onChange={(e) => setBand(e.target.value)}><option value="">Orice cotă</option>{['1.00–1.30', '1.30–1.50', '1.50–1.80', '1.80–2.20', '2.20–3.00', '3.00+'].map((b) => <option key={b}>{b}</option>)}</select>
          <label className="block text-xs text-muted-foreground">Șansă minimă: <b className="text-foreground">{Math.round(pMin * 100)}%</b><input type="range" min={0} max={0.9} step={0.05} value={pMin} onChange={(e) => setPMin(Number(e.target.value))} className="block w-full" /></label>
          <div className="flex gap-2 pt-1"><button className="btn btn-outline flex-1" onClick={() => { setMarket(''); setLeague(''); setBand(''); setPMin(0); }}>Resetează</button><button className="btn btn-primary flex-1" onClick={closeFilters}>Aplică</button></div>
        </div>
      </Sheet>

      <Notice>Se numără <b>doar predicțiile publicate de Robotul 3.0</b> începând cu {STATS_SINCE.split('-').reverse().join('.')}. Istoricul vechi/importat (v2) este exclus.</Notice>

      {journal.loading ? <Loading /> : (
        <>
          {tab === 'sumar' && (
            <div className="space-y-4">
              <Headline rec={official?.recommended} tickets={official?.tickets} accaLocal={accaSettled.tickets} pyramid={pyrSettled.tickets} />
              <StilLiveCard />
              <PontStats tickets={accaSettled.tickets} />
              <details className="card p-3.5 md:p-4">
                <summary className="cursor-pointer text-sm font-semibold">Toate predicțiile analizate ({overall.n} decontate, toate piețele fiecărui meci)</summary>
                <p className="mt-1 text-xs text-muted-foreground">Include fiecare piață a fiecărui meci, nu doar ce recomandă Robotul — util pentru calibrare, nu pentru profit. ROI, profit și cota medie se calculează doar pe selecțiile care au avut cotă ({overall.played ?? 0}).</p>
                <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
                  <Stat label="Selecții decontate" value={overall.n} sub={`${overall.pending} în așteptare`} />
                  <Stat label="Rată de câștig" value={pct(overall.win_rate, 1)} sub={`${overall.won}V / ${overall.lost}Î${overall.void ? ` / ${overall.void} anulate` : ''}`} />
                  <Stat label="ROI (cu cotă)" value={signed(overall.roi_pct, 1, '%')} tone={(overall.roi_pct ?? 0) >= 0 ? 'win' : 'loss'} sub={`${overall.played ?? 0} cu cotă`} />
                  <Stat label="Profit" value={`${signed(overall.profit, 2)} u`} tone={overall.profit >= 0 ? 'win' : 'loss'} />
                  <Stat label="Cotă medie" value={fo(overall.avg_odds)} sub={`șansă medie ${pct(overall.avg_p)}`} />
                  <Stat label="Precizie (Brier)" value={num(overall.brier, 3)} sub="mai mic = mai bine" />
                </div>
              </details>
              <div className="grid gap-4 lg:grid-cols-2">
                <Card className="p-4"><div className="mb-2 flex flex-wrap items-center justify-between gap-2"><h2 className="text-sm font-semibold">{eqMode === 'cum' ? 'Profit cumulat și drawdown' : 'ROI cumulat'}</h2>
                  <Segmented size="sm" value={eqMode} onChange={setEqMode} options={[{ value: 'cum', label: 'Profit' }, { value: 'roi', label: 'ROI %' }]} /></div>
                  <Segmented size="sm" className="mb-2" value={period === '7' || period === '30' ? period : 'all'} onChange={(v) => setPeriod(v as Period)} options={[{ value: '7', label: '7z' }, { value: '30', label: '30z' }, { value: 'all', label: 'Tot' }]} />
                  {eq.length < 2 ? <p className="text-sm text-muted-foreground">Date insuficiente.</p> : <LazyChart className="h-56 md:h-64">{(R) => <R.ResponsiveContainer><R.ComposedChart data={eq} margin={{ left: -12, right: 4 }}><R.CartesianGrid strokeDasharray="3 3" opacity={0.2} /><R.XAxis dataKey="key" minTickGap={24} tickFormatter={(k: string) => k.slice(5)} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.Tooltip {...tip} formatter={(v: number, n: string) => (n === 'ROI cumulat' ? `${v.toFixed(1)}%` : `${v.toFixed(2)} u`)} /><R.ReferenceLine y={0} stroke="#888" /><defs><linearGradient id="gdd" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f43f5e" stopOpacity={0.05} /><stop offset="100%" stopColor="#f43f5e" stopOpacity={0.35} /></linearGradient><linearGradient id="gcum" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#14b8a6" stopOpacity={0.35} /><stop offset="100%" stopColor="#14b8a6" stopOpacity={0} /></linearGradient></defs>{eqMode === 'cum' ? <><R.Area isAnimationActive={false} activeDot={activeDot} dataKey="dd" name="drawdown" fill="url(#gdd)" stroke="#f43f5e" strokeWidth={1.5} /><R.Area isAnimationActive={false} activeDot={activeDot} dataKey="cum" name="profit cumulat" stroke="#10b981" fill="url(#gcum)" strokeWidth={2.5} /></> : <R.Area isAnimationActive={false} activeDot={activeDot} dataKey="roi" name="ROI cumulat" stroke="#14b8a6" fill="url(#gcum)" strokeWidth={2.5} />}</R.ComposedChart></R.ResponsiveContainer>}</LazyChart>}
                </Card>
                <Card className="p-4"><div className="mb-2 flex items-center justify-between gap-2"><h2 className="text-sm font-semibold">{mkMode === 'roi' ? 'ROI pe piață' : 'Rată de câștig pe piață'}</h2>
                  <Segmented size="sm" value={mkMode} onChange={setMkMode} options={[{ value: 'roi', label: 'ROI' }, { value: 'wr', label: 'Câștig %' }]} /></div>
                  <LazyChart className="h-56 md:h-64">{(R) => { const d = byMarket.filter((b) => b.n >= 3).map((b) => ({ ...b, wr: Math.round((b.win_rate ?? 0) * 1000) / 10 })); const k = mkMode === 'roi' ? 'roi_pct' : 'wr'; return <R.ResponsiveContainer><R.BarChart data={d} layout="vertical" margin={{ left: 0, right: 8 }}><R.CartesianGrid strokeDasharray="3 3" opacity={0.2} /><R.XAxis type="number" domain={mkMode === 'wr' ? [0, 100] : ['auto', 'auto']} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} width={84} /><R.Tooltip {...tip} formatter={(v: number, _n: string, it: { payload?: { n?: number } }) => `${v.toFixed(1)}% · ${it?.payload?.n ?? 0} sel.`} /><R.ReferenceLine x={mkMode === 'wr' ? 50 : 0} stroke="#888" /><R.Bar isAnimationActive={false} radius={[4, 4, 4, 4]} dataKey={k} name={mkMode === 'roi' ? 'ROI' : 'Câștig'}>{d.map((b) => <R.Cell key={b.key} fill={mkMode === 'wr' ? ((b.wr ?? 0) >= 50 ? '#14b8a6' : '#f59e0b') : (b.roi_pct ?? 0) >= 0 ? '#10b981' : '#f43f5e'} />)}</R.Bar></R.BarChart></R.ResponsiveContainer>; }}</LazyChart>
                </Card>
                <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Distribuția cotelor (rată de câștig și ROI pe interval)</h2>
                  <LazyChart className="h-56 md:h-64">{(R) => <R.ResponsiveContainer><R.ComposedChart data={byBand.map((b) => ({ ...b, wr: (b.win_rate ?? 0) * 100 }))}><R.CartesianGrid strokeDasharray="3 3" opacity={0.2} /><R.XAxis dataKey="key" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis yAxisId="l" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis yAxisId="r" orientation="right" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.Tooltip {...tip} /><R.Legend wrapperStyle={{ fontSize: 11 }} /><R.Bar radius={[4, 4, 4, 4]} yAxisId="l" dataKey="n" name="selecții" fill="#6366f1" /><R.Line activeDot={activeDot} yAxisId="r" dataKey="roi_pct" name="ROI %" stroke="#f59e0b" /><R.Line activeDot={activeDot} yAxisId="r" dataKey="wr" name="câștig %" stroke="#10b981" /></R.ComposedChart></R.ResponsiveContainer>}</LazyChart>
                </Card>
                <Card className="p-4">
                  <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Lightbulb className="h-4 w-4 text-warn" />Recomandări de îmbunătățire</h2>
                  <ul className="space-y-2">{recs.slice(0, 10).map((r, i) => (
                    <li key={i} className={cn('rounded-lg border px-3 py-2 text-sm', r.severity === 'critical' ? 'border-rose-500/40 bg-loss' : r.severity === 'warn' ? 'border-amber-500/40 bg-warn' : 'bg-muted/40')}>{r.text}</li>
                  ))}</ul>
                </Card>
              </div>
              <ClvCard clv={official?.clv} />
              <div className="grid gap-4 lg:grid-cols-2"><BlockTable rows={byLeague} title="Pe ligă" /><BlockTable rows={bySource} title="Pe sursă / strategie" /></div>
            </div>
          )}

          {tab === 'pro' && <ProStats rows={rows} clv={official?.clv} buckets={official?.ticket_buckets} />}
          {tab === 'raport' && <WeeklyPanel />}
          {tab === 'bb' && <BuilderStats />}
          {tab === 'laborator' && <LabPanel />}
          {tab === 'boosts' && <BoostsPanel />}

          {tab === 'zi' && (
            <div className="space-y-4">
              <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Calendar ultimele 8 săptămâni (verde = profit, roșu = pierdere)</h2><Heatmap rows={daily} /></Card>
              <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Profit pe zi (unități)</h2>
                <LazyChart className="h-56 md:h-64">{(R) => <R.ResponsiveContainer><R.BarChart data={daily.slice(-60)}><R.CartesianGrid strokeDasharray="3 3" opacity={0.2} /><R.XAxis dataKey="key" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.Tooltip {...tip} /><R.ReferenceLine y={0} stroke="#888" /><R.Bar radius={[4, 4, 4, 4]} dataKey="profit" name="profit">{daily.slice(-60).map((d) => <R.Cell key={d.key} fill={d.profit >= 0 ? '#10b981' : '#f43f5e'} />)}</R.Bar></R.BarChart></R.ResponsiveContainer>}</LazyChart>
              </Card>
              <BlockTable rows={[...daily].reverse()} title="Tabel pe zile" />
            </div>
          )}

          {tab === 'luna' && (
            <div className="space-y-4">
              <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">ROI și rata de câștig pe lună</h2>
                <LazyChart className="h-64">{(R) => <R.ResponsiveContainer><R.ComposedChart data={monthly.map((m) => ({ ...m, label: monthLabel(m.key), wr: (m.win_rate ?? 0) * 100 }))}><R.CartesianGrid strokeDasharray="3 3" opacity={0.2} /><R.XAxis dataKey="label" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis yAxisId="l" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis yAxisId="r" orientation="right" domain={[0, 100]} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.Tooltip {...tip} /><R.Legend wrapperStyle={{ fontSize: 11 }} /><R.ReferenceLine yAxisId="l" y={0} stroke="#888" />
                  <R.Bar radius={[4, 4, 4, 4]} yAxisId="l" dataKey="roi_pct" name="ROI %">{monthly.map((m) => <R.Cell key={m.key} fill={(m.roi_pct ?? 0) >= 0 ? '#10b981' : '#f43f5e'} />)}</R.Bar><R.Line activeDot={activeDot} yAxisId="r" dataKey="wr" name="câștig %" stroke="#6366f1" /></R.ComposedChart></R.ResponsiveContainer>}</LazyChart>
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
                <h2 className="mb-1 text-sm font-semibold">Diagrama de calibrare — prezis vs. real</h2>
                <p className="mb-2 text-xs text-muted-foreground">Punctele pe diagonală = probabilități corecte. Sub diagonală = Robotul supraestimează.</p>
                {!calAll ? <p className="text-sm text-muted-foreground">Date insuficiente.</p> : (
                  <LazyChart className="h-72">{(R) => <R.ResponsiveContainer><R.ScatterChart margin={{ left: 0 }}><R.CartesianGrid strokeDasharray="3 3" opacity={0.2} /><R.XAxis type="number" dataKey="p_avg" name="prezis" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis type="number" dataKey="hit_rate" name="real" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.ZAxis dataKey="n" range={[40, 400]} /><R.Tooltip {...tip} formatter={(v: number, n: string) => (n === 'n' ? v : `${(v * 100).toFixed(1)}%`)} />
                    <R.ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#888" strokeDasharray="4 4" /><R.Scatter data={calAll.bins} fill="#10b981" /></R.ScatterChart></R.ResponsiveContainer>}</LazyChart>
                )}
              </Card>
              <Card className="overflow-hidden"><h2 className="p-3 text-sm font-semibold">Calibrare pe piață (ECE)</h2>
                <table className="w-full text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">Piață</th><th className="text-right">n</th><th className="text-right">ECE</th><th className="px-3 text-right">Stare</th></tr></thead>
                  <tbody>{cal.map((c) => <tr key={c.key} className="border-t"><td className="px-3 py-1.5">{marketTitle(c.key)}</td><td className="text-right">{c.n}</td><td className="text-right">{num(c.ece, 3)}</td><td className="px-3 text-right"><Badge tone={c.n < 20 ? 'muted' : c.healthy ? 'win' : 'loss'}>{c.n < 20 ? 'eșantion mic' : c.healthy ? 'sănătoasă' : 'necalibrată'}</Badge></td></tr>)}</tbody></table>
              </Card>
            </div>
          )}

          {tab === 'bilete' && (
            <TicketSection tickets={accaSettled.tickets} empty="Încă nu există bilete acumulator salvate (Robot 3.0)"
              groupTitle="Pe tip de bilet"
              extra={official?.tickets?.length ? <TypeCards title="Rezultate oficiale Robot (decontate automat)" rows={official.tickets.filter((t) => t.kind.startsWith('acca_')).map((t) => ({ key: ticketType({ kind: t.kind, variant: t.variant, target_odds: null, legs: [] }), n: t.n, won: t.won, lost: t.lost, roi: t.roi_pct ?? null }))} /> : null} />
          )}

          {tab === 'piramida' && <Segmented size="sm" value={pyrTrack} onChange={setPyrTrack} options={[{ value: '2.00', label: '2.00' }, { value: '1.40', label: '1.40' }, { value: 'mici', label: 'Ligi mici' }]} />}
          {tab === 'piramida' && pyrTrack !== '2.00' && <Pyramid140Stats key={pyrTrack} track={pyrTrack} />}
          {tab === 'piramida' && pyrTrack === '2.00' && (
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
              <RobotPanel learning={stats.data?.learning} calibration={stats.data?.calibration} />
                  {stats.data?.learning?.walk_forward?.length ? (
                    <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Walk-forward: LogLoss model vs. bază (mai mic = mai bine)</h2>
                      <LazyChart className="h-56 md:h-64">{(R) => <R.ResponsiveContainer><R.LineChart data={stats.data!.learning!.walk_forward}><R.CartesianGrid strokeDasharray="3 3" opacity={0.2} /><R.XAxis dataKey="fold" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} domain={['auto', 'auto']} /><R.Tooltip {...tip} /><R.Legend wrapperStyle={{ fontSize: 11 }} />
                        <R.Line activeDot={activeDot} dataKey="logloss_1x2" name="1X2 model" stroke="#10b981" /><R.Line activeDot={activeDot} dataKey="baseline_1x2" name="1X2 bază" stroke="#10b981" strokeDasharray="4 4" /><R.Line activeDot={activeDot} dataKey="logloss_ou25" name="O/U 2.5 model" stroke="#6366f1" /><R.Line activeDot={activeDot} dataKey="baseline_ou25" name="O/U 2.5 bază" stroke="#6366f1" strokeDasharray="4 4" /></R.LineChart></R.ResponsiveContainer>}</LazyChart>
                    </Card>
                  ) : null}
              <Card className="p-4"><h2 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Lightbulb className="h-4 w-4 text-warn" />Tipare detectate în rezultate</h2>
                <ul className="space-y-2">{recs.map((r, i) => <li key={i} className="rounded-lg bg-muted/40 px-3 py-2 text-sm">{r.text}</li>)}</ul>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** Titlul paginii: ce a publicat efectiv Robotul (recomandări + bilete), nu toate piețele analizate. */
function Headline({ rec, tickets, accaLocal, pyramid }: { rec?: StatBlock; tickets?: Array<{ kind: string; n: number; won: number; lost: number; pending?: number; profit: number; roi_pct: number | null }>; accaLocal: Ticket[]; pyramid: Ticket[] }) {
  const srv = (tickets ?? []).filter((t) => t.kind.startsWith('acca_'));
  // din lista de bilete (mereu la zi); sumarul serverului doar ca rezervă până se încarcă istoricul
  const live = accaLocal.length > 0;
  const tw = live ? accaLocal.filter((t) => t.status === 'won').length : srv.reduce((a, t) => a + t.won, 0);
  const tl = live ? accaLocal.filter((t) => t.status === 'lost').length : srv.reduce((a, t) => a + t.lost, 0);
  const tn = live ? accaLocal.length : srv.reduce((a, t) => a + t.n, 0);
  const tp = live
    ? accaLocal.reduce((a, t) => { const u = t.stake_units ?? 0; return a + (t.status === 'won' ? (t.payout ?? u * (t.effective_odds ?? t.total_odds)) - u : t.status === 'lost' ? -u : 0); }, 0)
    : srv.reduce((a, t) => a + (t.profit ?? 0), 0);
  const sp = (tickets ?? []).find((t) => t.kind === 'pyramid' && ((t as { variant?: string }).variant ?? 'principal') === 'principal');
  const pw = sp && !pyramid.length ? sp.won : pyramid.filter((t) => t.status === 'won').length;
  const pl = sp && !pyramid.length ? sp.lost : pyramid.filter((t) => t.status === 'lost').length;
  const pn = sp && !pyramid.length ? sp.n : pyramid.length;
  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold">Ce a publicat Robotul</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Recomandări decontate" value={rec ? rec.won + rec.lost : '—'} sub={rec ? `${rec.won}V / ${rec.lost}Î · ${rec.pending ?? 0} în așteptare` : 'se încarcă'} />
        <Stat label="ROI recomandări" value={signed(rec?.roi_pct ?? null, 1, '%')} tone={(rec?.roi_pct ?? 0) >= 0 ? 'win' : 'loss'} sub={rec ? `rată ${pct(rec.win_rate, 1)} · cotă medie ${fo(rec.avg_odds ?? null)}` : undefined} />
        <Stat label="Bilete acumulator" value={tn} sub={`${tw} câștigate / ${tl} pierdute${tw + tl ? ` · ${signed(tp, 2)} u` : ''}`} tone={tw + tl ? (tp >= 0 ? 'win' : 'loss') : undefined} />
        <Stat label="Piramida" value={pn} sub={`${pw} câștigate / ${pl} pierdute`} />
      </div>
    </div>
  );
}
