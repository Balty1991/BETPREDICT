import { useState } from 'react';
import { Zap } from 'lucide-react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { Badge } from '@/components/kit';
import { legWebUrl } from '@/components/PlayOnSuperbet';
import { eventAppLink, openSuperbet } from '@/lib/superbet';

type Boost = { match_id: number; home: string; away: string; league?: string; kickoff_utc: string; kind: string; label: string; info?: string;
  price: number; orig_price?: number | null; boost_pct?: number | null; p_fair?: number | null; ev?: number | null; method?: string; reliable: boolean; suspect?: boolean; sb_event_id?: string | null };
type Doc = { count: number; positive_ev: number; boosts: Boost[]; rules: string;
  stats?: Record<string, { n: number; won: number; hit_rate: number | null; roi: number | null } | number> };

const tz = 'Europe/Bucharest';
const dk = (d: Date) => d.toLocaleDateString('en-CA', { timeZone: tz });
const hm = (iso: string) => {
  const d = new Date(iso), t = d.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit', timeZone: tz });
  const now = new Date(), tm = new Date(now.getTime() + 864e5);
  const day = dk(d) === dk(now) ? 'Azi' : dk(d) === dk(tm) ? 'Mâine' : d.toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', timeZone: tz });
  return `${day} ${t}`;
};

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
        {list.map((b) => {
          const parts = b.label.split(';').map((x) => x.trim()).filter(Boolean);
          const open = () => b.sb_event_id && openSuperbet(eventAppLink(b.sb_event_id), legWebUrl({ sb_event_id: b.sb_event_id, home: b.home, away: b.away }));
          return (
          <li key={`${b.match_id}-${b.label}`}>
            <button type="button" onClick={open} disabled={!b.sb_event_id} aria-label={`Deschide ${b.home} – ${b.away} pe Superbet`}
              className="press flex w-full items-start gap-2 rounded-lg bg-muted/40 px-2.5 py-2 text-left">
              <div className="min-w-0 flex-1">
                <div className="break-words text-[13px] font-semibold leading-snug">{b.home} – {b.away}</div>
                <div className="text-[11px] text-muted-foreground">{hm(b.kickoff_utc)}{b.league ? ` · ${b.league}` : ''}</div>
                <ul className="mt-1 space-y-0.5">
                  {parts.map((x) => <li key={x} className="break-words text-xs leading-snug before:mr-1 before:text-primary before:content-['•']">{x}</li>)}
                </ul>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <div className="num text-base font-extrabold leading-none">{b.price.toFixed(2)}</div>
                {b.orig_price ? <div className="num text-[11px] text-muted-foreground line-through">{b.orig_price.toFixed(2)}</div> : null}
                {b.ev != null
                  ? (b.suspect || b.ev > 0.25) ? <Badge tone="warn" title={`${b.method ?? ''} · EV > 25% e aproape sigur o eroare de estimare; exclus din biletul +EV`}>EV suspect</Badge> : <Badge tone={b.ev > 0 ? 'win' : 'loss'} title={b.method}>EV {b.ev > 0 ? '+' : ''}{(b.ev * 100).toFixed(1)}%{b.reliable ? '' : ' ?'}</Badge>
                  : <Badge tone="muted">EV n/a</Badge>}
              </div>
            </button>
          </li>);
        })}
      </ul>
      <div className="mt-2 flex items-start justify-between gap-2 text-[11px] text-muted-foreground">
        <span className="min-w-0 flex-1">„?” = EV estimat: cota normală Superbet minus ~10% marjă (fără cote de piață); fără „?” = calculat din piață/Pinnacle sau model. Atinge un rând pentru meci pe Superbet.{st && st.n ? ` · istoric: ${st.n} decontate, lovit ${((st.hit_rate ?? 0) * 100).toFixed(0)}%, ROI ${((st.roi ?? 0) * 100).toFixed(0)}%` : ''}</span>
        {d.boosts.length > 4 ? <button type="button" className="font-semibold text-primary" onClick={() => setAll(!all)}>{all ? 'Mai puține' : `Toate (${d.boosts.length})`}</button> : null}
      </div>
    </section>
  );
}
