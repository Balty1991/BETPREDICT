import { useState } from 'react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { Badge } from '@/components/kit';

type Stil = { key: string; label: string; family: string; n: number; win_rate: number; avg_odds: number; roi: number | null; lift: number | null; status: string };
type Robot = { market: string; n: number; win_rate: number; avg_odds: number; roi: number | null; in_mix: boolean };
type Boost = { name: string; n: number; win_rate: number; avg_odds: number; roi: number | null };
type Doc = { generated_at: string; stil: Stil[]; robot: Robot[]; boosts: Boost[]; timing?: string | null; note: string };

const pct = (x: number | null | undefined) => (x == null ? '—' : `${x > 0 ? '+' : ''}${(x * 100).toFixed(1)}%`);
const tone = (x: number | null | undefined) => ((x ?? 0) > 0 ? 'text-win' : (x ?? 0) < 0 ? 'text-loss' : '');
const ST: Record<string, 'win' | 'loss' | 'muted' | 'primary'> = { 'dovedită': 'win', 'scoasă din bilete': 'loss', 'în bilete': 'primary', 'puține rezultate': 'muted' };
const ROBOT: Record<string, string> = { '1x2': '1X2', btts: 'Ambele marchează', draw_no_bet: 'Egal = pariu returnat', over_under: 'Peste / Sub', double_chance: 'Șansă dublă' };

function Row({ name, n, win, odds, roi, badge }: { name: string; n: number; win: number; odds: number; roi: number | null; badge?: [string, 'win' | 'loss' | 'muted' | 'primary'] }) {
  return (
    <li className="flex items-center gap-2 border-b border-border/50 py-1.5 text-xs last:border-0">
      <div className="min-w-0 flex-1">
        <div className="break-words font-semibold">{name}</div>
        <div className="text-[11px] text-muted-foreground">{n} rezultate · intră {(win * 100).toFixed(0)}% · cota {odds.toFixed(2)}</div>
      </div>
      {badge && <Badge tone={badge[1]}>{badge[0]}</Badge>}
      <span className={`num w-14 shrink-0 text-right font-extrabold ${tone(roi)}`}>{pct(roi)}</span>
    </li>
  );
}

/** Statistici › Audit piețe: ROI pe cotele reale Superbet și ce face Robotul cu fiecare piață (refăcut la fiecare rulare). */
export function MarketAudit() {
  const q = useAsync(() => getJSON<Doc>('api/stats/audit.json'), []);
  const [all, setAll] = useState(false);
  const d = q.data;
  if (q.loading) return <div className="text-sm text-muted-foreground">Se încarcă…</div>;
  if (!d) return <div className="text-sm text-muted-foreground">Auditul apare după următoarea rulare a Robotului.</div>;
  const stil = d.stil.filter((s) => all || s.n >= 30);
  return (
    <div className="space-y-4">
      <p className="text-[11px] text-muted-foreground">{d.note}</p>
      {d.boosts.length > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-bold">Cote mărite</h3>
          <ul>{d.boosts.map((b) => <Row key={b.name} name={b.name} n={b.n} win={b.win_rate} odds={b.avg_odds} roi={b.roi} />)}</ul>
        </section>
      )}
      <section>
        <h3 className="mb-1 text-sm font-bold">Piețe Stil (cote reale Superbet)</h3>
        <ul>{stil.map((s) => <Row key={s.key} name={s.label} n={s.n} win={s.win_rate} odds={s.avg_odds} roi={s.roi} badge={[s.status, ST[s.status] ?? 'muted']} />)}</ul>
        <button type="button" className="press mt-1 text-xs font-semibold text-primary" onClick={() => setAll((v) => !v)}>
          {all ? 'Doar piețele cu 30+ rezultate' : 'Arată și piețele cu puține rezultate'}
        </button>
      </section>
      {d.robot.length > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-bold">Robotul principal în biletele mixte</h3>
          <ul>{d.robot.map((r) => <Row key={r.market} name={ROBOT[r.market] ?? r.market} n={r.n} win={r.win_rate} odds={r.avg_odds} roi={r.roi}
            badge={r.in_mix ? ['intră', 'primary'] : ['scoasă', 'loss']} />)}</ul>
        </section>
      )}
      {d.timing && <p className="text-[11px] text-muted-foreground"><b>Când joci:</b> {d.timing}</p>}
    </div>
  );
}
