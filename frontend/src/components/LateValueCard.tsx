import { useState } from 'react';
import { Link } from 'react-router';
import { Clock } from 'lucide-react';
import { getJSON, useAsync } from '@/lib/fetcher';
import { odds as fo, pct, roDateTime, roTime, signed } from '@/lib/format';
import { Panel } from '@/components/dash';
import { SbPickButton, SuperbetLink } from '@/components/SuperbetLink';
import { cn } from '@/lib/utils';

export interface LvAlert {
  match_id: number; market: string; outcome: string; label: string; alerted_at: string; kickoff_utc: string;
  home: string; away: string; league?: string | null; superbet: number; fair: number | null; p_fair: number; edge: number;
  pin_price?: number | null; close_pin?: number | null; clv?: number | null; result?: string | null; score?: string | null; stake: number;
  superbet_url?: string | null; sb_event_id?: string | null; sb_pick?: { market: string; outcome: string; ref?: string } | null;
}
export interface LvDoc {
  generated_at: string; paper: boolean; rule: { min_edge: number; max_odds: number; window_h: number; stake: number; text: string };
  alerts: LvAlert[]; recent: LvAlert[];
  record: { alerts: number; settled: number; won: number; pending: number; hit_rate: number | null; staked: number; profit: number;
    roi: number | null; clv_n: number; avg_clv: number | null; beat_close: number | null };
  backtest: { n: number; roi: number; roi_ci: [number, number]; clv: number; per_week: number; note: string };
}

export function useLateValue() {
  return useAsync(() => getJSON<LvDoc>('api/alerts/late_value.json'), []);
}

const until = (iso: string, now: number) => {
  const m = Math.round((new Date(iso).getTime() - now) / 60000);
  return m >= 60 ? `în ${Math.floor(m / 60)} h ${m % 60} min` : `în ${m} min`;
};

/** Acasă: „Valoare în ultimele 3 ore” — Superbet peste prețul corect Pinnacle, aproape de start. Pe hârtie până la dovadă. */
export function LateValueCard() {
  const { data } = useLateValue();
  const [now] = useState(() => Date.now());
  if (!data) return null;
  const list = data.alerts.filter((a) => new Date(a.kickoff_utc).getTime() > now);
  const r = data.record;
  return (
    <Panel title="Valoare în ultimele 3 ore" icon={<Clock className="h-4 w-4" />}
      right={<span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-warn">pe hârtie</span>}>
      <p className="text-[11px] leading-snug text-muted-foreground">
        Simplu, cota Superbet cu ≥ {Math.round(data.rule.min_edge * 100)}% peste prețul corect Pinnacle, cu cel mult {data.rule.window_h} ore
        înainte de start, cota ≤ {data.rule.max_odds}. Miză de urmărire: {data.rule.stake} leu.
      </p>
      {list.length === 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">Nicio cotă cu valoare acum. Verificăm la fiecare rulare (actualizat {roTime(data.generated_at)}).</p>
      ) : (
        <ul className="mt-1 divide-y divide-border/50">
          {list.map((a) => (
            <li key={`${a.match_id}-${a.market}-${a.outcome}`} className="flex items-center justify-between gap-2 py-2 text-xs">
              <Link to={`/meci/${a.match_id}`} className="min-w-0">
                <span className="block truncate font-semibold">{a.home} – {a.away}</span>
                <span className="text-muted-foreground">{roTime(a.kickoff_utc)} ({until(a.kickoff_utc, now)}) · <b className="text-foreground">{a.label}</b></span>
                <span className="block text-[11px] text-muted-foreground">corect {fo(a.fair)} · valoare <b className="text-win">+{pct(a.edge, 1)}</b> · miză {a.stake} leu</span>
              </Link>
              <span className="flex shrink-0 flex-col items-end gap-0.5">
                <span className="big-num text-[17px] text-primary">{fo(a.superbet)}</span>
                {a.sb_pick && a.sb_event_id ? <SbPickButton eventId={a.sb_event_id} picks={[a.sb_pick]} webUrl={a.superbet_url} />
                  : a.superbet_url ? <SuperbetLink url={a.superbet_url} eventId={a.sb_event_id} className="inline-flex items-center gap-1 text-[11px] font-semibold text-[hsl(0_75%_62%)]" /> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
      <Link to="/statistici?tab=sumar" className="mt-2 block text-[11px] text-muted-foreground">
        Urmărire: {r.alerts} alerte{r.settled ? `, ${r.won}/${r.settled} intrate, ROI ${signed((r.roi ?? 0) * 100, 1, '%')}` : ', niciuna decontată încă'}
        {r.avg_clv != null ? ` · CLV ${signed(r.avg_clv * 100, 1, '%')}` : ''} →
      </Link>
    </Panel>
  );
}

const resTone = (r?: string | null) => (r === 'won' ? 'text-win' : r === 'lost' ? 'text-loss' : 'text-muted-foreground');
const resTxt = (r?: string | null) => (r === 'won' ? 'intrat' : r === 'lost' ? 'pierdut' : r === 'void' ? 'anulat' : 'în așteptare');

/** Statistici: urmărirea alertelor „Valoare în ultimele 3 ore” (n, rată, ROI la 1 leu, CLV față de închiderea Pinnacle). */
export function LateValueStats() {
  const { data } = useLateValue();
  if (!data) return null;
  const r = data.record;
  const b = data.backtest;
  return (
    <section className="card p-3.5 md:p-4" aria-label="Valoare în ultimele 3 ore: urmărire">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Valoare în ultimele 3 ore</h2>
        <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-warn">pe hârtie până la dovadă</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ['Alerte', String(r.alerts), r.pending ? `${r.pending} în așteptare` : 'toate decontate'],
          ['Rată de câștig', pct(r.hit_rate, 1), r.settled ? `${r.won} din ${r.settled}` : 'încă nimic decontat'],
          ['ROI (1 leu)', r.roi == null ? '—' : signed(r.roi * 100, 1, '%'), r.settled ? `profit ${signed(r.profit, 2)} lei` : '—'],
          ['CLV mediu', r.avg_clv == null ? '—' : signed(r.avg_clv * 100, 1, '%'), r.clv_n ? `${r.clv_n} cu închidere${r.beat_close != null ? `, ${pct(r.beat_close)} peste` : ''}` : 'după start'],
        ].map(([l, v, s], i) => (
          <div key={l} className="rounded-xl bg-[hsl(var(--elevated))] px-2.5 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{l}</div>
            <div className={cn('big-num mt-0.5 text-[18px]', i >= 2 && v !== '—' && (v.startsWith('+') ? 'text-win' : v.startsWith('-') ? 'text-loss' : ''))}>{v}</div>
            <div className="text-[10px] text-muted-foreground">{s}</div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
        {data.rule.text} CLV = cota luată × șansa corectă la închiderea Pinnacle − 1 (pozitiv = am bătut piața). Test pe istoric:
        {' '}{b.n} pariuri, ROI {signed(b.roi * 100, 0, '%')} (interval {signed(b.roi_ci[0] * 100, 0, '%')}…{signed(b.roi_ci[1] * 100, 0, '%')}), CLV {signed(b.clv * 100, 1, '%')}.
        Rămâne pe hârtie până când urmărirea reală are destule pariuri.
      </p>
      {data.recent.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-semibold">Ultimele alerte ({data.recent.length})</summary>
          <ul className="mt-1 divide-y divide-border/50">
            {data.recent.map((a) => (
              <li key={`${a.match_id}-${a.market}-${a.outcome}`} className="flex items-center justify-between gap-2 py-1.5 text-[11px]">
                <span className="min-w-0">
                  <span className="block truncate font-semibold">{a.home} – {a.away}</span>
                  <span className="text-muted-foreground">{roDateTime(a.kickoff_utc)} · {a.label} @{fo(a.superbet)} · +{pct(a.edge, 1)}{a.clv != null ? ` · CLV ${signed(a.clv * 100, 1, '%')}` : ''}</span>
                </span>
                <span className={cn('shrink-0 font-bold', resTone(a.result))}>{resTxt(a.result)}{a.score ? ` ${a.score}` : ''}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
