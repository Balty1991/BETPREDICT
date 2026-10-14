import { useMemo, useState } from 'react';
import { LazyChart } from '@/components/LazyChart';
import { tip, activeDot } from '@/lib/chart';
import { block, series, groups, calibration, equity, oddsBand } from '@/lib/analytics';
import { marketTitle, resultLabel } from '@/lib/markets';
import { todayRo, pct, signed, monthLabel, odds as fo, num } from '@/lib/format';
import { Card, Stat, Segmented, Notice, Empty, ResultBadge } from '@/components/kit';
import type { ClvDoc, JournalRow, StatBlock } from '@/lib/types';
import { cn } from '@/lib/utils';

type Status = 'all' | 'settled' | 'pending';
type SortKey = 'date' | 'odds' | 'profit';
type Dist = 'odds' | 'market' | 'grade';
type Metric = 'roi' | 'wr' | 'profit';

const PAGE = 20;
const ax = { fontSize: 11, fill: 'hsl(var(--muted-foreground))' };

function clvTxt(v?: number | null) {
  return v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;
}

/** Statistici avansate + istoricul selecțiilor, pe rândurile deja filtrate ale paginii. */
export function AdvancedStats({ rows, clv, error }: { rows: JournalRow[]; clv?: ClvDoc | null; error?: string | null }) {
  const year = todayRo().slice(0, 4);
  const yearRows = useMemo(() => rows.filter((r) => r.date.startsWith(year)), [rows, year]);
  const outside = rows.length - yearRows.length;
  const annual = useMemo(() => block(yearRows), [yearRows]);
  const months = useMemo(() => series(yearRows, 'month'), [yearRows]);
  const daily = useMemo(() => series(yearRows, 'day'), [yearRows]);
  const eq = useMemo(() => {
    const nOf = new Map(daily.map((d) => [d.key, d.n]));
    return equity(yearRows).map((d) => ({ ...d, n: nOf.get(d.key) ?? 0 }));
  }, [yearRows, daily]);
  const cal = useMemo(() => calibration(yearRows)[0], [yearRows]);
  const [month, setMonth] = useState<string | null>(null);
  const [showRoi, setShowRoi] = useState(true);
  const [showWr, setShowWr] = useState(true);
  const [dist, setDist] = useState<Dist>('odds');
  const [metric, setMetric] = useState<Metric>('roi');
  const hasGrade = yearRows.some((r) => !!r.grade);
  const distRows = useMemo(() => {
    if (dist === 'odds') return groups(yearRows, (r) => oddsBand(r.odds)).sort((a, b) => (a.key ?? '').localeCompare(b.key ?? ''));
    if (dist === 'grade') return groups(yearRows, (r) => r.grade || 'fără grad');
    return groups(yearRows, (r) => r.market, marketTitle);
  }, [yearRows, dist]);
  const pickMonth = (key: string) => { setMonth((m) => (m === key ? null : key)); setLimit(20); };

  const [status, setStatus] = useState<Status>('all');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<SortKey>('date');
  const [asc, setAsc] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const resetHist = () => { setMonth(null); setStatus('all'); setQ(''); setSort('date'); setAsc(false); setLimit(PAGE); };

  const hist = useMemo(() => {
    const base = month ? yearRows.filter((r) => r.date.startsWith(month)) : yearRows;
    const byStatus = status === 'settled' ? base.filter((r) => r.result !== 'pending') : status === 'pending' ? base.filter((r) => r.result === 'pending') : base;
    const qq = q.trim().toLowerCase();
    const found = qq ? byStatus.filter((r) => `${r.match} ${r.league} ${r.label}`.toLowerCase().includes(qq)) : byStatus;
    const dir = asc ? 1 : -1;
    return [...found].sort((a, b) => {
      if (sort === 'odds') return (a.odds - b.odds) * dir;
      if (sort === 'profit') {
        if (a.profit == null && b.profit == null) return b.date.localeCompare(a.date);
        if (a.profit == null) return 1;
        if (b.profit == null) return -1;
        return (a.profit - b.profit) * dir;
      }
      return a.date.localeCompare(b.date) * dir || a.match.localeCompare(b.match, 'ro');
    });
  }, [yearRows, month, status, q, sort, asc]);
  const histBlock = useMemo(() => block(hist), [hist]);
  const pendingN = hist.filter((r) => r.result === 'pending').length;
  const showSource = hist.some((r) => !!r.source);
  const periodLabel = month ? monthLabel(month) : `anul ${year}`;

  if (error && !rows.length) {
    return <Notice>Istoricul nu s-a putut încărca. {error}</Notice>;
  }
  if (!yearRows.length) {
    return <Empty title={`Nicio selecție în ${year} pentru filtrele alese`}>{outside ? `${outside} selecții din perioadă sunt în alți ani și nu intră în vederea anului curent.` : 'Schimbă perioada sau filtrele de deasupra.'}</Empty>;
  }

  const small = annual.n < 20;
  const distChart = distRows.filter((b) => b.n >= 3).map((b) => ({
    key: b.key, name: b.name ?? b.key,
    roi: b.played ? b.roi_pct : null,
    wr: b.win_rate == null ? null : Math.round(b.win_rate * 1000) / 10,
    profit: b.played ? b.profit : null,
    n: b.n,
  }));
  const distKey = metric;
  const calPts = (cal?.bins ?? []).map((b) => ({
    name: `${Math.round(b.lo * 100)}–${Math.round(b.hi * 100)}%`,
    prezis: Math.round(b.p_avg * 1000) / 10,
    observat: Math.round(b.hit_rate * 1000) / 10,
    n: b.n,
  }));

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold">Statistici avansate · {year}</h2>
        <p className="mt-1 text-xs text-muted-foreground">Anul curent, din perioada și filtrele de deasupra. Profitul, ROI-ul și rata de câștig vin din aceleași funcții ca în Sumar: 1 unitate pe selecție cu cotă, fără cele în așteptare. Trecutul nu spune ce se va întâmpla.</p>
        {outside > 0 && <p className="mt-1 text-xs text-muted-foreground">{outside} selecții din perioada aleasă sunt în alți ani și nu sunt incluse.</p>}
        {small && <p className="mt-1 text-xs text-muted-foreground">Eșantion mic, sub 20 de selecții decontate — același prag ca la calibrare. Nu trage o concluzie din el.</p>}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Stat label="Decontate" value={annual.n} sub={`${annual.pending ?? 0} în așteptare`} />
        <Stat label="Profit" value={annual.played ? `${signed(annual.profit, 2)} u` : '—'} tone={annual.played ? (annual.profit >= 0 ? 'win' : 'loss') : undefined} sub={annual.played ? `${annual.played} cu cotă` : 'nicio cotă decontată'} />
        <Stat label="ROI" value={annual.played ? signed(annual.roi_pct, 1, '%') : '—'} tone={annual.played ? ((annual.roi_pct ?? 0) >= 0 ? 'win' : 'loss') : undefined} sub="doar decontate cu cotă" />
        <Stat label="Rată de câștig" value={pct(annual.win_rate, 1)} sub={`${annual.won}V / ${annual.lost}Î`} />
        <Stat label="Cotă medie" value={fo(annual.avg_odds)} sub={`șansă medie ${pct(annual.avg_p)}`} />
        <Stat label="CLV publicat" value={clv?.all?.n ? clvTxt(clv.all.avg) : '—'} tone={clv?.all?.n ? ((clv.all.avg ?? 0) >= 0 ? 'win' : 'loss') : undefined} sub={clv?.all?.n ? `${clv.all.n} cu închidere, nu doar ${year}` : 'nu e în jurnalul anului'} />
      </div>

      <Card className="overflow-hidden p-4">
        <h3 className="text-sm font-semibold">Profit cumulat</h3>
        <p className="mb-2 text-xs text-muted-foreground">Unități, pe zilele cu selecții decontate. Semnul e și în textul din tooltip.</p>
        {eq.length < 2 ? <p className="text-sm text-muted-foreground">Date insuficiente pentru o serie în timp.</p> : (
          <LazyChart className="h-56">{(R) => (
            <R.ResponsiveContainer><R.ComposedChart data={eq} margin={{ left: 0, right: 4 }}>
              <R.CartesianGrid strokeDasharray="3 3" opacity={0.2} />
              <R.XAxis dataKey="key" minTickGap={28} tickFormatter={(k: string) => k.slice(5)} tick={ax} />
              <R.YAxis width={36} tick={ax} />
              <R.Tooltip {...tip} formatter={(v: number, n: string) => (n === 'selecții' ? v : `${v >= 0 ? '+' : ''}${v.toFixed(2)} u`)} labelFormatter={(k) => String(k)} />
              <R.ReferenceLine y={0} stroke="#888" />
              <R.Area isAnimationActive={false} activeDot={activeDot} dataKey="cum" name="profit cumulat" stroke="#14b8a6" fill="hsl(var(--primary) / .15)" strokeWidth={2} />
            </R.ComposedChart></R.ResponsiveContainer>
          )}</LazyChart>
        )}
      </Card>

      <Card className="overflow-hidden p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Luni din {year}</h3>
          <div className="flex gap-1">
            <button type="button" aria-pressed={showRoi} onClick={() => setShowRoi((v) => !v)} className={cn('chip min-h-10', showRoi && 'chip-on')}>ROI</button>
            <button type="button" aria-pressed={showWr} onClick={() => setShowWr((v) => !v)} className={cn('chip min-h-10', showWr && 'chip-on')}>Câștig %</button>
          </div>
        </div>
        <p className="mb-2 text-xs text-muted-foreground">Atinge o lună ca să vezi aceleași selecții în istoric. Încă o atingere revine la tot anul.</p>
        {!months.length ? <p className="text-sm text-muted-foreground">Nicio lună cu selecții decontate.</p> : (
          <LazyChart className="h-56">{(R) => (
            <R.ResponsiveContainer><R.ComposedChart data={months.map((m) => ({ ...m, label: monthLabel(m.key).replace(` ${year}`, ''), wr: m.win_rate == null ? null : Math.round(m.win_rate * 1000) / 10 }))} margin={{ left: 0, right: 4 }}>
              <R.CartesianGrid strokeDasharray="3 3" opacity={0.2} />
              <R.XAxis dataKey="label" minTickGap={12} tick={ax} />
              <R.YAxis yAxisId="l" width={32} tick={ax} />
              <R.YAxis yAxisId="r" orientation="right" width={28} tick={ax} />
              <R.Tooltip {...tip} formatter={(v: number, n: string, it: { payload?: StatBlock }) => `${typeof v === 'number' ? (n === 'selecții' ? v : n === 'câștig %' ? `${v.toFixed(1)}%` : `${v >= 0 ? '+' : ''}${n === 'ROI %' ? v.toFixed(1) + '%' : v.toFixed(2) + ' u'}`) : v}${it?.payload?.n != null && n !== 'selecții' ? '' : ''}`} />
              <R.ReferenceLine yAxisId="l" y={0} stroke="#888" />
              <R.Bar isAnimationActive={false} yAxisId="l" dataKey="profit" name="profit u" radius={[4, 4, 0, 0]} onClick={(d: { key?: string }) => d?.key && pickMonth(d.key)}>
                {months.map((m) => <R.Cell key={m.key} fill={m.key === month ? 'hsl(var(--primary))' : m.profit >= 0 ? '#10b981' : '#f43f5e'} cursor="pointer" />)}
              </R.Bar>
              {showRoi && <R.Line isAnimationActive={false} yAxisId="r" dataKey="roi_pct" name="ROI %" stroke="#f59e0b" activeDot={activeDot} connectNulls />}
              {showWr && <R.Line isAnimationActive={false} yAxisId="r" dataKey="wr" name="câștig %" stroke="#6366f1" activeDot={activeDot} connectNulls />}
            </R.ComposedChart></R.ResponsiveContainer>
          )}</LazyChart>
        )}
        <div className="mt-2 flex gap-1.5 overflow-x-auto scrollbar-none" role="group" aria-label="Luni">
          <button type="button" aria-pressed={month == null} onClick={() => { setMonth(null); setLimit(PAGE); }} className={cn('chip min-h-10 shrink-0', month == null && 'chip-on')}>Tot anul</button>
          {months.map((m) => (
            <button key={m.key} type="button" aria-pressed={month === m.key} onClick={() => pickMonth(m.key)} className={cn('chip min-h-10 shrink-0', month === m.key && 'chip-on')}>
              {monthLabel(m.key).replace(` ${year}`, '')} {signed(m.profit, 1)}u
            </button>
          ))}
        </div>
        <table className="mt-3 w-full text-xs">
          <caption className="sr-only">Rezumat lunar {year}</caption>
          <thead className="text-muted-foreground"><tr><th className="py-1 text-left font-medium">Lună</th><th className="text-right font-medium">n</th><th className="text-right font-medium">Profit</th><th className="text-right font-medium">ROI</th><th className="text-right font-medium">Câștig</th></tr></thead>
          <tbody>{months.map((m) => (
            <tr key={m.key} className="border-t"><td className="py-1">{monthLabel(m.key)}</td><td className="text-right tabular-nums">{m.n}</td><td className={cn('text-right tabular-nums', m.profit >= 0 ? 'text-win' : 'text-loss')}>{m.played ? `${signed(m.profit, 2)} u` : '—'}</td><td className="text-right tabular-nums">{m.played ? signed(m.roi_pct, 1, '%') : '—'}</td><td className="text-right tabular-nums">{pct(m.win_rate)}</td></tr>
          ))}</tbody>
        </table>
        <p className="mt-2 text-xs text-muted-foreground">Total {year}: {annual.n} decontate{annual.played ? `, profit ${signed(annual.profit, 2)} u, ROI ${signed(annual.roi_pct, 1, '%')}` : ''}.</p>
      </Card>

      <Card className="overflow-hidden p-4">
        <h3 className="text-sm font-semibold">Calibrare pe intervale</h3>
        <p className="mb-2 text-xs text-muted-foreground">Șansa medie estimată față de rata observată, aceleași intervale de 10% ca în Calibrare. Doar câștigat/pierdut, n={cal?.n ?? 0}{cal?.ece != null ? `, ECE ${num(cal.ece, 3)}` : ''}.</p>
        {!calPts.length ? <p className="text-sm text-muted-foreground">Date insuficiente pentru calibrare.</p> : (
          <>
            {(cal?.n ?? 0) < 20 && <p className="mb-2 text-xs text-muted-foreground">Eșantion mic, sub 20. Intervalele nu sunt o calibrare stabilă.</p>}
            <LazyChart className="h-56">{(R) => (
              <R.ResponsiveContainer><R.ComposedChart data={calPts} margin={{ left: 0, right: 4 }}>
                <R.CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                <R.XAxis dataKey="name" minTickGap={8} tick={ax} />
                <R.YAxis width={32} domain={[0, 100]} tick={ax} />
                <R.Tooltip {...tip} formatter={(v: number, _n: string, it: { payload?: { n?: number } }) => `${v.toFixed(1)}% · ${it?.payload?.n ?? 0} sel.`} />
                <R.Line isAnimationActive={false} dataKey="prezis" name="estimat %" stroke="#14b8a6" activeDot={activeDot} />
                <R.Line isAnimationActive={false} dataKey="observat" name="observat %" stroke="#f59e0b" activeDot={activeDot} />
              </R.ComposedChart></R.ResponsiveContainer>
            )}</LazyChart>
          </>
        )}
      </Card>

      <Card className="overflow-hidden p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Distribuție</h3>
          <Segmented size="sm" value={metric} onChange={setMetric} options={[{ value: 'roi', label: 'ROI' }, { value: 'wr', label: 'Câștig' }, { value: 'profit', label: 'Profit' }]} />
        </div>
        <Segmented size="sm" value={dist} onChange={setDist} options={[{ value: 'odds', label: 'Cotă' }, { value: 'market', label: 'Piață' }, { value: 'grade', label: 'Încredere' }]} />
        {dist === 'grade' && !hasGrade ? <p className="mt-2 text-sm text-muted-foreground">Gradul de încredere nu este în jurnalul acestui an.</p> : !distChart.length ? <p className="mt-2 text-sm text-muted-foreground">Niciun grup cu cel puțin 3 selecții decontate.</p> : (
          <LazyChart className="mt-2 h-56">{(R) => (
            <R.ResponsiveContainer><R.BarChart data={distChart} layout="vertical" margin={{ left: 0, right: 8 }}>
              <R.CartesianGrid strokeDasharray="3 3" opacity={0.2} />
              <R.XAxis type="number" tick={ax} />
              <R.YAxis type="category" dataKey="name" width={84} tick={ax} />
              <R.Tooltip {...tip} formatter={(v: number, _n: string, it: { payload?: { n?: number } }) => `${metric === 'profit' ? `${v >= 0 ? '+' : ''}${v.toFixed(2)} u` : `${v.toFixed(1)}%`} · ${it?.payload?.n ?? 0} sel.`} />
              <R.ReferenceLine x={metric === 'wr' ? 50 : 0} stroke="#888" />
              <R.Bar isAnimationActive={false} dataKey={distKey} name={metric === 'profit' ? 'profit' : metric === 'wr' ? 'câștig %' : 'ROI %'} radius={[0, 4, 4, 0]}>
                {distChart.map((b) => <R.Cell key={b.key} fill={(metric === 'wr' ? (b.wr ?? 0) >= 50 : ((metric === 'profit' ? b.profit : b.roi) ?? 0) >= 0) ? '#10b981' : '#f43f5e'} />)}
              </R.Bar>
            </R.BarChart></R.ResponsiveContainer>
          )}</LazyChart>
        )}
        <p className="mt-2 text-xs text-muted-foreground">Graficul arată grupuri cu cel puțin 3 selecții decontate. ROI-ul lipsește unde nu există cotă.</p>
      </Card>

      <section className="space-y-3" aria-labelledby="hist-title">
        <div>
          <h3 id="hist-title" className="text-sm font-semibold">Istoricul selecțiilor</h3>
          <p className="mt-1 text-xs text-muted-foreground">{hist.length} selecții · {periodLabel}{month ? ' (aleasă pe grafic)' : ''} · {histBlock.n} decontate, {pendingN} în așteptare{status !== 'pending' && histBlock.played ? ` · profit decontat ${signed(histBlock.profit, 2)} u` : ''}.</p>
          {small && <p className="mt-1 text-xs text-muted-foreground">Eșantion mic, sub 20 de selecții decontate pe anul {year}.</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input aria-label="Caută echipă, ligă sau selecție" className="input min-h-11 min-w-0 flex-1 basis-full sm:basis-40" placeholder="Echipă, ligă sau selecție" value={q} onChange={(e) => { setQ(e.target.value); setLimit(PAGE); }} />
          <Segmented size="sm" value={status} onChange={(v) => { setStatus(v); setLimit(PAGE); }} options={[{ value: 'all', label: 'Toate' }, { value: 'settled', label: 'Decontate' }, { value: 'pending', label: 'În așteptare' }]} />
          <select aria-label="Sortare" className="input min-h-11 w-auto" value={`${sort}-${asc ? 'asc' : 'desc'}`} onChange={(e) => { const [k, d] = e.target.value.split('-'); setSort(k as SortKey); setAsc(d === 'asc'); }}>
            <option value="date-desc">Dată, noi</option>
            <option value="date-asc">Dată, vechi</option>
            <option value="odds-desc">Cotă, mare</option>
            <option value="odds-asc">Cotă, mică</option>
            <option value="profit-desc">Profit, mare</option>
            <option value="profit-asc">Profit, mic</option>
          </select>
        </div>
        {!hist.length ? (
          <Empty title="Nicio selecție pentru filtrele istoricului"><span>Căutarea, luna și starea nu schimbă graficele.</span><div className="mt-2"><button type="button" className="btn btn-outline min-h-11" onClick={resetHist}>Resetează filtrele istoricului</button></div></Empty>
        ) : (
          <>
            <ul className="space-y-2 md:hidden">
              {hist.slice(0, limit).map((r, i) => <HistoryCard key={`${r.match_id}-${r.market}-${r.label}-${i}`} r={r} showSource={showSource} />)}
            </ul>
            <div className="hidden overflow-hidden md:block">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground"><tr>
                  <th className="py-1 text-left font-medium">Dată</th><th className="text-left font-medium">Meci</th><th className="text-left font-medium">Ligă</th><th className="text-left font-medium">Selecție</th>
                  <th className="text-right font-medium">Cotă</th><th className="text-right font-medium">Șansă</th><th className="text-left font-medium">Încredere</th><th className="text-left font-medium">Rezultat</th><th className="text-right font-medium">Scor</th><th className="text-right font-medium">Profit</th>
                  {showSource && <th className="text-left font-medium">Sursă</th>}
                </tr></thead>
                <tbody>{hist.slice(0, limit).map((r, i) => (
                  <tr key={`${r.match_id}-${r.market}-${i}`} className="border-t">
                    <td className="whitespace-nowrap py-1.5 tabular-nums">{r.date.slice(5)}</td>
                    <td className="min-w-[160px] whitespace-normal">{r.match}</td>
                    <td className="min-w-[110px] whitespace-normal text-muted-foreground">{r.league}</td>
                    <td className="max-w-[160px] truncate">{r.label}<span className="block text-[11px] text-muted-foreground">{marketTitle(r.market)}</span></td>
                    <td className="text-right tabular-nums">{fo(r.odds)}</td>
                    <td className="text-right tabular-nums">{r.p == null ? '—' : pct(r.p)}</td>
                    <td>{r.grade || '—'}</td>
                    <td><ResultBadge r={r.result} /></td>
                    <td className="text-right tabular-nums">{r.score || '—'}</td>
                    <td className={cn('text-right tabular-nums', r.profit == null ? 'text-muted-foreground' : r.profit >= 0 ? 'text-win' : 'text-loss')}>{r.result === 'pending' || r.profit == null ? '—' : `${signed(r.profit, 2)} u`}</td>
                    {showSource && <td className="text-muted-foreground">{r.source || '—'}</td>}
                  </tr>
                ))}</tbody>
              </table>
            </div>
            {hist.length > limit && <button type="button" className="btn btn-outline min-h-11 w-full" onClick={() => setLimit((n) => n + PAGE)}>Încarcă mai multe ({hist.length - limit} rămase)</button>}
          </>
        )}
      </section>
    </div>
  );
}

function HistoryCard({ r, showSource }: { r: JournalRow; showSource: boolean }) {
  return (
    <li className="card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] text-muted-foreground">{r.date} · {r.league}</div>
          <div className="break-words font-semibold">{r.match}</div>
          <div className="text-sm">{r.label}</div>
          <div className="text-[11px] text-muted-foreground">{marketTitle(r.market)}</div>
        </div>
        <ResultBadge r={r.result} />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs tabular-nums text-muted-foreground">
        <span>Cotă <b className="text-foreground">{fo(r.odds)}</b></span>
        <span>Șansă <b className="text-foreground">{r.p == null ? '—' : pct(r.p)}</b></span>
        <span>Încredere <b className="text-foreground">{r.grade || '—'}</b></span>
        <span>Scor <b className="text-foreground">{r.score || '—'}</b></span>
        <span>Profit <b className={cn(r.profit == null ? 'text-foreground' : r.profit >= 0 ? 'text-win' : 'text-loss')}>{r.result === 'pending' || r.profit == null ? '—' : `${signed(r.profit, 2)} u`}</b></span>
        {showSource && <span>Sursă <b className="text-foreground">{r.source || '—'}</b></span>}
      </div>
      <span className="sr-only">{resultLabel(r.result)}</span>
    </li>
  );
}
