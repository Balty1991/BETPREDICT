import { FlaskConical } from 'lucide-react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { Card, Loading, Empty, Badge, Notice } from '@/components/kit';

/* eslint-disable @typescript-eslint/no-explicit-any */
type M = { n: number; hit_rate: number; roi: number; roi_se?: number | null; max_drawdown_u: number; longest_losing_streak: number; profit_u: number };
type S = { name: string; market_set: string; band: number[]; tier: number; system: number; avg_legs: number; train: M; test: M };
type Lab = { matches: number; configs_tested: number; configs_eligible: number; test_positive: number; train_positive: number; both_positive: number;
  both_positive_expected_by_chance: number; both_positive_significant_test_t2: number; split: string; overround: number;
  tiers: Record<string, { configs: number; median_test_roi: number; share_test_positive: number }>; super: S[]; robust: S[];
  live?: Record<string, { n: number; won: number; lost: number; pending: number; staked_u: number; profit_u: number }> };

const P = (x: number) => `${x >= 0 ? '+' : ''}${(x * 100).toFixed(0)}%`;
const SETS: Record<string, string> = { sigure_mix: 'Mix sigure', goluri_peste: 'Goluri peste', goluri_sub: 'Goluri sub', sansa_dubla: 'Șansă dublă', favoriti_1x2: 'Favoriți 1X2', goluri_mix: 'Goluri mix' };
const title = (s: S) => `${SETS[s.market_set] ?? s.market_set} ${s.band[0].toFixed(2)}–${s.band[1].toFixed(2)} · ~${s.tier} · ${s.system ? `sistem N−${s.system}/N` : 'acumulator'}`;

function StratCard({ s, live }: { s: S; live?: { n: number; won: number; lost: number; pending: number; staked_u: number; profit_u: number } }) {
  const t = s.test;
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-start justify-between gap-2"><h3 className="text-sm font-semibold leading-snug">{title(s)}</h3><Badge tone={t.roi > 0 ? 'win' : 'loss'}>{P(t.roi)}</Badge></div>
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div><div className="text-muted-foreground">Lovit (test)</div><div className="text-base font-semibold">{(t.hit_rate * 100).toFixed(1)}%</div></div>
        <div><div className="text-muted-foreground">Bilete test</div><div className="text-base font-semibold">{t.n}</div></div>
        <div><div className="text-muted-foreground">Selecții</div><div className="text-base font-semibold">~{s.avg_legs}</div></div>
        <div><div className="text-muted-foreground">Drawdown</div><div className="font-semibold">{t.max_drawdown_u}u</div></div>
        <div><div className="text-muted-foreground">Șir pierderi</div><div className="font-semibold">{t.longest_losing_streak}</div></div>
        <div><div className="text-muted-foreground">ROI antrenare</div><div className="font-semibold">{P(s.train.roi)}</div></div>
      </div>
      {t.roi_se ? <p className="mt-2 text-xs text-muted-foreground">Incertitudine ROI test: ± {(t.roi_se * 100).toFixed(0)}% — câteva bilete câștigate fac tot rezultatul.</p> : null}
      {live ? <p className="mt-1 text-xs">Live: {live.n} bilete · {live.won} câștigate · {live.lost} pierdute · profit {live.profit_u.toFixed(2)}u</p> : null}
    </Card>
  );
}

export function LabPanel() {
  const lab = useAsync(() => getJSON<Lab>('api/lab/results.json'), []);
  if (lab.loading) return <Loading />;
  const d = lab.data;
  if (!d) return <Empty title="Laboratorul nu are încă rezultate" />;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold"><FlaskConical className="h-4 w-4" />Laboratorul de strategii</h2>
        <p className="text-xs text-muted-foreground">{d.configs_tested.toLocaleString('ro-RO')} strategii de bilete lungi testate pe {d.matches.toLocaleString('ro-RO')} meciuri ({d.split}). Selecție doar cu informații dinainte de meci, cote de închidere cu marjă tip Superbet ({((d.overround - 1) * 100).toFixed(0)}%).</p>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div><div className="text-muted-foreground">Pozitive în test</div><div className="text-base font-semibold">{d.test_positive}/{d.configs_eligible}</div></div>
          <div><div className="text-muted-foreground">Pozitive în ambele</div><div className="text-base font-semibold">{d.both_positive}</div></div>
          <div><div className="text-muted-foreground">Așteptat din noroc</div><div className="text-base font-semibold">{d.both_positive_expected_by_chance}</div></div>
        </div>
      </Card>
      <Notice tone="warn">Concluzie onestă: biletele lungi pierd în medie (ROI median în test între {P(Math.max(...Object.values(d.tiers).map((x) => x.median_test_roi)))} și {P(Math.min(...Object.values(d.tiers).map((x) => x.median_test_roi)))}). Strategiile „pozitive” nu sunt mai multe decât ar da întâmplarea și niciuna nu e semnificativă statistic. Super biletele sunt jucate cu risc asumat, miză fixă mică.</Notice>
      <Card className="overflow-hidden"><h2 className="p-3 text-sm font-semibold">Pe țintă de cotă (doar perioada de test)</h2>
        <table className="w-full text-sm"><thead className="text-xs text-muted-foreground"><tr><th className="px-3 py-1 text-left">Cotă</th><th className="text-right">Strategii</th><th className="text-right">ROI median</th><th className="px-3 text-right">Pozitive</th></tr></thead>
          <tbody>{Object.entries(d.tiers).map(([k, v]) => <tr key={k} className="border-t"><td className="px-3 py-1.5">~{k}</td><td className="text-right">{v.configs}</td><td className="text-right">{P(v.median_test_roi)}</td><td className="px-3 text-right">{(v.share_test_positive * 100).toFixed(0)}%</td></tr>)}</tbody></table>
      </Card>
      <h2 className="text-sm font-semibold">Strategiile folosite la Super bilete</h2>
      {d.super.map((s) => <StratCard key={s.name} s={s} live={d.live?.[s.name] as any} />)}
    </div>
  );
}
