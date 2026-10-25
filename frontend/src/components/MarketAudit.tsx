import { useState } from 'react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { Badge } from '@/components/kit';

type Stil = { key: string; label: string; family: string; n: number; win_rate: number; avg_odds: number; roi: number | null; lift: number | null; status: string };
type Robot = { market: string; n: number; win_rate: number; avg_odds: number; roi: number | null; in_mix: boolean };
type Boost = { name: string; n: number; win_rate: number; avg_odds: number; roi: number | null };
type Split = { name: string; n: number; won: number; win_rate: number; avg_odds: number; roi: number | null; avg_legs: number; leg_win_rate: number | null; boost_win_rate: number | null };
type Doc = { generated_at: string; stil: Stil[]; robot: Robot[]; boosts: Boost[]; boost_split?: Split[]; timing?: string | null; note: string };

const pct = (x: number | null | undefined) => (x == null ? '—' : `${x > 0 ? '+' : ''}${(x * 100).toFixed(1)}%`);
const tone = (x: number | null | undefined) => ((x ?? 0) > 0 ? 'text-win' : (x ?? 0) < 0 ? 'text-loss' : '');
const ST: Record<string, 'win' | 'loss' | 'muted' | 'primary'> = { 'dovedită': 'win', 'scoasă din bilete': 'loss', 'în bilete': 'primary', 'puține rezultate': 'muted' };
// regula de revenire (supersocial.LIFT_DROP = 0.97): piața intră înapoi singură când raportul câștigate reale ÷ promise de cotă
// (micșorat spre 0.95 cu 20 de pseudo-rezultate) urcă la ≥ 0.97 — adică intră cam ≥ 97% din cât spune cota
const reopen = (s: Stil) => `Revine automat dacă intră ≥ ${Math.min(99, Math.round((0.97 / Math.max(1.01, s.avg_odds)) * 100))}% (acum ${(s.win_rate * 100).toFixed(0)}%${s.lift ? `, raport ${s.lift.toFixed(2)} din 0.97 necesar` : ''}).`;
const ROBOT: Record<string, string> = { '1x2': '1X2', btts: 'Ambele marchează', draw_no_bet: 'Egal = pariu returnat', over_under: 'Peste / Sub', double_chance: 'Șansă dublă' };

function Row({ name, n, win, odds, roi, badge, note }: { name: string; n: number; win: number; odds: number; roi: number | null; badge?: [string, 'win' | 'loss' | 'muted' | 'primary']; note?: string }) {
  return (
    <li className="flex items-center gap-2 border-b border-border/50 py-1.5 text-xs last:border-0">
      <div className="min-w-0 flex-1">
        <div className="break-words font-semibold">{name}</div>
        <div className="text-[11px] text-muted-foreground">{n} rezultate · intră {(win * 100).toFixed(0)}% · cota {odds.toFixed(2)}</div>
        {note && <div className="text-[11px] font-semibold text-warn">{note}</div>}
      </div>
      {badge && <Badge tone={badge[1]}>{badge[0]}</Badge>}
      <span className={`num w-14 shrink-0 text-right font-extrabold ${tone(roi)}`}>{pct(roi)}</span>
    </li>
  );
}

/** Statistici › Audit piețe: ROI pe cotele reale Superbet și ce face Robotul cu fiecare piață (refăcut la fiecare rulare). */
type PG = { n: number; win_rate: number | null; roi: number | null; avg_odds: number | null };
type PDoc = { groups: Array<{ name: string; all: PG; last7: PG }>; days: Array<PG & { day: string }>; tickets: { n: number; won: number; roi: number | null }; note: string };

/** Monitorizarea tiparului 80%+ (predicții clasice pe piețele bune față de rest și de Stil). */
function Pattern80() {
  const q = useAsync(() => getJSON<PDoc>('api/stats/pattern80.json'), []);
  const d = q.data;
  if (!d) return null;
  const line = (g: PG) => (g.n ? `${g.n} · intră ${((g.win_rate ?? 0) * 100).toFixed(0)}% · cota ${g.avg_odds?.toFixed(2)}` : 'fără rezultate');
  return (
    <section>
      <h3 className="mb-1 text-sm font-bold">Tiparul 80%+</h3>
      <ul>{d.groups.map((g) => (
        <li key={g.name} className="flex items-center gap-2 border-b border-border/50 py-1.5 text-xs last:border-0">
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{g.name}</div>
            <div className="text-[11px] text-muted-foreground">Total: {line(g.all)} · 7 zile: <span className={tone(g.last7.roi)}>{pct(g.last7.roi)}</span></div>
          </div>
          <span className={`num w-14 shrink-0 text-right font-extrabold ${tone(g.all.roi)}`}>{pct(g.all.roi)}</span>
        </li>
      ))}</ul>
      {d.days.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">{d.days.map((x) => (
          <span key={x.day} className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${tone(x.roi)}`}>{x.day.slice(8)}.{x.day.slice(5, 7)}: {((x.win_rate ?? 0) * 100).toFixed(0)}% · {pct(x.roi)}</span>
        ))}</div>
      )}
      <p className="mt-1 text-[11px] text-muted-foreground">Biletele „Tiparul 80%+”: {d.tickets.n ? `${d.tickets.won} câștigate din ${d.tickets.n}, ROI ${pct(d.tickets.roi)}` : 'încă nedecontate'}. {d.note}</p>
    </section>
  );
}

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
      <Pattern80 />
      {d.boosts.length > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-bold">Cote mărite</h3>
          <ul>{d.boosts.map((b) => <Row key={b.name} name={b.name} n={b.n} win={b.win_rate} odds={b.avg_odds} roi={b.roi} />)}</ul>
        </section>
      )}
      {(d.boost_split?.length ?? 0) > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-bold">Bilete Stil: cu cotă mărită față de fără</h3>
          <ul>{d.boost_split!.map((b) => (
            <li key={b.name} className="flex items-center gap-2 border-b border-border/50 py-1.5 text-xs last:border-0">
              <div className="min-w-0 flex-1">
                <div className="font-semibold">{b.name}</div>
                <div className="text-[11px] text-muted-foreground">
                  {b.n} bilete · {b.won} câștigate · cota medie {b.avg_odds.toFixed(0)} · {b.avg_legs} selecții
                  {b.leg_win_rate != null && <> · selecțiile intră {(b.leg_win_rate * 100).toFixed(0)}%</>}
                  {b.boost_win_rate != null && <> · cota mărită intră {(b.boost_win_rate * 100).toFixed(0)}%</>}
                </div>
              </div>
              <span className={`num w-14 shrink-0 text-right font-extrabold ${tone(b.roi)}`}>{pct(b.roi)}</span>
            </li>
          ))}</ul>
          <p className="mt-1 text-[11px] text-muted-foreground">Biletele de cotă mare se câștigă rar: până la câteva zeci de bilete, cât intră selecțiile spune mai mult decât ROI-ul.</p>
        </section>
      )}
      <section>
        <h3 className="mb-1 text-sm font-bold">Piețe Stil (cote reale Superbet)</h3>
        <ul>{stil.map((s) => <Row key={s.key} name={s.label} n={s.n} win={s.win_rate} odds={s.avg_odds} roi={s.roi} badge={[s.status, ST[s.status] ?? 'muted']} note={s.status === 'scoasă din bilete' ? reopen(s) : undefined} />)}</ul>
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
