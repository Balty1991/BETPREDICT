import { Brain, CalendarClock, Cpu, FlaskConical, Gauge, History, SlidersHorizontal } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { loadRobot } from '@/lib/data';
import { marketTitle } from '@/lib/markets';
import { roDateTime } from '@/lib/format';
import type { CalibrationMarket, Learning, RobotDoc, BtMetrics } from '@/lib/types';
import { Card, InfoTip, Badge } from './kit';
import { cn } from '@/lib/utils';

const f3 = (x?: number | null) => (x == null ? '—' : x.toFixed(3));
const fpct = (x?: number | null, d = 1) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`);
const sgn = (x?: number | null, d = 1) => (x == null ? '—' : `${x > 0 ? '+' : ''}${(x * 100).toFixed(d)}%`);

const LOG_LABEL: Record<string, string> = {
  backtest_v2: 'Backtest v2', segment: 'Segment ligă × piață', champion_cycle: 'Campion vs. challenger', calibration: 'Calibrare', threshold: 'Prag EV',
  blend: 'Ponderi', exclude_market: 'Piață exclusă', include_market: 'Piață reactivată', league_penalty: 'Penalizare ligă',
  blend_weights: 'Ponderi', bsd_weight: 'Pondere BSD', ticket_strategy: 'Strategie bilete', ticket_shrink: 'Bilete: model vs piață',
  leg_bias: 'Bilete: corecție selecții', leg_block: 'Bilete: tip selecție exclus', leg_unblock: 'Bilete: tip selecție readmis',
  variant_weights: 'Bilete: ponderi variante', tier_min_p: 'Bilete: prag pe nivel',
};

function Better({ a, b }: { a?: BtMetrics | null; b?: BtMetrics | null }) {
  if (!a || !b) return <span className="text-muted-foreground">—</span>;
  const d = b.logloss - a.logloss;
  return <span className={cn('font-semibold tabular-nums', d < 0 ? 'text-win' : d > 0 ? 'text-loss' : 'text-muted-foreground')}>{d > 0 ? '+' : ''}{d.toFixed(3)}</span>;
}

function Section({ icon: Icon, title, tip, children }: { icon: typeof Brain; title: string; tip?: string; children: React.ReactNode }) {
  return (
    <Card className="overflow-hidden">
      <h2 className="flex items-center gap-2 px-4 pb-2 pt-3.5 text-[15px] font-bold"><Icon className="h-4 w-4 text-primary" aria-hidden />{title}{tip && <InfoTip text={tip} label={`Despre: ${title}`} />}</h2>
      {children}
    </Card>
  );
}

/** Secțiunea „Robotul”: modelul activ, backtest, calibrare, praguri, jurnal, următoarea reantrenare. */
export function RobotPanel({ learning, calibration }: { learning?: Learning | null; calibration?: CalibrationMarket[] | null }) {
  const doc = useAsync(loadRobot, []);
  const d: RobotDoc | null = doc.data ?? null;
  const label = (d?.model_label ?? 'robot-v2').replace('robot-', 'Robot ');
  const m = d?.model ?? learning?.model;
  const bt = d?.backtest;
  const log = d?.log ?? learning?.log ?? [];
  const liveCal = (calibration ?? []).filter((c) => c.n > 0);
  const next = d?.schedule?.next_retrain_utc;

  return (
    <div className="space-y-4">
      <div className="hero relative overflow-hidden rounded-3xl border p-5">
        <div className="eyebrow">Modelul activ</div>
        <div className="mt-1 flex flex-wrap items-baseline gap-2">
          <span className="font-display text-3xl font-extrabold tracking-tight">{label}</span>
          <Badge tone="win">activ</Badge>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{d?.engine ?? 'LightGBM + Dixon-Coles (stacking), calibrat, tras spre piață'}</p>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div><dt className="text-[11px] text-muted-foreground">Meciuri în istoric</dt><dd className="num text-lg font-bold">{(bt?.history_matches ?? m?.matches)?.toLocaleString('ro-RO') ?? '—'}</dd></div>
          <div><dt className="text-[11px] text-muted-foreground">Antrenat</dt><dd className="text-lg font-bold">{m?.trained_at ? roDateTime(m.trained_at).split(',')[0] : bt?.generated_at ? roDateTime(bt.generated_at).split(',')[0] : '—'}</dd></div>
          <div><dt className="text-[11px] text-muted-foreground">Orizont predicții</dt><dd className="text-lg font-bold">{d?.days_ahead != null ? `azi + ${d.days_ahead} zile` : '—'}</dd></div>
          <div><dt className="flex items-center text-[11px] text-muted-foreground"><CalendarClock className="mr-1 h-3 w-3" aria-hidden />Următoarea reantrenare</dt><dd className="text-lg font-bold">{next ? roDateTime(next) : 'luni dimineața'}</dd></div>
        </dl>
        {doc.loading && <p className="mt-3 text-xs text-muted-foreground">Se încarcă raportul…</p>}
      </div>

      {bt?.markets?.length ? (
        <Section icon={FlaskConical} title="Backtest walk-forward" tip="Testat pe meciuri pe care modelul nu le-a văzut. LogLoss și Brier: mai mic = mai bine. Comparăm v2 cu v1 și cu piața (casele de pariuri). ROI: dacă am fi jucat 1u pe fiecare recomandare.">
          <p className="px-4 pb-2 text-xs text-muted-foreground">Evaluare din {bt.eval_from ?? '—'} · {bt.odds_matches?.toLocaleString('ro-RO') ?? '—'} meciuri cu cote pre-meci (din {bt.odds_from ?? '—'})</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr className="whitespace-nowrap border-y bg-[hsl(var(--elevated))]"><th className="px-4 py-2 text-left font-semibold">Piață</th><th className="px-2 text-right font-semibold">LogLoss v2</th><th className="px-2 text-right font-semibold">vs v1</th><th className="px-2 text-right font-semibold">Brier</th><th className="px-2 text-right font-semibold">v2+piață vs piață</th><th className="px-4 text-right font-semibold">ROI recomandări</th></tr>
              </thead>
              <tbody className="divide-y">
                {bt.markets.map((r) => (
                  <tr key={r.key}>
                    <td className="px-4 py-2 font-medium">{r.title}</td>
                    <td className="px-2 text-right num">{f3(r.v2?.logloss)}</td>
                    <td className="px-2 text-right"><Better a={r.v1} b={r.v2} /></td>
                    <td className="px-2 text-right num">{f3(r.v2?.brier)}</td>
                    <td className="px-2 text-right"><Better a={r.market} b={r.v2_market} /></td>
                    <td className="px-4 text-right num">{r.roi_rec ? <><span className={cn('font-semibold', (r.roi_rec.roi ?? 0) > 0 ? 'text-win' : 'text-loss')}>{sgn(r.roi_rec.roi)}</span><span className="text-[11px] text-muted-foreground"> · {r.roi_rec.n}</span></> : <span className="text-muted-foreground">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="px-4 py-2.5 text-[11px] text-muted-foreground">Verde = v2 mai precis. ROI-urile au eșantioane mici — de aceea Robotul cere valoare minimă pe piață și mize prudente.</p>
        </Section>
      ) : null}

      {bt?.markets?.length ? (
        <Section icon={Gauge} title="Calibrare" tip="ECE = diferența medie dintre șansa afișată și frecvența reală. Sub 2% înseamnă că „70%” chiar câștigă ~70% din cazuri.">
          <ul className="grid gap-2 px-4 pb-4 sm:grid-cols-2">
            {bt.markets.map((r) => {
              const ece = r.v2_market?.ece ?? r.v2?.ece;
              const live = liveCal.find((c) => c.key === r.key);
              const w = Math.min(100, ((ece ?? 0) / 0.05) * 100);
              return (
                <li key={r.key} className="rounded-xl bg-[hsl(var(--elevated))] px-3 py-2">
                  <div className="flex items-center justify-between text-sm"><span className="font-medium">{r.title}</span><span className="num font-semibold">{fpct(ece)}</span></div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted"><div className={cn('h-full rounded-full', (ece ?? 1) < 0.02 ? 'bg-[hsl(var(--win))]' : 'bg-[hsl(var(--warn))]')} style={{ width: `${w}%` }} /></div>
                  <div className="mt-1 text-[11px] text-muted-foreground">{live ? `Live: ECE ${fpct(live.ece)} pe ${live.n} rezultate` : 'Live: se acumulează rezultate'}</div>
                </li>
              );
            })}
          </ul>
        </Section>
      ) : null}

      {d?.thresholds?.length ? (
        <Section icon={SlidersHorizontal} title="Praguri pe piață" tip="Valoarea minimă (EV) cerută ca o selecție să fie jucabilă. Pornesc din backtest și se ajustează săptămânal din rezultatele reale.">
          <ul className="divide-y text-sm">
            {d.thresholds.map((t) => (
              <li key={t.key} className="flex items-center gap-2 px-4 py-2">
                <span className="min-w-0 flex-1 truncate">{marketTitle(t.key)}</span>
                <Badge tone={t.source === 'backtest' ? 'muted' : 'primary'}>{t.source === 'backtest' ? 'backtest' : 'învățat'}</Badge>
                <span className="w-20 text-right num font-semibold">EV ≥ {sgn(t.min_ev, 0)}</span>
              </li>
            ))}
          </ul>
          {d.excluded_markets?.length ? <p className="px-4 py-2 text-xs text-muted-foreground">Excluse din bilete: {d.excluded_markets.map(marketTitle).join(', ')}</p> : null}
        </Section>
      ) : null}

      <Section icon={History} title="Jurnal de învățare">
        {log.length ? (
          <ol className="relative mx-4 mb-4 border-l pl-4">
            {log.slice(0, 30).map((l, i) => (
              <li key={i} className="relative pb-3 last:pb-0">
                <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-primary ring-4 ring-[hsl(var(--card))]" aria-hidden />
                <div className="flex flex-wrap items-center gap-2 text-sm"><b>{LOG_LABEL[l.change_type ?? ''] ?? l.change_type}</b>{l.market && <span className="text-muted-foreground">{marketTitle(l.market)}</span>}<span className="ml-auto text-xs text-muted-foreground">{l.run_at ? roDateTime(l.run_at) : ''}</span></div>
                {(l.before != null || l.after != null) && <div className="text-xs text-muted-foreground">{String(l.before ?? '')} → {String(l.after ?? '')}</div>}
                {(l as { why?: string | null }).why ? <div className="text-xs">{(l as { why?: string | null }).why}</div> : null}
              </li>
            ))}
          </ol>
        ) : <p className="px-4 pb-4 text-sm text-muted-foreground">Prima reantrenare din rezultate reale are loc {next ? roDateTime(next) : 'luni'}; atunci apar aici ajustările.</p>}
      </Section>

      <Card className="flex items-start gap-3 p-4 text-sm">
        <Cpu className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
        <p className="text-muted-foreground">Program: predicții noi zilnic la {d?.schedule?.daily ?? '00:15 UTC'} (03:15 ora României), cote actualizate {d?.schedule?.refresh ?? 'din oră în oră'}, reantrenare {d?.schedule?.retrain ?? 'lunea'} (06:45 ora României). Statisticile Robotului 3.0 se numără din {d?.stats_since ?? '9 oct. 2026'}.</p>
      </Card>
    </div>
  );
}
