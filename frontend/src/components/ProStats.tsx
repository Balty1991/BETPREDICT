import { useMemo, useState } from 'react';
import { LazyChart } from '@/components/LazyChart';
import { Card, Stat, Segmented, Notice } from '@/components/kit';
import { calibration, groups, oddsBand } from '@/lib/analytics';
import { marketTitle } from '@/lib/markets';
import { pct, signed, num, odds as fo } from '@/lib/format';
import type { ClvDoc, JournalRow, StatBlock, TicketBucket } from '@/lib/types';
import { cn } from '@/lib/utils';

const tip = { contentStyle: { background: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))', fontSize: 12, borderRadius: 12 }, cursor: { fill: 'hsl(var(--accent))', opacity: 0.4 } };
const ax = { fontSize: 11, fill: 'hsl(var(--muted-foreground))' };
const WD = ['Duminică', 'Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă'];
const BANK0 = 100;

const played = (r: JournalRow) => r.result !== 'pending' && r.result !== 'void' && r.odds != null && r.odds > 1;

/** Curba băncii (100u, 1u/selecție), drawdown, profit așteptat vs real (noroc vs skill). */
export function bankrollSeries(rows: JournalRow[]) {
  const ps = rows.filter(played).sort((a, b) => a.date.localeCompare(b.date));
  let bank = BANK0, peak = BANK0, xp = 0, act = 0, maxDd = 0, varSum = 0;
  const out: Array<{ i: number; date: string; bank: number; dd: number; xprofit: number; profit: number }> = [];
  ps.forEach((r, i) => {
    const p = r.p ?? 1 / r.odds;
    const pr = r.profit ?? 0;
    bank += pr; act += pr; xp += p * r.odds - 1; varSum += p * (1 - p) * r.odds * r.odds;
    peak = Math.max(peak, bank); const dd = bank - peak; maxDd = Math.min(maxDd, dd);
    out.push({ i: i + 1, date: r.date, bank: +bank.toFixed(2), dd: +dd.toFixed(2), xprofit: +xp.toFixed(2), profit: +act.toFixed(2) });
  });
  const sd = Math.sqrt(varSum);
  return { out, n: ps.length, bank, maxDd, xp, act, sd, z: sd ? (act - xp) / sd : null };
}

function SegTable({ title, rows }: { title: string; rows: StatBlock[] }) {
  if (!rows.length) return null;
  const maxAbs = Math.max(1, ...rows.map((r) => Math.abs(r.roi_pct ?? 0)));
  return (
    <Card className="overflow-hidden">
      <h3 className="px-4 pt-3 text-sm font-semibold">{title}</h3>
      <div className="overflow-x-auto"><table className="pro-table w-full text-sm">
        <thead><tr><th className="text-left">Segment</th><th>n</th><th>Câștig</th><th>Cotă</th><th>Profit</th><th className="w-[30%]">ROI</th></tr></thead>
        <tbody>{rows.slice(0, 15).map((b) => (
          <tr key={b.key}><td className="max-w-[180px] truncate text-left">{b.name ?? b.key}</td><td>{b.played ?? b.n}</td><td>{pct(b.win_rate)}</td><td>{fo(b.avg_odds ?? null)}</td>
            <td className={b.profit >= 0 ? 'text-win' : 'text-loss'}>{signed(b.profit, 2)}</td>
            <td><div className="flex items-center justify-end gap-2"><span className={cn('font-semibold', (b.roi_pct ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{signed(b.roi_pct, 1, '%')}</span>
              <span aria-hidden className="relative h-1.5 w-16 overflow-hidden rounded-full bg-muted"><span className={cn('absolute inset-y-0 left-1/2', (b.roi_pct ?? 0) >= 0 ? 'bg-[hsl(var(--win))]' : 'right-1/2 left-auto bg-[hsl(var(--loss))]')} style={{ width: `${(Math.abs(b.roi_pct ?? 0) / maxAbs) * 50}%` }} /></span></div></td></tr>
        ))}</tbody></table></div>
    </Card>
  );
}

type Scope = 'rec' | 'pub' | 'all';
const SCOPE_OK: Record<Scope, (r: JournalRow) => boolean> = {
  rec: (r) => r.source === 'recomandată',
  pub: (r) => r.source === 'recomandată' || r.source === 'principală',
  all: () => true,
};

function Buckets({ rows }: { rows?: TicketBucket[] }) {
  if (!rows?.length) return null;
  return (
    <Card className="overflow-hidden">
      <h3 className="px-4 pt-3 text-sm font-semibold">Bilete publicate — cost vs. câștig</h3>
      <div className="overflow-x-auto"><table className="pro-table w-full text-sm">
        <thead><tr><th className="text-left">Tip</th><th>Bilete</th><th>V / Î</th><th>În joc</th><th>Cost</th><th>Returnat</th><th>Profit</th><th>ROI</th></tr></thead>
        <tbody>{rows.map((b) => (
          <tr key={b.bucket}><td className="text-left font-semibold">{b.bucket}</td><td>{b.n}</td><td>{b.won}/{b.lost}</td><td>{b.pending}</td><td>{num(b.cost, 2)}u</td><td>{num(b.returned, 2)}u</td>
            <td className={b.profit >= 0 ? 'text-win' : 'text-loss'}>{signed(b.profit, 2)}</td><td className={cn('font-semibold', (b.roi_pct ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{signed(b.roi_pct, 1, '%')}</td></tr>
        ))}</tbody></table></div>
    </Card>
  );
}

export function ProStats({ rows: allRows, clv, buckets }: { rows: JournalRow[]; clv?: ClvDoc; buckets?: TicketBucket[] }) {
  const [scope, setScope] = useState<Scope>('rec');
  const rows = useMemo(() => allRows.filter(SCOPE_OK[scope]), [allRows, scope]);
  const bk = useMemo(() => bankrollSeries(rows), [rows]);
  const playedRows = useMemo(() => rows.filter(played), [rows]);
  const cal = useMemo(() => calibration(rows)[0], [rows]);
  const seg = useMemo(() => ({
    market: groups(playedRows, (r) => r.market, marketTitle),
    league: groups(playedRows, (r) => r.league).slice(0, 15),
    band: groups(playedRows, (r) => oddsBand(r.odds)).sort((a, b) => (a.key ?? '').localeCompare(b.key ?? '')),
    wd: groups(playedRows, (r) => String(new Date(`${r.date}T12:00:00`).getDay()), (k) => WD[Number(k)]).sort((a, b) => ((Number(a.key) + 6) % 7) - ((Number(b.key) + 6) % 7)),
    grade: groups(playedRows, (r) => r.grade ?? '—', (k) => `Grad ${k}`).sort((a, b) => (a.key ?? '').localeCompare(b.key ?? '')),
  }), [playedRows]);
  const clvRows = (clv?.by_market ?? []).filter((c) => c.n >= 3 && c.avg != null).map((c) => ({ name: marketTitle(c.key ?? ''), clv: +((c.avg ?? 0) * 100).toFixed(2), n: c.n }));
  const verdict = bk.z == null ? '—' : bk.z > 1.5 ? 'Peste așteptări (posibil noroc)' : bk.z < -1.5 ? 'Sub așteptări (posibil ghinion)' : 'În linie cu modelul';

  return (
    <div className="space-y-4">
      <Segmented size="sm" value={scope} onChange={setScope} options={[{ value: 'rec', label: 'Recomandate' }, { value: 'pub', label: 'Publicate (pontul meciului)' }, { value: 'all', label: 'Toate piețele · analiză' }]} />
      {scope === 'all' && <Notice><b>Analiză, nu pariuri.</b> „Toate piețele” include fiecare piață a fiecărui meci analizat, inclusiv cele pe care Robotul nu le-ar juca. Folosește-l pentru calibrare, nu ca rezultat al pariurilor.</Notice>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Bancă (start 100u)" value={`${num(bk.bank, 1)}u`} tone={bk.bank >= BANK0 ? 'win' : 'loss'} sub={`${bk.n} pariuri cu cotă · 1u fix`} />
        <Stat label="Drawdown maxim" value={`${num(bk.maxDd, 1)}u`} tone="loss" sub="cea mai mare cădere de la vârf" />
        <Stat label="CLV mediu (toate publicate)" value={clv?.all?.avg != null ? signed(clv.all.avg * 100, 2, '%') : '—'} tone={(clv?.all?.avg ?? 0) >= 0 ? 'win' : 'loss'} sub={clv?.all ? `bate închiderea: ${pct(clv.all.beat_rate)} · n=${clv.all.n}` : 'se acumulează'} />
        <Stat label="Noroc vs skill" value={bk.z == null ? '—' : `${bk.z >= 0 ? '+' : ''}${bk.z.toFixed(2)}σ`} sub={verdict} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4"><h3 className="text-sm font-semibold">Curba băncii și drawdown</h3>
          <p className="mb-2 text-xs text-muted-foreground">Pariu cu pariu, miză fixă 1u, doar selecțiile cu cotă reală.</p>
          {bk.out.length < 2 ? <p className="text-sm text-muted-foreground">Date insuficiente.</p> : <LazyChart className="h-60">{(R) => <R.ResponsiveContainer><R.ComposedChart data={bk.out}><defs><linearGradient id="pbank" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.45} /><stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} /></linearGradient></defs><R.CartesianGrid strokeDasharray="2 6" opacity={0.25} /><R.XAxis dataKey="i" tick={ax} minTickGap={24} /><R.YAxis yAxisId="b" tick={ax} domain={['auto', 'auto']} /><R.YAxis yAxisId="d" orientation="right" tick={ax} /><R.Tooltip {...tip} labelFormatter={(i) => `pariul #${i} · ${bk.out[Number(i) - 1]?.date ?? ''}`} /><R.ReferenceLine yAxisId="b" y={BANK0} stroke="#888" strokeDasharray="3 3" /><R.Bar yAxisId="d" dataKey="dd" name="drawdown" fill="hsl(var(--loss))" opacity={0.45} /><R.Area yAxisId="b" dataKey="bank" name="bancă" stroke="hsl(var(--primary))" strokeWidth={2.2} fill="url(#pbank)" dot={false} /></R.ComposedChart></R.ResponsiveContainer>}</LazyChart>}
        </Card>
        <Card className="p-4"><h3 className="text-sm font-semibold">Noroc vs skill — profit real vs așteptat</h3>
          <p className="mb-2 text-xs text-muted-foreground">Așteptat = Σ(șansă × cotă − 1). Real peste așteptat = noroc; sub = ghinion. σ = {num(bk.sd, 1)}u.</p>
          {bk.out.length < 2 ? <p className="text-sm text-muted-foreground">Date insuficiente.</p> : <LazyChart className="h-60">{(R) => <R.ResponsiveContainer><R.LineChart data={bk.out}><R.CartesianGrid strokeDasharray="2 6" opacity={0.25} /><R.XAxis dataKey="i" tick={ax} minTickGap={24} /><R.YAxis tick={ax} /><R.Tooltip {...tip} /><R.Legend wrapperStyle={{ fontSize: 11 }} /><R.ReferenceLine y={0} stroke="#888" /><R.Line dataKey="profit" name="real" stroke="hsl(var(--primary))" dot={false} strokeWidth={2.2} /><R.Line dataKey="xprofit" name="așteptat (model)" stroke="hsl(var(--glow-3))" strokeDasharray="5 4" dot={false} strokeWidth={2} /></R.LineChart></R.ResponsiveContainer>}</LazyChart>}
        </Card>
        <Card className="p-4"><h3 className="text-sm font-semibold">CLV pe piață</h3>
          <p className="mb-2 text-xs text-muted-foreground">Pozitiv = am prins o cotă mai bună decât cea de la start. Cel mai bun semn de skill pe termen lung.</p>
          {!clvRows.length ? <p className="text-sm text-muted-foreground">CLV-ul se acumulează după start-ul meciurilor (n ≥ 3 pe piață).</p> : <LazyChart className="h-60">{(R) => <R.ResponsiveContainer><R.BarChart data={clvRows} layout="vertical" margin={{ left: 0, right: 8 }}><R.CartesianGrid strokeDasharray="2 6" opacity={0.25} /><R.XAxis type="number" tick={ax} unit="%" /><R.YAxis type="category" dataKey="name" tick={ax} width={92} /><R.Tooltip {...tip} formatter={(v: number) => `${v.toFixed(2)}%`} /><R.ReferenceLine x={0} stroke="#888" /><R.Bar dataKey="clv" name="CLV" radius={[4, 4, 4, 4]}>{clvRows.map((c) => <R.Cell key={c.name} fill={c.clv >= 0 ? 'hsl(var(--win))' : 'hsl(var(--loss))'} />)}</R.Bar></R.BarChart></R.ResponsiveContainer>}</LazyChart>}
        </Card>
        <Card className="p-4"><h3 className="text-sm font-semibold">Calibrare — prezis vs real</h3>
          <p className="mb-2 text-xs text-muted-foreground">Diagonala = probabilități perfecte. Mărimea punctului = numărul de selecții.</p>
          {!cal ? <p className="text-sm text-muted-foreground">Date insuficiente.</p> : <LazyChart className="h-60">{(R) => <R.ResponsiveContainer><R.ComposedChart data={cal.bins}><R.CartesianGrid strokeDasharray="2 6" opacity={0.25} /><R.XAxis type="number" dataKey="p_avg" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={ax} /><R.YAxis type="number" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={ax} /><R.Tooltip {...tip} formatter={(v: number) => `${(v * 100).toFixed(1)}%`} /><R.ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#888" strokeDasharray="4 4" /><R.Line dataKey="hit_rate" name="real" stroke="hsl(var(--primary))" strokeWidth={2} dot={{ r: 4, fill: 'hsl(var(--primary))' }} /></R.ComposedChart></R.ResponsiveContainer>}</LazyChart>}
        </Card>
      </div>

      <Buckets rows={buckets} />
      <h2 className="pt-2">Pe segmente</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <SegTable title="Pe piață" rows={seg.market} />
        <SegTable title="Pe interval de cotă" rows={seg.band} />
        <SegTable title="Pe ligă (top 15)" rows={seg.league} />
        <SegTable title="Pe zi a săptămânii" rows={seg.wd} />
        <SegTable title="Pe grad de încredere" rows={seg.grade} />
      </div>
    </div>
  );
}
