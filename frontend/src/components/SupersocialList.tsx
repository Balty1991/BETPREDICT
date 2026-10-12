import { useMemo, useState } from 'react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { Badge } from '@/components/kit';
import { cn } from '@/lib/utils';

type Row = { match_id: number; key: string; label: string; p: number; odds?: number | null; fair_odds?: number | null; edge?: number | null;
  kickoff_utc: string; home: string; away: string; src: string; bb: boolean; est?: boolean; corner_mean?: number | null; group?: string };
type Doc = { count: number; matches: number; note: string; rows: Row[] };

const GROUPS: Array<[string, string, string[]]> = [
  ['all', 'Toate', []],
  ['reprize', 'Goluri pe reprize', ['H13x2', 'R1R2', 'BB_H13x2_O15']],
  ['combo', 'Combo R1 0.5 & 1.5', ['R1O15']],
  ['interval', 'Interval goluri', ['G13', 'G24', 'G25']],
  ['r1_cornere', 'R1 cornere', ['H1CLT5', 'H1C56', 'H1C7P', 'H1C25', 'H1C35', 'BB_H1C25_U65']],
  ['cornere', 'Cornere meci', ['C65', 'C75', 'C85', 'C95', 'BB_C65_U145']],
];
const SHORT: Record<string, string> = { H13x2: '1-3 fiecare repriză', R1R2: 'Gol ambele reprize', BB_H13x2_O15: '1-3 reprize & 1.5',
  R1O15: 'R1 0.5 & 1.5', G13: '1-3', G24: '2-4', G25: '2-5', H1CLT5: 'sub 5', H1C56: '5-6', H1C7P: '7+',
  H1C25: 'Peste 2.5', H1C35: 'Peste 3.5', BB_H1C25_U65: 'Interval 3-6',
  C65: 'Peste 6.5', C75: 'Peste 7.5', C85: 'Peste 8.5', C95: 'Peste 9.5', BB_C65_U145: '6.5 & sub 14.5' };
const tz = 'Europe/Bucharest';
const when = (iso: string) => new Date(iso).toLocaleString('ro-RO', { weekday: 'short', hour: '2-digit', minute: '2-digit', timeZone: tz });

/** Predicții „Stil Supersocial” (cornere, reprize, intervale, BB) sortate după șansă, cu prețul Superbet și EV. */
export function SupersocialList() {
  const q = useAsync(() => getJSON<Doc>('api/supersocial/today.json'), []);
  const [g, setG] = useState('all');
  const [k, setK] = useState('');
  const [minP, setMinP] = useState(0);
  const keys = GROUPS.find((x) => x[0] === g)![2];
  const all = q.data?.rows ?? [];
  const cnt = (f: (r: Row) => boolean) => all.filter((r) => f(r) && r.p >= minP).length;
  const rows = useMemo(() => all.filter((r) => (k ? r.key === k : !keys.length || keys.includes(r.key)) && r.p >= minP),
    [all, keys, k, minP]);
  if (q.loading) return <div className="card p-4 text-sm text-muted-foreground">Se încarcă…</div>;
  if (!q.data) return <div className="card p-4 text-sm text-muted-foreground">Predicțiile Stil Supersocial nu sunt publicate încă.</div>;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {GROUPS.map(([id, l, ks]) => <button key={id} className={cn('chip', g === id && 'chip-on')} aria-pressed={g === id}
          onClick={() => { setG(id); setK(''); }}>{l} ({cnt((r) => !ks.length || ks.includes(r.key))})</button>)}
      </div>
      {keys.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          <button className={cn('chip', !k && 'chip-on')} onClick={() => setK('')}>Toate</button>
          {keys.map((x) => <button key={x} className={cn('chip', k === x && 'chip-on')} aria-pressed={k === x} onClick={() => setK(x)}>{SHORT[x] ?? x} ({cnt((r) => r.key === x)})</button>)}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {[0, 0.5, 0.6, 0.7, 0.8].map((x) => <button key={x} className={cn('chip', minP === x && 'chip-on')} onClick={() => setMinP(x)}>{x ? `≥${x * 100}%` : 'Orice șansă'}</button>)}
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
                <span className="num text-xs">@{r.odds.toFixed(2)}{r.est ? ' est.' : ''}</span>
              ) : <span className="num text-[11px] text-muted-foreground">corect {r.fair_odds?.toFixed(2)}</span>}
              {r.edge != null ? <Badge tone={r.edge > 0 ? 'win' : 'loss'}>EV {r.edge > 0 ? '+' : ''}{(r.edge * 100).toFixed(1)}%</Badge> : r.bb ? <Badge tone="muted">BB</Badge> : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
