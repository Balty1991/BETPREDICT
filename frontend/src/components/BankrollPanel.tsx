import { useMemo, useState } from 'react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { LazyChart } from '@/components/LazyChart';
import { Card, InfoTip, Notice, Segmented, Skeleton } from '@/components/kit';
import { tip, activeDot } from '@/lib/chart';
import { cn } from '@/lib/utils';

type Calib = { n: number; buckets: Array<{ lo: number; hi: number; n: number; pred: number; hit: number }>; pred: number | null; hit: number | null; brier: number | null; ece: number | null };
type Product = {
  id: 's10' | 'long' | 'pyr2'; label: string; bets: number; won: number; lost: number; pending: number;
  hit: number | null; expected_hit: number | null; expected_wins: number; profit: number; roi: number | null; roi_no_bonus: number | null;
  avg_odds: number | null; best: number | null; max_drawdown: number; streaks: { win: number; loss: number; current: number };
  by_day: Array<{ day: string; n: number; won: number; profit: number; cum: number }>;
  clv: { n: number; avg: number | null; median: number | null; beat: number | null }; calibration: Calib;
  legs_settled: number; legs_hit: number | null;
  series?: { runs: number; best: number; current: number; avg: number | null; lengths: number[] };
};
type SimIn = { p_mean: number; payout: number; per_day: number; ev: number; legs: number; leg_ratio: number; p_model: number };
type Plan = {
  plan: string; label: string; stakes: Record<string, number>; p5: number; p25: number; p50: number; p75: number; p95: number; mean: number;
  p_profit: number; p_down20: number; mdd_median: number; ev_pct: Record<string, number>;
  fan: Array<{ day: number; p5: number; p25: number; p50: number; p75: number; p95: number }>;
};
type BankrollDoc = {
  generated_at: string; since: string | null; days: number; products: Product[];
  sim: { horizon_days: number; paths: number; start_bank: number; inputs: Record<string, SimIn>; pyramid: { stake_fraction: number; suggest_at: number }; plans: Plan[]; sample_small: boolean };
};

const ax = { fontSize: 11, fill: 'hsl(var(--muted-foreground))' };
const WIN = '#2ee6a6';
const LOSS = '#ff5c7a';
const LABEL: Record<string, string> = { s10: 'Cotă ~10', long: 'Bilete lungi', pyr2: 'Piramidă cotă 2' };

const p100 = (x: number | null | undefined, d = 0) => (x == null ? '—' : `${(x * 100).toFixed(d).replace('.', ',')}%`);
const sgn = (x: number | null | undefined, d = 0, suf = '%', mul = 100) => (x == null ? '—' : `${x * mul >= 0 ? '+' : '−'}${Math.abs(x * mul).toFixed(d).replace('.', ',')}${suf}`);
const units = (x: number) => `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(1).replace('.', ',')} u`;
const tone = (x: number | null | undefined) => (x == null ? '' : x >= 0 ? 'text-win' : 'text-loss');
const chance = (p: number) => (p >= 0.01 ? p100(p, 1) : `1 la ${Math.round(1 / p).toLocaleString('ro-RO')}`);
const dayShort = (d: string) => d.slice(8, 10) + '.' + d.slice(5, 7);

function Tile({ label, value, sub, cls, help }: { label: string; value: string; sub?: string; cls?: string; help?: string }) {
  return (
    <div className="rounded-2xl border bg-card/50 p-3">
      <div className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground">{label}{help && <InfoTip text={help} />}</div>
      <div className={cn('num mt-0.5 text-lg font-extrabold leading-tight tabular-nums', cls)}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{sub}</div>}
    </div>
  );
}

function ProductSummary({ p }: { p: Product }) {
  const streak = p.streaks.current;
  return (
    <div className="grid grid-cols-2 gap-2">
      <Tile label="Bilete decontate" value={String(p.bets)} sub={`${p.won} câștigate · ${p.lost} pierdute${p.pending ? ` · ${p.pending} în joc` : ''}`} />
      <Tile label="Câștigate vs așteptat" value={p.bets ? `${p.won} / ${p.expected_wins.toFixed(p.expected_wins < 1 ? 2 : 1).replace('.', ',')}` : '—'}
        sub={p.bets ? `rată ${p100(p.hit, 1)} față de ${p.expected_hit != null && p.expected_hit < 0.01 ? chance(p.expected_hit) : p100(p.expected_hit, 1)} estimat` : 'nimic decontat încă'}
        cls={p.bets ? (p.won >= p.expected_wins ? 'text-win' : 'text-loss') : ''} help="Câștigate efectiv față de suma șanselor publicate pe bilete. Pe puține bilete diferența e mai ales noroc." />
      <Tile label="ROI cu SuperBonus" value={sgn(p.roi, 1)} cls={tone(p.roi)} sub={p.roi == null ? 'miză egală pe bilet' : `fără bonus ${sgn(p.roi_no_bonus, 1)} · profit ${units(p.profit)}`} help="Miză de 1 unitate pe fiecare bilet. Câștigul include SuperBonusul Superbet unde se aplică." />
      <Tile label="Scădere maximă" value={p.bets ? `−${p.max_drawdown.toFixed(1).replace('.', ',')} u` : '—'} cls={p.max_drawdown ? 'text-loss' : ''} sub="cea mai mare cădere de la un vârf" />
      <Tile label="Serie maximă" value={p.bets ? `${p.streaks.win} / ${p.streaks.loss}` : '—'} sub={`câștigate / pierdute la rând${streak ? ` · acum ${Math.abs(streak)} ${streak > 0 ? 'câștigate' : 'pierdute'}` : ''}`} />
      <Tile label="CLV selecții" value={p.clv.n ? sgn(p.clv.avg, 1) : '—'} cls={tone(p.clv.avg)}
        sub={p.clv.n ? `${p100(p.clv.beat)} peste închidere · ${p.clv.n} selecții` : 'fără cote de închidere încă'}
        help="Cota luată față de cota Superbet de la start. Peste zero de mult timp = prețuri bune, chiar dacă biletele pierd." />
      {p.series && (
        <Tile label="Record serie piramidă" value={p.series.runs ? String(p.series.best) : '—'} sub={p.series.runs ? `pași câștigați · ${p.series.runs} serii, medie ${String(p.series.avg ?? 0).replace('.', ',')} · acum ${p.series.current}` : 'nicio serie încă'} />
      )}
      <Tile label="Selecții intrate" value={p100(p.legs_hit, 1)} sub={p.legs_settled ? `${p.legs_settled} selecții decontate` : 'nimic decontat'} />
    </div>
  );
}

function ProfitChart({ p }: { p: Product }) {
  if (p.by_day.length < 2) return <p className="text-sm text-muted-foreground">Curba apare după cel puțin două zile cu bilete decontate.</p>;
  return (
    <LazyChart className="h-52">{(R) => (
      <R.ResponsiveContainer><R.ComposedChart data={p.by_day} margin={{ left: 0, right: 4, top: 4 }}>
        <defs>
          <linearGradient id={`bk-${p.id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
            <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} />
        <R.XAxis dataKey="day" tickFormatter={dayShort} minTickGap={24} tick={ax} />
        <R.YAxis width={38} tick={ax} />
        <R.Tooltip {...tip} labelFormatter={(d) => dayShort(String(d))} formatter={(v: number, n: string) => [units(v), n]} />
        <R.ReferenceLine y={0} stroke="#888" />
        <R.Bar isAnimationActive={false} dataKey="profit" name="ziua" barSize={10} radius={[3, 3, 0, 0]}>
          {p.by_day.map((d) => <R.Cell key={d.day} fill={d.profit >= 0 ? WIN : LOSS} fillOpacity={0.55} />)}
        </R.Bar>
        <R.Area isAnimationActive={false} type="monotone" dataKey="cum" name="cumulat" stroke="hsl(var(--primary))" strokeWidth={2} fill={`url(#bk-${p.id})`} activeDot={activeDot} />
      </R.ComposedChart></R.ResponsiveContainer>
    )}</LazyChart>
  );
}

function CalibChart({ c }: { c: Calib }) {
  if (!c.buckets.length) return <p className="text-sm text-muted-foreground">Nicio selecție decontată cu șansă estimată.</p>;
  const data = c.buckets.map((b) => ({ name: `${Math.round(b.lo * 100)}–${Math.round(b.hi * 100)}%`, estimat: +(b.pred * 100).toFixed(1), iesit: +(b.hit * 100).toFixed(1), n: b.n }));
  return (
    <>
      <LazyChart className="h-48">{(R) => (
        <R.ResponsiveContainer><R.BarChart data={data} margin={{ left: 0, right: 4, top: 4 }} barGap={2}>
          <R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} />
          <R.XAxis dataKey="name" tick={ax} interval={0} />
          <R.YAxis width={30} domain={[0, 100]} tick={ax} />
          <R.Tooltip {...tip} formatter={(v: number, n: string, it: { payload?: { n?: number } }) => [`${v.toFixed(1).replace('.', ',')}% · ${it?.payload?.n ?? 0} sel.`, n]} />
          <R.Bar isAnimationActive={false} dataKey="estimat" name="estimat" fill="hsl(var(--muted-foreground))" fillOpacity={0.45} radius={[3, 3, 0, 0]} />
          <R.Bar isAnimationActive={false} dataKey="iesit" name="ieșit" radius={[3, 3, 0, 0]}>
            {data.map((d) => <R.Cell key={d.name} fill={d.iesit >= d.estimat ? WIN : LOSS} />)}
          </R.Bar>
        </R.BarChart></R.ResponsiveContainer>
      )}</LazyChart>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {c.n} selecții · estimat {p100(c.pred, 1)}, ieșit {p100(c.hit, 1)}{c.brier != null ? ` · Brier ${c.brier.toFixed(3).replace('.', ',')}` : ''}
        {c.n < 100 ? ' · eșantion mic: diferențele pe interval sunt mai ales noroc.' : ''}
      </p>
    </>
  );
}

function FanChart({ plan }: { plan: Plan }) {
  const data = plan.fan.map((f) => ({ day: f.day, b90: [f.p5, f.p95], b50: [f.p25, f.p75], p50: f.p50 }));
  return (
    <LazyChart className="h-56">{(R) => (
      <R.ResponsiveContainer><R.ComposedChart data={data} margin={{ left: 0, right: 4, top: 4 }}>
        <R.CartesianGrid strokeDasharray="2 6" vertical={false} opacity={0.35} />
        <R.XAxis dataKey="day" tick={ax} tickFormatter={(d: number) => `z${d}`} minTickGap={20} />
        <R.YAxis width={34} tick={ax} domain={['auto', 'auto']} />
        <R.Tooltip {...tip} labelFormatter={(d) => `Ziua ${d}`}
          formatter={(v: number | number[], n: string) => [Array.isArray(v) ? `${v[0].toFixed(0)}–${v[1].toFixed(0)}` : v.toFixed(0), n]} />
        <R.ReferenceLine y={100} stroke="#888" strokeDasharray="4 4" />
        <R.Area isAnimationActive={false} dataKey="b90" name="90% din drumuri" stroke="none" fill="hsl(var(--primary))" fillOpacity={0.12} />
        <R.Area isAnimationActive={false} dataKey="b50" name="50% din drumuri" stroke="none" fill="hsl(var(--primary))" fillOpacity={0.28} />
        <R.Line isAnimationActive={false} dataKey="p50" name="mijloc" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} activeDot={activeDot} />
      </R.ComposedChart></R.ResponsiveContainer>
    )}</LazyChart>
  );
}

function Simulator({ doc }: { doc: BankrollDoc }) {
  const plans = doc.sim.plans;
  const [id, setId] = useState(plans[0]?.plan ?? '');
  const plan = plans.find((p) => p.plan === id) ?? plans[0];
  if (!plan) return null;
  const inp = doc.sim.inputs;
  return (
    <Card className="overflow-hidden p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Simulator de bancă · {doc.sim.horizon_days} de zile</h3>
        <InfoTip text={`${doc.sim.paths.toLocaleString('ro-RO')} de drumuri Monte Carlo, bancă 100. Fiecare drum își trage propria șansă din ce s-a măsurat (cu incertitudine), nu un avantaj presupus.`} />
      </div>
      <p className="mb-3 text-xs text-muted-foreground">Unde poate ajunge o bancă de 100 cu planul de mize ales, dacă biletele continuă cum au ieșit până acum.</p>
      <Segmented size="sm" value={plan.plan} onChange={setId} options={plans.map((p) => ({ value: p.plan, label: p.label }))} />
      <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
        {(['s10', 'long', 'pyr2'] as const).map((k) => (
          <span key={k} className={cn('rounded-full border px-2 py-1', !plan.stakes[k] && 'opacity-50 line-through')}>
            {LABEL[k]}: {k === 'pyr2' ? `${p100(plan.stakes[k], 0)} pe serie` : `${p100(plan.stakes[k], 1)} pe bilet`}
          </span>
        ))}
      </div>
      <div className="mt-3"><FanChart plan={plan} /></div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Tile label="Mijlocul (mediana)" value={plan.p50.toFixed(0)} cls={plan.p50 >= 100 ? 'text-win' : 'text-loss'} sub={`media ${plan.mean.toFixed(0)} (trasă de câștigurile rare)`} />
        <Tile label="90% din drumuri" value={`${plan.p5.toFixed(0)}–${plan.p95.toFixed(0)}`} sub={`jumătate între ${plan.p25.toFixed(0)} și ${plan.p75.toFixed(0)}`} />
        <Tile label="Șansa de profit" value={p100(plan.p_profit)} cls={plan.p_profit >= 0.5 ? 'text-win' : 'text-loss'} sub={`sub 80: ${p100(plan.p_down20)} din drumuri`} />
        <Tile label="Scădere tipică" value={`−${p100(plan.mdd_median)}`} cls="text-loss" sub="cea mai mare cădere, la jumătatea drumurilor" />
      </div>
      <table className="mt-3 w-full text-xs">
        <caption className="sr-only">Datele folosite în simulare</caption>
        <thead className="text-muted-foreground"><tr><th className="py-1 text-left font-medium">Produs</th><th className="text-right font-medium">Șansă</th><th className="text-right font-medium">Plată</th><th className="text-right font-medium">EV</th><th className="text-right font-medium">Pe zi</th></tr></thead>
        <tbody>{(['s10', 'long', 'pyr2'] as const).filter((k) => inp[k]).map((k) => (
          <tr key={k} className="border-t">
            <td className="py-1.5">{LABEL[k]}</td>
            <td className="text-right tabular-nums">{chance(inp[k].p_mean)}</td>
            <td className="text-right tabular-nums">{inp[k].payout >= 100 ? Math.round(inp[k].payout).toLocaleString('ro-RO') : inp[k].payout.toFixed(2).replace('.', ',')}</td>
            <td className={cn('text-right tabular-nums', tone(inp[k].ev))}>{sgn(inp[k].ev, 1)}</td>
            <td className="text-right tabular-nums">{String(inp[k].per_day).replace('.', ',')}</td>
          </tr>
        ))}</tbody>
      </table>
      {Object.keys(plan.ev_pct).length > 0 && (
        <p className="mt-2 text-[11px] text-muted-foreground">
          În medie, pe {doc.sim.horizon_days} de zile: {Object.entries(plan.ev_pct).map(([k, v]) => `${LABEL[k]} ${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1).replace('.', ',')}% din bancă`).join(' · ')}.
        </p>
      )}
      <p className="mt-2 text-[11px] text-muted-foreground">
        Piramida: o serie primește procentul din bancă, mizează {p100(doc.sim.pyramid.stake_fraction)} din banca seriei la fiecare pas și se încasează după {doc.sim.pyramid.suggest_at} pași câștigați sau la prima pierdere.
        Șansa = șansa publicată × raportul ieșit/estimat pe selecții (micșorat spre 0,97), apoi corectată cu biletele decontate. Marja casei e inclusă.
      </p>
    </Card>
  );
}

/** Banca și performanța celor trei produse de la noul început (`api/stats/bankroll.json`). Nu afișează nimic dacă fișierul lipsește. */
export function BankrollPanel() {
  const q = useAsync(() => getJSON<BankrollDoc>('api/stats/bankroll.json'), []);
  const [sel, setSel] = useState<Product['id']>('s10');
  const doc = q.data;
  const prod = useMemo(() => doc?.products.find((p) => p.id === sel) ?? doc?.products[0], [doc, sel]);
  if (q.loading && !doc) return <Skeleton className="h-64 w-full" />;
  if (!doc || !doc.products?.length || !prod) return null;
  const since = doc.since ? `${doc.since.slice(8, 10)}.${doc.since.slice(5, 7)}.${doc.since.slice(0, 4)}` : null;
  return (
    <section className="space-y-3" aria-label="Banca și performanța">
      <div className="grid grid-cols-3 gap-2" role="tablist" aria-label="Produs">
        {doc.products.map((p) => (
          <button key={p.id} type="button" role="tab" aria-selected={p.id === prod.id} onClick={() => setSel(p.id)}
            className={cn('press rounded-2xl border bg-card/50 p-2.5 text-left transition-colors', p.id === prod.id && 'border-primary/60 bg-primary/10')}>
            <span className="block truncate text-[11px] font-semibold text-muted-foreground">{p.label}</span>
            <span className={cn('num block text-lg font-extrabold leading-tight tabular-nums', tone(p.roi))}>{sgn(p.roi, 0)}</span>
            <span className="block text-[11px] text-muted-foreground">{p.bets ? `${p.won}/${p.bets} câștigate` : p.pending ? `${p.pending} în joc` : 'fără bilete'}</span>
          </button>
        ))}
      </div>
      {doc.sim.sample_small && (
        <Notice tone="warn">Eșantion mic{since ? ` (de la ${since})` : ''}: cifrele de mai jos se mișcă mult de la o zi la alta. Judecă după sute de bilete, nu după câteva.</Notice>
      )}
      <Card className="p-4">
        <h3 className="mb-3 text-sm font-semibold">{prod.label}{since ? <span className="font-normal text-muted-foreground"> · de la {since}</span> : null}</h3>
        <ProductSummary p={prod} />
      </Card>
      <Card className="overflow-hidden p-4">
        <h3 className="text-sm font-semibold">Profit pe zile</h3>
        <p className="mb-2 text-xs text-muted-foreground">Unități la miză egală (1 u pe bilet): bara = ziua, linia = cumulat.</p>
        <ProfitChart p={prod} />
      </Card>
      <Card className="overflow-hidden p-4">
        <div className="flex items-center gap-1"><h3 className="text-sm font-semibold">Calibrare selecții</h3><InfoTip text="Pentru fiecare interval de șansă estimată: cât s-a estimat și cât a ieșit. Un model bun are barele apropiate." /></div>
        <p className="mb-2 text-xs text-muted-foreground">Gri = șansa estimată; verde/roșu = rata ieșită (peste / sub estimare).</p>
        <CalibChart c={prod.calibration} />
      </Card>
      <Simulator doc={doc} />
    </section>
  );
}
