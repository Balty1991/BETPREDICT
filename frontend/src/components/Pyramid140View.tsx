import { useAsync } from '@/lib/fetcher';
import { loadPyramid140, loadPyramidMici } from '@/lib/data';
import { odds as fo, pct, lei } from '@/lib/format';
import { Card, Loading, Stat, SectionTitle, Badge, Notice } from '@/components/kit';
import { TicketCard, isLostTicket } from '@/components/TicketCard';
import type { PyramidBacktest } from '@/lib/types';
import { cn } from '@/lib/utils';
import { ActionCard, type PyrAction } from '@/components/PyramidAction';

export type Track = '1.40' | 'mici';
export function useP140(track: Track = '1.40') {
  return useAsync(track === 'mici' ? loadPyramidMici : loadPyramid140, [track]);
}
const COPY: Record<Track, { eyebrow: string; title: string; text: string; lost: string }> = {
  '1.40': { eyebrow: 'Cotă în jur de 1.40', title: 'Piramida 1.40',
    text: 'În paralel cu 2.00. Se alege combinația cu cea mai mare șansă. Câștigul se reinvestește, jumătate din profit se retrage. După o pierdere, reiei de la 100 lei.',
    lost: 'Mâine Piramida 1.40 reîncepe de la treapta 1.' },
  mici: { eyebrow: 'Cotă în jur de 2.00', title: 'Piramida 2.00 Ligi mici',
    text: 'Favoriți din League One, League Two și National League. Reinvestești tot. După 7 câștiguri încasezi tot. După o pierdere reiei de la treapta 1.',
    lost: 'Mâine Piramida Ligi mici reîncepe de la treapta 1.' },
};

type MiciBt = { train: { days: number; win_rate: number; runs: number; net: number; roi_pct: number }; test: { days: number; win_rate: number; avg_odds: number; runs: number; staked: number; returned: number; net: number; roi_pct: number; max_steps: number; cashouts_at_7: number }; note?: string };
function MiciBacktest({ bt }: { bt?: MiciBt | null }) {
  if (!bt?.test) return null;
  const t = bt.test;
  return (
    <Card className="p-4">
      <h2 className="mb-1 font-semibold">Backtest pe istoric (iul. 2024 → azi, 100 lei/serie)</h2>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Pași câștigați" value={pct(t.win_rate, 0)} sub={`${t.days} zile · cotă medie ${fo(t.avg_odds)}`} />
        <Stat label="Serii" value={t.runs} sub={`${t.cashouts_at_7} încasări la pasul 7`} />
        <Stat label="Investit / încasat" value={`${lei(t.staked)}`} sub={`încasat ${lei(t.returned)}`} />
        <Stat label="Rezultat net" value={lei(t.net)} tone={t.net >= 0 ? 'win' : 'loss'} sub={`antrenare 2021–24: ${lei(bt.train.net)}`} />
      </div>
      {bt.note && <p className="mt-2 text-[11px] text-muted-foreground">{bt.note}</p>}
    </Card>
  );
}

export function BacktestCard({ bt }: { bt?: PyramidBacktest | null }) {
  if (!bt) return null;
  const mx = Math.max(1, ...bt.distribution.map((d) => d.runs));
  return (
    <Card className="p-4">
      <h2 className="mb-1 font-semibold">Backtest 1.40 pe istoric</h2>
      <p className="mb-3 text-xs text-muted-foreground">{bt.days} zile de joc ({bt.from} → {bt.to}), football-data. Selecții cu ≥80% șansă (piața fără marjă), 1–4 pe bilet, cota ~1.40, cea mai mare șansă comună.</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Pași câștigați" value={pct(bt.win_rate ?? 0, 1)} sub={`cotă medie ${fo(bt.avg_odds ?? 0)} · ${bt.avg_legs} sel.`} />
        <Stat label="Pași / serie (medie)" value={bt.avg_steps ?? '—'} sub={`mediană ${bt.median_steps ?? '—'}`} />
        <Stat label="Cea mai lungă serie" value={bt.max_steps ?? '—'} sub={`${bt.runs} serii`} />
        <Stat label="Ajunge la pasul 5" value={pct(bt.reach_probability['5'] ?? 0, 1)} sub={`pasul 10: ${pct(bt.reach_probability['10'] ?? 0, 1)} · 17: ${pct(bt.reach_probability['17'] ?? 0, 1)}`} />
      </div>
      <div className="mt-3 space-y-1" aria-label="Distribuția seriilor">
        {bt.distribution.map((d) => (
          <div key={String(d.steps)} className="flex items-center gap-2 text-xs">
            <span className="num w-10 text-right text-muted-foreground">{d.steps} p.</span>
            <span className="h-3 rounded bg-primary/70" style={{ width: `${(d.runs / mx) * 75}%` }} />
            <span className="num text-muted-foreground">{d.runs}</span>
          </div>
        ))}
      </div>
      {bt.bank_sim && <p className="mt-2 text-[11px] text-muted-foreground">Simulare 100 lei/serie cu retragere 50% din profit: investit {lei(bt.bank_sim.restarts_cost)}, retras {lei(bt.bank_sim.withdrawn)}, net {lei(bt.bank_sim.net)}. Marja casei se adună la fiecare pas.</p>}
    </Card>
  );
}

function StepBars({ current, p }: { current: number; p: number }) {
  const base = Math.min(0.97, Math.max(0.05, p));
  const bars = [1, 2, 3, 4, 5, 6, 7, 8].map((k) => ({ k, p: Math.pow(base, k) }));
  return (
    <>
      <ol className="mt-5 grid grid-cols-8 items-end gap-1.5" aria-label="Treptele piramidei">
        {bars.map(({ k, p: chance }) => {
          const on = k === current, done = k < current;
          return (
            <li key={k} className="flex flex-col items-center gap-1">
              <span className="num text-[10px] text-muted-foreground">{pct(chance)}</span>
              <span className={cn('pyr-step w-full rounded-t-lg', done ? 'pyr-done' : on ? 'pyr-on' : '')} style={{ height: `${14 + k * 9}px` }} />
              <span className={cn('num text-[11px] font-bold', on ? 'text-primary' : 'text-muted-foreground')}>{k}</span>
            </li>
          );
        })}
      </ol>
      <p className="mt-1 text-center text-[11px] text-muted-foreground">Treapta curentă: <b className="text-foreground">{current}</b> · deasupra: șansa de a ajunge acolo</p>
    </>
  );
}

export default function Pyramid140View({ track = '1.40' }: { track?: Track }) {
  const api = useP140(track);
  const cp = COPY[track];
  if (api.loading) return <Loading />;
  const d = api.data;
  if (!d) return <Notice>{cp.title} pornește la următoarea rulare a robotului.</Notice>;
  const main = d.today?.status === 'pick' ? d.today.main : null;
  const run = d.run;
  const restart = !run || run.status === 'lost' || run.status === 'completed';
  const step = restart ? 1 : (run!.step ?? 0) + 1;
  const bank = restart ? (d.rules as unknown as { start_bank?: number }).start_bank ?? 100 : run!.bank ?? 100;
  return (
    <div className="space-y-5">
      <section className="page-hero">
        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0">
            <div className="eyebrow">{cp.eyebrow}</div>
            <h1 className="mt-1 text-[22px] leading-tight">{cp.title}</h1>
          </div>
          <div className="slip-odds shrink-0 rounded-2xl px-3 py-2 text-center">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-primary-foreground/75">Azi</div>
            <div className="num text-[28px] font-extrabold leading-none text-primary-foreground">{main ? fo(main.total_odds) : 'Pauză'}</div>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <div className="pyr-tile pyr-a rounded-xl bg-[hsl(var(--elevated))] px-1.5 py-2"><div className="text-[10px] font-bold uppercase text-muted-foreground">Treapta</div><div className="num mt-0.5 whitespace-nowrap text-base font-extrabold">{step}</div></div>
          <div className="pyr-tile pyr-b rounded-xl bg-[hsl(var(--elevated))] px-1.5 py-2"><div className="text-[10px] font-bold uppercase text-muted-foreground">Miza</div><div className="num mt-0.5 whitespace-nowrap text-base font-extrabold">{main ? lei(bank) : '—'}</div></div>
          <div className="pyr-tile pyr-c rounded-xl bg-[hsl(var(--elevated))] px-1.5 py-2"><div className="text-[10px] font-bold uppercase text-muted-foreground">Dacă intră</div><div className={cn('num mt-0.5 whitespace-nowrap text-base font-extrabold', main ? 'text-win' : 'text-muted-foreground')}>{main ? lei(bank * main.total_odds) : 'pauză'}</div></div>
        </div>
        <StepBars current={step} p={main?.p_ticket ?? (track === 'mici' ? (d.backtest as MiciBt | undefined)?.test?.win_rate : (d.backtest as PyramidBacktest | undefined)?.win_rate) ?? (track === '1.40' ? 0.75 : 0.5)} />
      </section>
      <ActionCard a={(d as unknown as { action?: PyrAction }).action} />
      <section>
        <SectionTitle title="Biletul de azi" />
        {!main ? <Notice tone="warn">{d.today?.reason ?? 'Azi fără bilet.'}</Notice>
          : isLostTicket(main) ? <Notice>Biletul de azi a pierdut. {cp.lost}</Notice> : <TicketCard t={main} />}
      </section>
      {track === 'mici' ? <MiciBacktest bt={d.backtest as unknown as MiciBt} /> : <BacktestCard bt={d.backtest} />}
      <GridCard grid={(d as unknown as { grid?: PyramidGrid }).grid} />
      <Card className="overflow-hidden">
        <h2 className="p-3 font-semibold">Serii (run-uri)</h2>
        <table className="w-full text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">#</th><th className="text-left">Perioadă</th><th className="text-right">Pași</th><th className="px-3 text-right">Retras</th></tr></thead>
          <tbody>{(d.runs ?? []).map((r) => (
            <tr key={r.id} className="border-t"><td className="px-3 py-1.5">{r.id}</td><td className="text-xs text-muted-foreground">{r.start_date} → {r.end_date ?? 'acum'}</td><td className="text-right">{r.steps}</td><td className="px-3 text-right">{lei(r.withdrawn ?? 0)}</td></tr>
          ))}</tbody></table>
        {!(d.runs ?? []).length && <p className="p-3 text-xs text-muted-foreground">Prima serie începe cu primul bilet.</p>}
      </Card>
    </div>
  );
}

export function Pyramid140Stats({ track = '1.40' }: { track?: Track }) {
  const api = useP140(track);
  const d = api.data;
  if (api.loading) return <Loading />;
  if (!d) return <Notice>Încă nu există date pentru {COPY[track].title}.</Notice>;
  const h = d.history ?? [];
  const won = h.filter((x) => x.result === 'won').length, lost = h.filter((x) => x.result === 'lost').length;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
        <Stat label="Zile urmărite" value={h.length} sub={`${h.filter((x) => x.status === 'pick').length} cu bilet`} />
        <Stat label="Pași" value={`${won} / ${lost}`} sub="câștigați / pierduți" />
        <Stat label="Serii" value={(d.runs ?? []).length} sub={`cel mai bun pas: ${Math.max(0, ...(d.runs ?? []).map((r) => r.steps ?? 0))}`} />
        <Stat label="Total retras" value={lei((d.runs ?? []).reduce((s, r) => s + (r.withdrawn ?? 0), 0))} />
      </div>
      <Card className="overflow-hidden"><table className="w-full text-sm"><tbody>{h.slice(0, 60).map((r) => (
        <tr key={r.date} className="border-t"><td className="px-3 py-1.5 text-xs">{r.date}</td><td className="text-right">{r.odds ? fo(r.odds) : '—'}</td><td className="text-right">{r.p != null ? pct(r.p) : ''}</td>
          <td className="px-3 text-right"><Badge tone={r.result === 'won' ? 'win' : r.result === 'lost' ? 'loss' : 'muted'}>{r.status === 'no_bet' ? 'pauză' : r.result === 'won' ? 'câștigat' : r.result === 'lost' ? 'pierdut' : 'în curs'}</Badge></td></tr>
      ))}</tbody></table></Card>
      {track === 'mici' ? <MiciBacktest bt={d.backtest as unknown as MiciBt} /> : <BacktestCard bt={d.backtest} />}
    </div>
  );
}

type GridRow = { markets: string; real_prices: boolean; leagues: string; drift_filter: boolean; min_leg_p: number; max_legs: number; withdraw: number; label?: string;
  test: { days: number; win_rate: number | null; max_step: number; reach: Record<string, number>; roi_pct: number; flat_roi_pct: number | null; avg_odds: number | null } };
export type PyramidGrid = { matches: number; split: string; tested: number; both_positive: number; baseline?: GridRow | null; top: GridRow[]; verdict?: string };
const MK: Record<string, string> = { '1x2_fav': 'Favoriți 1X2', ou25_real: 'Peste/Sub 2.5', real_mix: '1X2 + O/U 2.5', sansa_dubla: 'Șansă dublă', 'peste_0.5_1.5': 'Peste 0.5/1.5', 'sub_3.5_4.5': 'Sub 3.5/4.5', mix_tot: 'Mix toate' };
const LG: Record<string, string> = { toate: 'toate ligile', top: 'ligi top', liga2: 'ligi 2', altele: 'ligi mici' };

export function GridCard({ grid }: { grid?: PyramidGrid | null }) {
  if (!grid) return null;
  const rows = [...(grid.baseline ? [{ ...grid.baseline, label: 'Regula live' }] : []), ...grid.top];
  return (
    <Card className="overflow-hidden p-0">
      <div className="p-3"><h2 className="font-semibold">Variante testate ({grid.tested})</h2>
        <p className="text-xs text-muted-foreground">{grid.matches.toLocaleString('ro-RO')} meciuri; variantele alese pe 2021–2024, rezultatele de mai jos pe perioada de test ({grid.split} → azi). * = cote modelate, nu reale.</p></div>
      <div className="overflow-x-auto"><table className="w-full whitespace-nowrap text-xs">
        <thead className="text-muted-foreground"><tr><th className="px-3 text-left">Variantă</th><th className="text-right">Pași câșt.</th><th className="text-right">Max</th><th className="text-right">≥3 / 5 / 7 / 10 / 15</th><th className="text-right">ROI fix</th><th className="px-3 text-right">ROI piramidă</th></tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i} className={cn('border-t', r.label && 'bg-[hsl(var(--elevated))]')}>
            <td className="px-3 py-1.5">{r.label ? <b>{r.label}: </b> : null}{MK[r.markets] ?? r.markets}{r.real_prices ? '' : '*'} · {LG[r.leagues] ?? r.leagues} · ≥{Math.round(r.min_leg_p * 100)}% · max {r.max_legs} · {r.drift_filter ? 'fără cote în creștere' : 'orice cotă'} · retras {Math.round(r.withdraw * 100)}%</td>
            <td className="num text-right">{pct(r.test.win_rate ?? 0, 0)}</td><td className="num text-right">{r.test.max_step}</td>
            <td className="num text-right">{['3', '5', '7', '10', '15'].map((k) => pct(r.test.reach[k] ?? 0, 0)).join(' / ')}</td>
            <td className={cn('num text-right', (r.test.flat_roi_pct ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{(r.test.flat_roi_pct ?? 0) > 0 ? '+' : ''}{r.test.flat_roi_pct}%</td>
            <td className={cn('num px-3 text-right', r.test.roi_pct >= 0 ? 'text-win' : 'text-loss')}>{r.test.roi_pct > 0 ? '+' : ''}{r.test.roi_pct}%</td></tr>
        ))}</tbody></table></div>
      {grid.verdict && <p className="p-3 text-xs text-muted-foreground">{grid.verdict}</p>}
    </Card>
  );
}
