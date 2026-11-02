import { useMemo } from 'react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { addDays, roTime } from '@/lib/format';
import { todayRo } from '@/lib/format';

 type MarketRow = {
  market: string; label: string; line: number; selection: 'OVER' | 'UNDER'; p: number;
  fair_odds?: number | null; odds?: number | null; odds_observed_at?: string | null;
  odds_source?: string | null; mean?: number | null; result?: 'won' | 'lost' | null;
};
 type MatchRow = { match_id: number; home: string; away: string; kickoff_utc: string; markets: MarketRow[] };
 type DayDoc = { date: string; experimental: true; recommended: false; note: string; matches: MatchRow[] };
 type StatRow = { market: string; line: number; selection: string; n: number; won: number; lost: number;
  hit_rate: number; p_mean: number; logloss: number; n_with_superbet_odds: number; paper_roi: number | null; proven: boolean; ticket_eligible: false };
 type StatsDoc = { experimental: true; proof_rule: string; markets: Record<string, StatRow> };

function pct(n?: number | null) { return n == null ? '—' : `${(n * 100).toFixed(1).replace('.', ',')}%`; }
function dec(n?: number | null) { return n == null ? '—' : n.toFixed(2).replace('.', ','); }

export function ExperimentalMarkets({ day = null }: { day?: string | null }) {
  const today = todayRo();
  const days = useMemo(() => day ? [day] : [today, addDays(today, 1), addDays(today, 2)], [day, today]);
  const feed = useAsync(async () => Promise.all(days.map((d) => getJSON<DayDoc>(`api/experimental/${d}.json`))), [days.join('|')]);
  const stats = useAsync(() => getJSON<StatsDoc>('api/experimental/stats.json'), []);
  const matches = (feed.data ?? []).flatMap((d) => d?.matches ?? []);
  const rows = matches.flatMap((m) => m.markets.map((x) => ({ ...x, match: `${m.home} – ${m.away}`, kickoff: m.kickoff_utc }))
    .filter((x) => ['h1', 'h2', 'corners'].includes(x.market)));
  const statRows = Object.values(stats.data?.markets ?? {}).filter((s) => ['h1', 'h2', 'corners'].includes(s.market) && s.n > 0)
    .sort((a, b) => a.market.localeCompare(b.market) || a.line - b.line || a.selection.localeCompare(b.selection));
  if (feed.loading) return <div className="card p-4 text-sm text-muted-foreground">Se încarcă predicțiile experimentale…</div>;
  return <section className="space-y-3" aria-label="Piețe experimentale">
    <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs leading-relaxed">
      <b>Urmărire pe hârtie — nu sunt recomandări și nu intră în bilete.</b> Cotele afișate sunt ultimele cote Superbet observate înaintea predicției; lipsa cotei înseamnă că nu a fost găsită o ofertă exactă și proaspătă.
    </div>
    {rows.length ? <div className="space-y-2">
      {rows.map((r, i) => <article key={`${r.match}-${r.market}-${r.line}-${r.selection}-${i}`} className="card p-3">
        <div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="truncate text-sm font-bold">{r.match}</div><div className="text-[11px] text-muted-foreground">{roTime(r.kickoff)}</div></div>
          <span className="shrink-0 rounded-full bg-amber-500/15 px-2 py-1 text-[10px] font-bold uppercase text-amber-500">experimental</span></div>
        <div className="mt-2 flex items-end justify-between gap-3"><div className="text-sm font-semibold">{r.label}</div><div className="text-right"><div className="text-xs text-muted-foreground">Șansă model</div><b className="num">{pct(r.p)}</b></div></div>
        <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-muted-foreground"><span>Cotă Superbet: <b className="num text-foreground">{dec(r.odds)}</b></span><span>Cotă corectă model: <b className="num text-foreground">{dec(r.fair_odds)}</b></span>{r.result && <span>Rezultat: <b>{r.result === 'won' ? 'câștigat' : 'pierdut'}</b></span>}</div>
      </article>)}
    </div> : <div className="card p-4 text-sm text-muted-foreground">Nu există predicții experimentale publicate pentru această zi. Oferta sau datele necesare pot lipsi.</div>}
    <details className="card px-4 py-2">
      <summary className="cursor-pointer py-1 text-sm font-bold">Performanță experimentală pe termen lung</summary>
      <p className="my-2 text-[11px] text-muted-foreground">ROI-ul este paper, calculat numai pentru selecțiile decontate care aveau cotă Superbet salvată. Nu este profit din pariuri efectuate. Prag de validare: {stats.data?.proof_rule ?? 'încărcare…'}</p>
      {statRows.length ? <div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left text-xs"><thead><tr className="border-b text-muted-foreground"><th className="py-2">Piață / selecție</th><th>n</th><th>Câștigate</th><th>Hit rate</th><th>Șansă medie</th><th>Acoperire cote</th><th>ROI paper</th></tr></thead><tbody>{statRows.map((s) => <tr key={`${s.market}-${s.line}-${s.selection}`} className="border-b border-border/50"><td className="py-2">{s.market} {s.selection === 'OVER' ? 'peste' : 'sub'} {s.line}</td><td>{s.n}</td><td>{s.won}/{s.n}</td><td>{pct(s.hit_rate)}</td><td>{pct(s.p_mean)}</td><td>{s.n_with_superbet_odds}/{s.n}</td><td className={s.paper_roi != null && s.paper_roi < 0 ? 'text-loss' : ''}>{pct(s.paper_roi)}</td></tr>)}</tbody></table></div> : <p className="py-2 text-xs text-muted-foreground">Nu există rezultate decontate încă.</p>}
    </details>
  </section>;
}
