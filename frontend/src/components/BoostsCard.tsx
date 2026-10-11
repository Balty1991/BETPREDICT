import { useState } from 'react';
import { Zap } from 'lucide-react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { Badge } from '@/components/kit';

type Boost = { match_id: number; home: string; away: string; league?: string; kickoff_utc: string; kind: string; label: string; info?: string;
  price: number; orig_price?: number | null; boost_pct?: number | null; p_fair?: number | null; ev?: number | null; method?: string; reliable: boolean };
type Doc = { count: number; positive_ev: number; boosts: Boost[]; rules: string;
  stats?: Record<string, { n: number; won: number; hit_rate: number | null; roi: number | null } | number> };

const hm = (iso: string) => new Date(iso).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Bucharest' });

/** „Cote mărite” Superbet cu EV calculat (sub Biletul zilei). */
export function BoostsCard() {
  const doc = useAsync(() => getJSON<Doc>('api/boosts/today.json'), []);
  const [all, setAll] = useState(false);
  const d = doc.data;
  if (!d || !d.boosts?.length) return null;
  const list = all ? d.boosts : d.boosts.slice(0, 4);
  const st = d.stats?.toate as { n: number; hit_rate: number | null; roi: number | null } | undefined;
  return (
    <section aria-labelledby="boosts-title" className="card mb-4 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 id="boosts-title" className="flex items-center gap-1.5 text-sm font-bold"><Zap className="h-4 w-4 text-warn" />Cote mărite Superbet</h2>
        <span className="text-[11px] text-muted-foreground">{d.positive_ev}/{d.count} cu EV&gt;0</span>
      </div>
      <ul className="space-y-1.5">
        {list.map((b) => (
          <li key={`${b.match_id}-${b.label}`} className="flex items-center gap-2 rounded-lg bg-muted/40 px-2 py-1.5">
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-semibold">{b.label}</div>
              <div className="truncate text-[11px] text-muted-foreground">{b.home} – {b.away} · {hm(b.kickoff_utc)}</div>
            </div>
            <div className="text-right">
              <div className="num text-sm font-extrabold">{b.price.toFixed(2)}</div>
              {b.orig_price ? <div className="num text-[10px] text-muted-foreground line-through">{b.orig_price.toFixed(2)}</div> : null}
            </div>
            {b.ev != null
              ? <Badge tone={b.ev > 0 ? 'win' : 'loss'} title={b.method}>{b.ev > 0 ? '+' : ''}{(b.ev * 100).toFixed(0)}%{b.reliable ? '' : '?'}</Badge>
              : <Badge tone="muted">n/a</Badge>}
          </li>
        ))}
      </ul>
      <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
        <span>„?” = estimare incertă{st && st.n ? ` · istoric: ${st.n} decontate, lovit ${((st.hit_rate ?? 0) * 100).toFixed(0)}%, ROI ${((st.roi ?? 0) * 100).toFixed(0)}%` : ''}</span>
        {d.boosts.length > 4 ? <button type="button" className="font-semibold text-primary" onClick={() => setAll(!all)}>{all ? 'Mai puține' : `Toate (${d.boosts.length})`}</button> : null}
      </div>
    </section>
  );
}
