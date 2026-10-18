import { useState } from 'react';
import { Link } from 'react-router';
import { getJSON, useAsync } from '@/lib/fetcher';
import { roTime } from '@/lib/format';
import { cn } from '@/lib/utils';

interface Mh { key: string; label: string; status: 'active' | 'paused'; since: string; n: number; hit: number; p: number; roi: number }
interface MhDoc { days: number; min_n: number; rule: string; markets: Mh[] }
interface Va { match_id: number; kickoff_utc: string; home: string; away: string; league?: string; label: string; superbet: number; fair: number; value: number }
interface VaDoc { generated_at: string; alerts: Va[]; record: { settled: number; won: number; expected: number; roi: number | null }; push_enabled: boolean; push_rule: string }

const pct = (v: number, d = 0) => `${(v * 100).toFixed(d)}%`;

/** Piețele Stil: active / pauzate automat (modelul promite peste ce intră și pierd). */
export function MarketHealth() {
  const { data } = useAsync(() => getJSON<MhDoc>('api/stats/market_health.json'), []);
  if (!data?.markets?.length) return null;
  const paused = data.markets.filter((m) => m.status === 'paused');
  const active = data.markets.filter((m) => m.status === 'active').sort((a, b) => b.roi - a.roi);
  const Row = ({ m }: { m: Mh }) => (
    <li className="flex items-center justify-between gap-2 py-1.5 text-xs">
      <span className="min-w-0 truncate">{m.label}</span>
      <span className="num shrink-0 text-muted-foreground">{m.n} · {pct(m.hit)} vs {pct(m.p)} · <b className={m.roi >= 0 ? 'text-win' : 'text-loss'}>{m.roi >= 0 ? '+' : ''}{pct(m.roi, 1)}</b></span>
    </li>
  );
  return (
    <section className="card p-3.5" aria-label="Piețe active și pauzate">
      <div className="flex items-center justify-between">
        <h2 className="text-[15px] font-bold">Piețe active / pauzate</h2>
        <span className="text-[11px] text-muted-foreground">ultimele {data.days} zile</span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-center">
        <div className="rounded-xl bg-muted/50 py-2"><div className="big-num text-[22px] text-win">{active.length}</div><div className="label">active</div></div>
        <div className="rounded-xl bg-muted/50 py-2"><div className={cn('big-num text-[22px]', paused.length ? 'text-loss' : '')}>{paused.length}</div><div className="label">pauzate</div></div>
      </div>
      {paused.length > 0 && <ul className="mt-2 divide-y divide-border/50">{paused.map((m) => <Row key={m.key} m={m} />)}</ul>}
      <details className="mt-1 text-xs">
        <summary className="inline-flex min-h-9 cursor-pointer items-center font-semibold text-primary">Toate piețele active ▾</summary>
        <ul className="divide-y divide-border/50">{active.map((m) => <Row key={m.key} m={m} />)}</ul>
        <p className="mt-1 text-[11px] text-muted-foreground">Rândul: selecții · intrate vs promise · ROI. {data.rule}.</p>
      </details>
    </section>
  );
}

/** Superbet peste prețul corect Pinnacle (fără marjă), pe meciuri neîncepute. */
export function ValueAlerts() {
  const { data } = useAsync(() => getJSON<VaDoc>('api/alerts/value.json'), []);
  const [now] = useState(() => Date.now());
  if (!data) return null;
  const list = data.alerts.filter((a) => new Date(a.kickoff_utc).getTime() > now);
  const r = data.record;
  return (
    <details className="card p-3.5" aria-label="Cote cu valoare față de Pinnacle">
      <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-2">
        <span className="text-[15px] font-bold">Valoare vs Pinnacle <span className="ml-1 rounded-full bg-primary/15 px-2 py-0.5 text-xs text-primary">{list.length}</span></span>
        <span className="text-[11px] text-muted-foreground">▾</span>
      </summary>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Superbet plătește cu ≥ 5% peste cota corectă Pinnacle. Istoric: {r.settled} decontate, {r.won} câștigate (așteptat {r.expected.toLocaleString('ro-RO')}){r.roi != null ? `, ROI ${r.roi >= 0 ? '+' : ''}${pct(r.roi, 1)}` : ''}.
        {data.push_enabled ? ' Notificări pornite.' : ` În probă: ${data.push_rule}.`}
      </p>
      {list.length === 0 ? <p className="mt-2 text-xs text-muted-foreground">Nicio cotă cu valoare acum.</p> : (
        <ul className="mt-1 divide-y divide-border/50">
          {list.map((a) => (
            <li key={`${a.match_id}-${a.label}`}>
              <Link to={`/meci/${a.match_id}`} className="flex items-center justify-between gap-2 py-2 text-xs">
                <span className="min-w-0"><span className="block truncate font-semibold">{a.home} – {a.away}</span><span className="text-muted-foreground">{roTime(a.kickoff_utc)} · {a.label}</span></span>
                <span className="shrink-0 text-right"><span className="big-num text-[15px] text-primary">{a.superbet.toFixed(2)}</span><span className="block text-[11px] text-muted-foreground">corect {a.fair.toFixed(2)} · <b className="text-win">+{pct(a.value)}</b></span></span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}
