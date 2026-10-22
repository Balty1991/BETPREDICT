import { useLocation } from 'react-router';
import { PageHero } from '@/components/PageHero';
import { MarketHealth, ClvStrategy } from '@/components/MarketHealth';
import { KindSparks } from '@/components/KindSparks';
import { ticketType } from '@/components/MyBank';
import { AdvancedStats } from '@/components/AdvancedStats';
import { BuilderStats } from '@/components/BuilderStats';
import { PontStats } from '@/components/PontStats';
import { tip, activeDot } from '@/lib/chart';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ChevronRight, Download, Lightbulb, Search, SlidersHorizontal } from 'lucide-react';
import { LazyChart } from '@/components/LazyChart';
import { useAsync } from '@/lib/fetcher';
import { loadStats, loadJournalRows, loadTicketsHistory, loadTickets, loadPyramid } from '@/lib/data';
import { ProStats } from '@/components/ProStats';
import { RobotPanel } from '@/components/RobotPanel';
import { LabPanel } from '@/components/LabPanel';
import { BoostsPanel } from '@/components/BoostsPanel';
import { MarketAudit } from '@/components/MarketAudit';
import { MyBank } from '@/components/MyBank';
import { MonthlyCompare } from '@/components/MonthlyCompare';
import { ClvCard, WeeklyPanel } from '@/components/WeeklyPanel';
import { StilLiveCard } from '@/components/LabPanel';
import { Pyramid140Stats } from '@/components/Pyramid140View';
import { TicketSection, pyramidDaysSummary } from '@/components/StatsSections';
import { useStore } from '@/lib/store';
import { useSettledTickets } from '@/lib/hooks';
import { addDays, todayRo, pct, signed, num, monthLabel, odds as fo } from '@/lib/format';
import { block, series, groups, calibration, equity, recommendations, oddsBand, simulatePyramid } from '@/lib/analytics';
import { marketTitle } from '@/lib/markets';
import { Card, Loading, Empty, Segmented, Stat, Badge, ResultBadge, Notice, Sheet } from '@/components/kit';
import type { JournalRow, StatBlock, Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';
import { pickBoard } from '@/lib/board';
import { STATS_SINCE } from '@/lib/rules';


type Tab = 'pro' | 'sumar' | 'zi' | 'luna' | 'eveniment' | 'avansat' | 'calibrare' | 'bilete' | 'egaluri' | 'peval' | 'piramida' | 'robot' | 'raport' | 'laborator' | 'bb' | 'boosts' | 'alte' | 'audit';
type Period = '7' | '30' | '90' | 'all' | 'custom';

const STAT_GROUPS: Array<{ id: string; label: string; hint: string; tabs: Array<{ value: Tab; label: string }> }> = [
  { id: 'rezultate', label: 'Rezultate', hint: 'Ce ar fi ieșit la 1 unitate pe fiecare predicție publicată. Verde = profit, roșu = pierdere.', tabs: [
    { value: 'sumar', label: 'Sumar' }, { value: 'avansat', label: 'Avansate' },
  ] },
  { id: 'bilete', label: 'Bilete', hint: 'Lista din pagina Bilete: până la 10 bilete pe zi. Un bilet poate repeta cel mult 3 meciuri. Profitul e la miza publicată.', tabs: [
    { value: 'bilete', label: 'Jucate' }, { value: 'alte', label: 'Restul' },
  ] },
  { id: 'model', label: 'Model', hint: 'Cât de corect e șansa scrisă de Robot, nu cât a câștigat un bilet. Doar Superbet, fără pariuri live.', tabs: [
    { value: 'pro', label: 'Pro' }, { value: 'laborator', label: 'Laborator' },
  ] },
];
const PARENT: Partial<Record<Tab, Tab>> = {
  zi: 'sumar', luna: 'sumar', eveniment: 'sumar',
  egaluri: 'alte', piramida: 'alte', bb: 'alte', boosts: 'alte', peval: 'bilete',
  calibrare: 'pro', robot: 'pro', raport: 'pro', audit: 'pro',
};
const TAB_RE = '(?:pro|sumar|avansat|zi|luna|eveniment|calibrare|bilete|peval|piramida|robot|raport|bb|laborator|boosts|egaluri|alte|audit)';

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
  const pad = (new Date(`${days[0]}T12:00:00Z`).getUTCDay() + 6) % 7;
  const cells: Array<string | null> = [...Array(pad).fill(null), ...days];
  const map = new Map(rows.map((r) => [r.key!, r]));
  return (
    <div>
      <div className="mb-1 grid grid-cols-7 gap-1 text-center text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {['Lu', 'Ma', 'Mi', 'Jo', 'Vi', 'Sâ', 'Du'].map((d) => <div key={d}>{d}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((d, i) => {
          if (!d) return <div key={`pad-${i}`} className="aspect-square" />;
          const r = map.get(d); const p = r?.profit ?? 0; const a = Math.min(1, Math.abs(p) / 5);
          return <div key={d} title={`${d}: ${r ? `${r.n} selecții, profit ${p >= 0 ? '+' : ''}${p.toFixed(2)}u` : 'fără date în perioada aleasă'}`} className="heat-cell aspect-square" style={{ background: !r ? 'hsl(var(--muted))' : p >= 0 ? `rgba(16,185,129,${0.28 + a * 0.72})` : `rgba(244,63,94,${0.28 + a * 0.72})` }} />;
        })}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1"><i className="legend-swatch bg-muted" /> fără date</span>
        <span className="inline-flex items-center gap-1"><i className="legend-swatch bg-emerald-500" /> profit</span>
        <span className="inline-flex items-center gap-1"><i className="legend-swatch bg-rose-500" /> pierdere</span>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">Fiecare rând e o săptămână, de luni până duminică. Culoarea folosește perioada aleasă mai sus.</p>
    </div>
  );
}

function download(name: string, text: string, type: string) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

const SPARK_KINDS = [['Pontul zilei', 'Pont'], ['Piramidă', 'Piramidă'], ['Sub 20', 'Sub 20'], ['Cotă 20–99', '20–99'], ['Cotă 100+', '100+'], ['Cotă 500+', '500+']] as const;

export default function StatsPage() {
  const minOdds = useStore((s) => s.settings.minOdds);
  const stats = useAsync(loadStats, []);
  const journal = useAsync(() => loadJournalRows(minOdds, 400), [minOdds]);
  const myTickets = useStore((s) => s.myTickets);
  const robotLogAll = useStore((s) => s.robotLog);
  const pyramidLogAll = useStore((s) => s.pyramidLog);
  const [pyrTrack, setPyrTrack] = useState<'2.00' | '1.20' | '1.40' | '1.60' | 'boost' | 'mici' | 'r5' | 'r10'>('1.20');
  // doar Robotul 3.0, de la STATS_SINCE (fără istoricul vechi)
  const robotLog = useMemo(() => Object.fromEntries(Object.entries(robotLogAll).filter(([d]) => d >= STATS_SINCE)), [robotLogAll]);
  const pyramidLog = useMemo(() => Object.fromEntries(Object.entries(pyramidLogAll).filter(([d]) => d >= STATS_SINCE)), [pyramidLogAll]);
  const withdrawals = useStore((s) => s.withdrawals);
  const robotArchive = useStore((s) => s.robotArchive);

  const rules = useStore((s) => s.settings.pyramid);
  const [tab, setTab] = useState<Tab>(() => { const m = typeof window !== 'undefined' ? window.location.hash.match(new RegExp(`[?&]tab=(${TAB_RE})\\b`)) : null; return (m?.[1] as Tab) ?? 'sumar'; });
  // link direct (#/statistici?tab=laborator) sau din meniul „Mai mult”: fila urmează adresa
  const locSearch = useLocation().search;
  useEffect(() => {
    const m = locSearch.match(new RegExp(`[?&]tab=(${TAB_RE})\\b`));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fila e stare locală, sincronizată cu adresa
    if (m) setTab(m[1] as Tab);
  }, [locSearch]);
  const apiHist = useAsync(async () => {
    if (!['bilete', 'piramida', 'sumar', 'alte', 'egaluri', 'peval', 'zi', 'luna', 'eveniment'].includes(tab)) return null;
    const [h, t, pyr] = await Promise.all([loadTicketsHistory(), loadTickets(todayRo()), loadPyramid()]);
    return { tickets: [...(t?.tickets ?? []), ...h], pyramid: pyr };
  }, [tab]);
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

  const all = useMemo(() => journal.data?.rows ?? [], [journal.data]);
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
  const softTickets = useMemo(() => accaSettled.tickets.filter((t) => t.kind === 'acca_soft'), [accaSettled.tickets]);
  // „Jucate” = lista publicată (aceeași ca în Bilete): doar biletele serverului, fără arhiva locală sau biletele mele
  const playedRaw: Ticket[] = useMemo(() => {
    const map = new Map<string, Ticket>();
    for (const t of apiHist.data?.tickets ?? []) if (t.kind?.startsWith('acca_') && (t.date ?? '') >= STATS_SINCE) map.set(String(t.id), t);
    return pickBoard([...map.values()]);
  }, [apiHist.data]);
  const played = useSettledTickets(playedRaw).tickets;
  const mineSettled = useSettledTickets(myTickets).tickets;
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
  const view = PARENT[tab] ?? tab;
  const zone = STAT_GROUPS.find((g) => g.tabs.some((t) => t.value === view)) ?? STAT_GROUPS[0];
  return (
    <div className="space-y-4">
      <PageHero eyebrow="Doar Superbet · fără live" title="Statistici" right={(
        <div className="flex shrink-0 gap-1">
          <button className="btn btn-outline h-11 w-11 p-0" onClick={exportCsv} disabled={!rows.length} aria-label="Descarcă CSV" title="Descarcă CSV"><Download className="h-4 w-4" /></button>
          <button className="btn btn-outline h-11 px-2.5 text-xs" onClick={() => download(`betpredict-statistici-${todayRo()}.json`, JSON.stringify(rows, null, 1), 'application/json')} disabled={!rows.length} aria-label="Descarcă JSON">JSON</button>
        </div>
      )} />
      <div className="grid grid-cols-3 gap-2" role="group" aria-label="Zonă statistici">
        {STAT_GROUPS.map((g) => {
          const on = g.id === zone.id;
          return (
            <button key={g.id} type="button" aria-pressed={on} onClick={() => setTab(g.tabs[0].value)}
              className={cn('min-h-[52px] rounded-2xl px-2 text-sm font-extrabold', on ? 'bg-primary text-primary-foreground' : 'border bg-card text-muted-foreground')}>
              {g.label}
            </button>
          );
        })}
      </div>

      <div className="min-w-0">
        <Segmented size="sm" value={view} onChange={setTab} className="w-full max-w-full" options={zone.tabs} />
      </div>

      {['sumar', 'avansat', 'pro'].includes(view) && (
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Segmented size="sm" value={period} onChange={setPeriod} className="min-w-0 flex-1 basis-full sm:basis-auto" options={[{ value: '7', label: '7 zile' }, { value: '30', label: '30 zile' }, { value: '90', label: '90 zile' }, { value: 'all', label: 'Tot' }, { value: 'custom', label: 'Interval' }]} />
            <button className="btn btn-outline relative ml-auto h-11 shrink-0 px-3" onClick={() => setFiltersOpen(true)}><SlidersHorizontal className="h-4 w-4" />Filtre{nF > 0 && <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">{nF}</span>}</button>
          </div>
        </div>
      )}
      {period === 'custom' && <div className="flex gap-2"><input type="date" aria-label="De la" className="input" value={from} onChange={(e) => setFrom(e.target.value)} /><input type="date" aria-label="Până la" className="input" value={to} onChange={(e) => setTo(e.target.value)} /></div>}
      {['sumar', 'avansat', 'pro'].includes(view) && (
        <p className="text-xs text-muted-foreground">
          Perioadă: <b className="text-foreground">{period === 'all' ? `de la ${STATS_SINCE.split('-').reverse().join('.')}` : period === 'custom' ? `${from.split('-').reverse().join('.')} – ${to.split('-').reverse().join('.')}` : `ultimele ${period} zile`}</b>
          {' · '}<b className="text-foreground">{settled.length}</b> decontate din {rows.length}
          {settled.length > 0 && settled.length < 20 ? ' · eșantion mic, sub 20, același prag ca la calibrare' : ''}
        </p>
      )}
      <Sheet open={filtersOpen} onClose={closeFilters} title="Filtre statistici" subtitle="Se aplică imediat pe perioada aleasă."
        footer={<div className="flex gap-2"><button className="btn btn-outline min-h-11 flex-1" onClick={() => { setMarket(''); setLeague(''); setBand(''); setPMin(0); }}>Resetează</button><button className="btn btn-primary min-h-11 flex-1" onClick={closeFilters}>Gata</button></div>}>
        <div className="space-y-3">
          <select aria-label="Piață" className="input min-h-11" value={market} onChange={(e) => setMarket(e.target.value)}><option value="">Toate piețele</option>{markets.map((m) => <option key={m} value={m}>{marketTitle(m)}</option>)}</select>
          <select aria-label="Ligă" className="input min-h-11" value={league} onChange={(e) => setLeague(e.target.value)}><option value="">Toate ligile</option>{leagues.map((l) => <option key={l} value={l}>{l}</option>)}</select>
          <select aria-label="Interval de cotă" className="input min-h-11" value={band} onChange={(e) => setBand(e.target.value)}><option value="">Orice cotă</option>{['1.00–1.30', '1.30–1.50', '1.50–1.80', '1.80–2.20', '2.20–3.00', '3.00+'].map((b) => <option key={b}>{b}</option>)}</select>
          <label className="block text-xs text-muted-foreground">Șansă minimă: <b className="text-foreground">{Math.round(pMin * 100)}%</b><input type="range" min={0} max={0.9} step={0.05} value={pMin} onChange={(e) => setPMin(Number(e.target.value))} className="mt-1 block h-8 w-full" /></label>
        </div>
      </Sheet>
      {nF > 0 && (
        <div className="flex gap-1.5 overflow-x-auto scrollbar-none">
          {market && <button type="button" className="chip chip-on shrink-0" onClick={() => setMarket('')}>{marketTitle(market)} ×</button>}
          {league && <button type="button" className="chip chip-on shrink-0" onClick={() => setLeague('')}>{league} ×</button>}
          {band && <button type="button" className="chip chip-on shrink-0" onClick={() => setBand('')}>{band} ×</button>}
          {pMin > 0 && <button type="button" className="chip chip-on shrink-0" onClick={() => setPMin(0)}>șansă ≥ {Math.round(pMin * 100)}% ×</button>}
        </div>
      )}

      <Notice>Se numără <b>doar predicțiile publicate de Robotul 3.0</b> începând cu {STATS_SINCE.split('-').reverse().join('.')}. Istoricul vechi/importat (v2) este exclus.</Notice>

      {journal.loading ? <Loading /> : (
        <>
          {tab === 'avansat' && <AdvancedStats rows={rows} clv={official?.clv} error={journal.error} />}
          {(tab === 'sumar' || tab === 'zi' || tab === 'luna' || tab === 'eveniment') && (
            <div className="space-y-4">
              <Headline rec={official?.recommended} tickets={official?.tickets} accaLocal={accaSettled.tickets} pyramid={pyrSettled.tickets} />
              <StilLiveCard />
              <MarketHealth />
              <KindSparks tickets={[...accaSettled.tickets, ...pyrSettled.tickets]} kinds={SPARK_KINDS} kindOf={ticketType} />
              <MonthlyCompare tickets={[...accaSettled.tickets, ...pyrSettled.tickets]} />
              <ClvStrategy />
              <PontStats tickets={accaSettled.tickets} />
              <details className="card p-3.5 md:p-4">
                <summary className="cursor-pointer text-sm font-semibold">Toate predicțiile analizate ({overall.n} decontate, toate piețele fiecărui meci)</summary>
                <p className="mt-1 text-xs text-muted-foreground">Include fiecare piață a fiecărui meci, nu doar ce recomandă Robotul — util pentru calibrare, nu pentru profit. ROI, profit și cota medie se calculează doar pe selecțiile care au avut cotă ({overall.played ?? 0}).</p>
                <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
                  <Stat label="Selecții decontate" value={overall.n} sub={`${overall.pending} în așteptare`} />
                  <Stat label="Rată de câștig" value={pct(overall.win_rate, 1)} sub={`${overall.won}V / ${overall.lost}Î${overall.void ? ` / ${overall.void} anulate` : ''}`} />
                  <Stat label="ROI (cu cotă)" value={signed(overall.roi_pct, 1, '%')} tone={(overall.roi_pct ?? 0) >= 0 ? 'win' : 'loss'} sub={`${overall.played ?? 0} cu cotă`} />
                  <Stat label="Profit" value={`${signed(overall.profit, 2)} u`} tone={overall.profit >= 0 ? 'win' : 'loss'} sub={`${overall.played ?? 0} selecții cu cotă`} />
                  <Stat label="Cotă medie" value={fo(overall.avg_odds)} sub={`șansă medie ${pct(overall.avg_p)}`} />
                  <Stat label="Precizie (Brier)" value={num(overall.brier, 3)} sub="mai mic = mai bine" />
                </div>
              </details>
              <div className="grid gap-4 lg:grid-cols-2">
                <Card className="p-4"><div className="mb-2 flex flex-wrap items-center justify-between gap-2"><h2 className="text-sm font-semibold">{eqMode === 'cum' ? 'Profit cumulat și drawdown' : 'ROI cumulat'}</h2>
                  <Segmented size="sm" value={eqMode} onChange={setEqMode} options={[{ value: 'cum', label: 'Profit' }, { value: 'roi', label: 'ROI %' }]} /></div>
                  {eq.length < 2 ? <p className="text-sm text-muted-foreground">Date insuficiente.</p> : <LazyChart className="h-56 md:h-64">{(R) => <R.ResponsiveContainer><R.ComposedChart data={eq} margin={{ left: -12, right: 4 }}><R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} /><R.XAxis dataKey="key" minTickGap={24} tickFormatter={(k: string) => k.slice(5)} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.Tooltip {...tip} formatter={(v: number, n: string) => (n === 'ROI cumulat' ? `${v.toFixed(1)}%` : `${v.toFixed(2)} u`)} /><R.ReferenceLine y={0} stroke="#888" /><defs><linearGradient id="gdd" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ff5c7a" stopOpacity={0.05} /><stop offset="100%" stopColor="#ff5c7a" stopOpacity={0.35} /></linearGradient><linearGradient id="gcum" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22d3ee" stopOpacity={0.35} /><stop offset="100%" stopColor="#22d3ee" stopOpacity={0} /></linearGradient></defs>{eqMode === 'cum' ? <><R.Area isAnimationActive={false} activeDot={activeDot} dataKey="dd" name="drawdown" fill="url(#gdd)" stroke="#ff5c7a" strokeWidth={1.5} /><R.Area isAnimationActive={false} activeDot={activeDot} dataKey="cum" name="profit cumulat" stroke="#2ee6a6" fill="url(#gcum)" strokeWidth={2.5} /></> : <R.Area isAnimationActive={false} activeDot={activeDot} dataKey="roi" name="ROI cumulat" stroke="#22d3ee" fill="url(#gcum)" strokeWidth={2.5} />}</R.ComposedChart></R.ResponsiveContainer>}</LazyChart>}
                </Card>
                <Card className="p-4"><div className="mb-2 flex items-center justify-between gap-2"><h2 className="text-sm font-semibold">{mkMode === 'roi' ? 'ROI pe piață' : 'Rată de câștig pe piață'}</h2>
                  <Segmented size="sm" value={mkMode} onChange={setMkMode} options={[{ value: 'roi', label: 'ROI' }, { value: 'wr', label: 'Câștig %' }]} /></div>
                  <LazyChart className="h-56 md:h-64">{(R) => { const d = byMarket.filter((b) => b.n >= 3).map((b) => ({ ...b, wr: Math.round((b.win_rate ?? 0) * 1000) / 10 })); const k = mkMode === 'roi' ? 'roi_pct' : 'wr'; return <R.ResponsiveContainer><R.BarChart data={d} layout="vertical" margin={{ left: 0, right: 8 }}><R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} /><R.XAxis type="number" domain={mkMode === 'wr' ? [0, 100] : ['auto', 'auto']} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} width={84} /><R.Tooltip {...tip} formatter={(v: number, _n: string, it: { payload?: { n?: number } }) => `${v.toFixed(1)}% · ${it?.payload?.n ?? 0} sel.`} /><R.ReferenceLine x={mkMode === 'wr' ? 50 : 0} stroke="#888" /><R.Bar isAnimationActive={false} radius={[4, 4, 4, 4]} dataKey={k} name={mkMode === 'roi' ? 'ROI' : 'Câștig'}>{d.map((b) => <R.Cell key={b.key} fill={mkMode === 'wr' ? ((b.wr ?? 0) >= 50 ? '#22d3ee' : '#fbbf24') : (b.roi_pct ?? 0) >= 0 ? '#2ee6a6' : '#ff5c7a'} />)}</R.Bar></R.BarChart></R.ResponsiveContainer>; }}</LazyChart>
                </Card>
                <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Distribuția cotelor (rată de câștig și ROI pe interval)</h2>
                  <LazyChart className="h-56 md:h-64">{(R) => <R.ResponsiveContainer><R.ComposedChart data={byBand.map((b) => ({ ...b, wr: (b.win_rate ?? 0) * 100 }))}><R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} /><R.XAxis dataKey="key" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis yAxisId="l" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis yAxisId="r" orientation="right" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.Tooltip {...tip} /><R.Legend wrapperStyle={{ fontSize: 11 }} /><R.Bar radius={[4, 4, 4, 4]} yAxisId="l" dataKey="n" name="selecții" fill="#a78bfa" /><R.Line activeDot={activeDot} yAxisId="r" dataKey="roi_pct" name="ROI %" stroke="#fbbf24" /><R.Line activeDot={activeDot} yAxisId="r" dataKey="wr" name="câștig %" stroke="#2ee6a6" /></R.ComposedChart></R.ResponsiveContainer>}</LazyChart>
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

          {(tab === 'pro' || tab === 'calibrare' || tab === 'robot' || tab === 'raport') && <ProStats rows={rows} clv={official?.clv} buckets={official?.ticket_buckets} />}
          {view === 'pro' && <Fold title="Săptămâna" startOpen={tab === 'raport'}><WeeklyPanel /></Fold>}
          {view === 'pro' && <Fold title="Audit piețe" startOpen={tab === 'audit'}><MarketAudit /></Fold>}
          {tab === 'laborator' && <LabPanel />}
          {view === 'alte' && <Fold title="Egaluri" startOpen={tab === 'egaluri' || tab === 'alte'}><SoftDrawMonitor tickets={softTickets} /></Fold>}
          {view === 'alte' && <Fold title="Bet Builder" startOpen={tab === 'bb'}><BuilderStats /></Fold>}
          {view === 'alte' && <Fold title="Cote mărite" startOpen={tab === 'boosts'}><BoostsPanel /></Fold>}

          {view === 'sumar' && (
            <Fold title="Pe zi" startOpen={tab === 'zi'}>
            <div className="space-y-4">
              <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Calendar · verde profit, roșu pierdere</h2><Heatmap rows={daily} /></Card>
              <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Profit pe zi, în unități</h2>
                <LazyChart className="h-56 md:h-64">{(R) => <R.ResponsiveContainer><R.BarChart data={daily.slice(-60)}><R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} /><R.XAxis dataKey="key" minTickGap={28} tickFormatter={(k: string) => String(k).slice(5)} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} width={36} /><R.Tooltip {...tip} formatter={(v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)} u`} /><R.ReferenceLine y={0} stroke="#888" /><R.Bar radius={[4, 4, 4, 4]} dataKey="profit" name="profit">{daily.slice(-60).map((d) => <R.Cell key={d.key} fill={d.profit >= 0 ? '#2ee6a6' : '#ff5c7a'} />)}</R.Bar></R.BarChart></R.ResponsiveContainer>}</LazyChart>
              </Card>
              <BlockTable rows={[...daily].reverse()} title="Tabel pe zile" />
            </div>
            </Fold>
          )}

          {view === 'sumar' && (
            <Fold title="Pe lună" startOpen={tab === 'luna'}>
            <div className="space-y-4">
              <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">ROI și rata de câștig pe lună</h2>
                <LazyChart className="h-64">{(R) => <R.ResponsiveContainer><R.ComposedChart data={monthly.map((m) => ({ ...m, label: monthLabel(m.key), wr: (m.win_rate ?? 0) * 100 }))}><R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} /><R.XAxis dataKey="label" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis yAxisId="l" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis yAxisId="r" orientation="right" domain={[0, 100]} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.Tooltip {...tip} /><R.Legend wrapperStyle={{ fontSize: 11 }} /><R.ReferenceLine yAxisId="l" y={0} stroke="#888" />
                  <R.Bar radius={[4, 4, 4, 4]} yAxisId="l" dataKey="roi_pct" name="ROI %">{monthly.map((m) => <R.Cell key={m.key} fill={(m.roi_pct ?? 0) >= 0 ? '#2ee6a6' : '#ff5c7a'} />)}</R.Bar><R.Line activeDot={activeDot} yAxisId="r" dataKey="wr" name="câștig %" stroke="#a78bfa" /></R.ComposedChart></R.ResponsiveContainer>}</LazyChart>
              </Card>
              <BlockTable rows={[...monthly].reverse().map((m) => ({ ...m, name: monthLabel(m.key) }))} title="Tabel pe luni" />
            </div>
            </Fold>
          )}

          {view === 'sumar' && (
            <Fold title="Pe meci" startOpen={tab === 'eveniment'}>
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
            </Fold>
          )}

          {view === 'pro' && (
            <Fold title="Calibrare" startOpen={tab === 'calibrare'}>
            <div className="space-y-4">
              <Card className="p-4">
                <h2 className="mb-1 text-sm font-semibold">Diagrama de calibrare — prezis vs. real</h2>
                <p className="mb-2 text-xs text-muted-foreground">Punctele pe diagonală = probabilități corecte. Sub diagonală = Robotul supraestimează.</p>
                {!calAll ? <p className="text-sm text-muted-foreground">Date insuficiente.</p> : (
                  <LazyChart className="h-72">{(R) => <R.ResponsiveContainer><R.ScatterChart margin={{ left: 0 }}><R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} /><R.XAxis type="number" dataKey="p_avg" name="prezis" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis type="number" dataKey="hit_rate" name="real" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.ZAxis dataKey="n" range={[40, 400]} /><R.Tooltip {...tip} formatter={(v: number, n: string) => (n === 'n' ? v : `${(v * 100).toFixed(1)}%`)} />
                    <R.ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#888" strokeDasharray="4 4" /><R.Scatter data={calAll.bins} fill="#2ee6a6" /></R.ScatterChart></R.ResponsiveContainer>}</LazyChart>
                )}
              </Card>
              <Card className="overflow-hidden"><h2 className="p-3 text-sm font-semibold">Calibrare pe piață (ECE)</h2>
                <table className="w-full text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">Piață</th><th className="text-right">n</th><th className="text-right">ECE</th><th className="px-3 text-right">Stare</th></tr></thead>
                  <tbody>{cal.map((c) => <tr key={c.key} className="border-t"><td className="px-3 py-1.5">{marketTitle(c.key)}</td><td className="text-right">{c.n}</td><td className="text-right">{num(c.ece, 3)}</td><td className="px-3 text-right"><Badge tone={c.n < 20 ? 'muted' : c.healthy ? 'win' : 'loss'}>{c.n < 20 ? 'eșantion mic' : c.healthy ? 'sănătoasă' : 'necalibrată'}</Badge></td></tr>)}</tbody></table>
              </Card>
            </div>
            </Fold>
          )}

          {(tab === 'bilete' || tab === 'peval') && (
            <div className="space-y-3">
              <Fold title="Banca mea" startOpen><MyBank tickets={mineSettled} /></Fold>
              <p className="text-xs text-muted-foreground">Aceeași listă ca în Bilete (de la 16.10: de la cota 20, cel mult un bilet sub 50 pe zi). Profitul e la miza publicată.</p>
              <TicketSection tickets={played} empty="Încă nu există bilete în lista jucată." groupTitle="Pe zi" groupKey={(t) => t.date ?? '—'} />
              <Fold title="Piețele din spate"><StilLiveCard /></Fold>
            </div>
          )}

          {view === 'alte' && (
            <Fold title="Piramidă" startOpen={tab === 'piramida'}>
              <Segmented size="sm" value={pyrTrack} onChange={setPyrTrack} options={[{ value: '1.20', label: '1.20' }, { value: '1.40', label: '1.40' }, { value: 'boost', label: 'Cote mărite' }]} />
              {pyrTrack !== '2.00' && <Pyramid140Stats key={pyrTrack} track={pyrTrack} />}
              {pyrTrack === '2.00' && (
            <TicketSection tickets={pyrSettled.tickets} empty="Încă nu există propuneri de piramidă salvate (Robot 3.0)"
              groupTitle="Pe număr de selecții" groupKey={(t) => `${t.legs.length} ${t.legs.length === 1 ? 'meci' : 'meciuri'}`}
              extra={<div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
                <Stat label="Zile urmărite" value={pyrDays.days} sub={`${pyrDays.picks} cu pariu · ${pyrDays.noBet} „AZI NU”`} />
                <Stat label="Run-uri (simulare)" value={pyrSim.runs.length} sub={`cel mai bun pas: ${Math.max(0, ...pyrSim.runs.map((r) => r.steps))}`} />
                <Stat label="Pași câștigați" value={pyrSim.steps.filter((x) => x.result === 'won').length} sub={`${pyrSim.steps.filter((x) => x.result === 'lost').length} pierduți`} />
                <Stat label="Total retras" value={`${pyrSim.totalWithdrawn.toFixed(2)} lei`} tone={pyrSim.totalWithdrawn > 0 ? 'win' : undefined} />
              </div>} />
              )}
            </Fold>
          )}

          {view === 'pro' && (
            <Fold title="Robotul" startOpen={tab === 'robot'}>
            <div className="space-y-4">
              <RobotPanel learning={stats.data?.learning} calibration={stats.data?.calibration} />
                  {stats.data?.learning?.walk_forward?.length ? (
                    <Card className="p-4"><h2 className="mb-2 text-sm font-semibold">Walk-forward: LogLoss model vs. bază (mai mic = mai bine)</h2>
                      <LazyChart className="h-56 md:h-64">{(R) => <R.ResponsiveContainer><R.LineChart data={stats.data!.learning!.walk_forward}><R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} /><R.XAxis dataKey="fold" minTickGap={16} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} /><R.YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} domain={['auto', 'auto']} /><R.Tooltip {...tip} /><R.Legend wrapperStyle={{ fontSize: 11 }} />
                        <R.Line activeDot={activeDot} dataKey="logloss_1x2" name="1X2 model" stroke="#2ee6a6" /><R.Line activeDot={activeDot} dataKey="baseline_1x2" name="1X2 bază" stroke="#2ee6a6" strokeDasharray="4 4" /><R.Line activeDot={activeDot} dataKey="logloss_ou25" name="O/U 2.5 model" stroke="#a78bfa" /><R.Line activeDot={activeDot} dataKey="baseline_ou25" name="O/U 2.5 bază" stroke="#a78bfa" strokeDasharray="4 4" /></R.LineChart></R.ResponsiveContainer>}</LazyChart>
                    </Card>
                  ) : null}
              <Card className="p-4"><h2 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Lightbulb className="h-4 w-4 text-warn" />Tipare detectate în rezultate</h2>
                <ul className="space-y-2">{recs.map((r, i) => <li key={i} className="rounded-lg bg-muted/40 px-3 py-2 text-sm">{r.text}</li>)}</ul>
              </Card>
            </div>
            </Fold>
          )}
        </>
      )}
    </div>
  );
}

/** Secțiune pliabilă. Linkurile vechi (?tab=zi) o lasă deschisă. */
function Fold({ title, startOpen, children }: { title: string; startOpen?: boolean; children: ReactNode }) {
  return (
    <details className="card group" {...(startOpen ? { open: true } : {})}>
      <summary className="flex min-h-[48px] cursor-pointer list-none items-center gap-2 px-4 text-sm font-bold">
        {title}
        <ChevronRight className="ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
      </summary>
      <div className="space-y-4 px-3 pb-3">{children}</div>
    </details>
  );
}

/** Egaluri Superbet: fiecare meci (selecția) și biletul de două, decontate automat. */
function SoftDrawMonitor({ tickets }: { tickets: Ticket[] }) {
  const legs = tickets.flatMap((t) => t.legs);
  const won = legs.filter((l) => l.result === 'won' || l.result === 'half_won').length;
  const lost = legs.filter((l) => l.result === 'lost' || l.result === 'half_lost').length;
  const pending = legs.filter((l) => !l.result).length;
  const settled = won + lost;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h2 className="text-sm font-semibold">Selecții — egalul, fiecare meci</h2>
        <p className="mt-1 text-xs text-muted-foreground">Intră în listă doar egalul la care Superbet e cu cel puțin 2% peste mediana pieței, cotă 2,80–3,60. Se decontează după scorul final.</p>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Selecții" value={legs.length} sub={`${pending} în curs`} />
          <Stat label="Câștigate" value={won} tone="win" />
          <Stat label="Pierdute" value={lost} tone="loss" />
          <Stat label="Rată" value={settled ? pct(won / settled) : '—'} sub={settled ? `din ${settled}` : 'încă nimic decontat'} />
        </div>
      </Card>
      <TicketSection tickets={tickets} groupTitle="Bilete de două egaluri" empty="Încă nu e niciun bilet de egaluri. Apare după următoarea actualizare, dacă Superbet are prețul peste piață." />
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
        <Stat label="ROI recomandări" value={signed(rec?.roi_pct ?? null, 1, '%')} tone={(rec?.roi_pct ?? 0) >= 0 ? 'win' : 'loss'} sub={rec ? `${rec.n} selecții · rată ${pct(rec.win_rate, 1)}` : undefined} />
        <Stat label="Bilete acumulator" value={tn} sub={`${tw} câștigate / ${tl} pierdute${tw + tl ? ` · ${signed(tp, 2)} u` : ''}`} tone={tw + tl ? (tp >= 0 ? 'win' : 'loss') : undefined} />
        <Stat label="Piramida" value={pn} sub={`${pw} câștigate / ${pl} pierdute`} />
      </div>
    </div>
  );
}
