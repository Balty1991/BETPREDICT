import { useMemo, useState } from 'react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { Badge } from '@/components/kit';
import { cn } from '@/lib/utils';

type Row = { match_id: number; key: string; label: string; p: number; odds?: number | null; fair_odds?: number | null; edge?: number | null;
  kickoff_utc: string; home: string; away: string; src: string; bb: boolean; corner_mean?: number | null };
type Doc = { count: number; matches: number; note: string; rows: Row[] };

const GROUPS: Array<[string, string, (k: string) => boolean]> = [
  ['all', 'Toate', () => true],
  ['corn', 'Cornere', (k) => /^C\d/.test(k)],
  ['h1c', 'R1 cornere', (k) => k.startsWith('H1C')],
  ['half', 'Reprize', (k) => ['R1R2', 'H13x2', 'R1O15'].includes(k)],
  ['int', 'Interval goluri', (k) => /^G\d/.test(k)],
  ['bb', 'Bet Builder', (k) => k.startsWith('BB_')],
];
const tz = 'Europe/Bucharest';
const when = (iso: string) => new Date(iso).toLocaleString('ro-RO', { weekday: 'short', hour: '2-digit', minute: '2-digit', timeZone: tz });

/** Predicții „Stil Supersocial” (cornere, reprize, intervale, BB) sortate după șansă, cu prețul Superbet și EV. */
export function SupersocialList() {
  const q = useAsync(() => getJSON<Doc>('api/supersocial/today.json'), []);
  const [g, setG] = useState('all');
  const [minP, setMinP] = useState(0.6);
  const rows = useMemo(() => {
    const f = GROUPS.find((x) => x[0] === g)![2];
    return (q.data?.rows ?? []).filter((r) => f(r.key) && r.p >= minP);
  }, [q.data, g, minP]);
  if (q.loading) return <div className="card p-4 text-sm text-muted-foreground">Se încarcă…</div>;
  if (!q.data) return <div className="card p-4 text-sm text-muted-foreground">Predicțiile Stil Supersocial nu sunt publicate încă.</div>;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {GROUPS.map(([id, l]) => <button key={id} className={cn('chip', g === id && 'chip-on')} aria-pressed={g === id} onClick={() => setG(id)}>{l}</button>)}
        {[0.5, 0.6, 0.7, 0.8].map((x) => <button key={x} className={cn('chip', minP === x && 'chip-on')} onClick={() => setMinP(x)}>≥{x * 100}%</button>)}
      </div>
      <p className="text-[11px] text-muted-foreground">{rows.length} selecții · sortate după șansă. EV = șansa modelului × cota Superbet − 1. {q.data.note}</p>
      <ul className="card divide-y px-3">
        {rows.slice(0, 200).map((r) => (
          <li key={`${r.match_id}-${r.key}`} className="flex items-start gap-2 py-2.5">
            <div className="min-w-0 flex-1">
              <div className="break-words text-[13px] font-semibold leading-snug">{r.label}</div>
              <div className="break-words text-xs">{r.home} – {r.away}</div>
              <div className="text-[11px] text-muted-foreground">{when(r.kickoff_utc)} · {r.src}{r.corner_mean && /C/.test(r.key) ? ` · ~${r.corner_mean} cornere` : ''}</div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <span className="num text-sm font-extrabold">{(r.p * 100).toFixed(0)}%</span>
              {r.odds ? (
                <span className="num text-xs">@{r.odds.toFixed(2)}</span>
              ) : <span className="num text-[11px] text-muted-foreground">corect {r.fair_odds?.toFixed(2)}</span>}
              {r.edge != null ? <Badge tone={r.edge > 0 ? 'win' : 'loss'}>EV {r.edge > 0 ? '+' : ''}{(r.edge * 100).toFixed(1)}%</Badge> : r.bb ? <Badge tone="muted">BB</Badge> : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
