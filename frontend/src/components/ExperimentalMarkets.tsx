import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { useAsync, getJSON } from '@/lib/fetcher';
import { addDays, roTime, todayRo } from '@/lib/format';
import { BuilderStats } from '@/components/BuilderStats';
import { cn } from '@/lib/utils';

 type MarketRow = {
  market: string; label: string; line: number; selection: string; p: number;
  fair_odds?: number | null; odds?: number | null; odds_observed_at?: string | null;
  odds_source?: string | null; mean?: number | null; result?: 'won' | 'lost' | null;
};
 type MatchRow = { match_id: number; home: string; away: string; kickoff_utc: string; markets: MarketRow[] };
 type DayDoc = { date: string; experimental: true; recommended: false; note: string; matches: MatchRow[] };
 type StatRow = { market: string; line: number; selection: string; n: number; won: number; lost: number;
  hit_rate: number; p_mean: number; logloss: number; n_with_superbet_odds: number; paper_roi: number | null; proven: boolean; ticket_eligible: false };
type StatsDoc = { experimental: true; proof_rule: string; markets: Record<string, StatRow> };

const SHOWN_MARKETS = new Set(['team_home', 'team_away', 'h1', 'h2', 'corners', 'ht_corners', 'h1_result', 'h2_result',
  'half_most_goals', 'goals_range', 'corners_range', 'ht_corners_range']);
const MARKET_NAMES: Record<string, string> = {
  team_home: 'Goluri gazde', team_away: 'Goluri oaspeți', h1: 'Goluri prima repriză', h2: 'Goluri repriza a doua',
  corners: 'Cornere meci', ht_corners: 'Cornere prima repriză', h1_result: 'Rezultat prima repriză',
  h2_result: 'Rezultat repriza a doua', half_most_goals: 'Repriza cu cele mai multe goluri',
  goals_range: 'Interval goluri', corners_range: 'Interval cornere meci', ht_corners_range: 'Interval cornere prima repriză',
};
const OUTCOMES: Record<string, string> = {
  OVER: 'peste', UNDER: 'sub', HOME: 'gazde', AWAY: 'oaspeți', DRAW: 'egal', FIRST: 'repriza 1', EQUAL: 'egalitate', SECOND: 'repriza 2',
  'LT:9': 'sub 9', 'RANGE:11': '9–11', 'GE:12': '12+', 'LT:5': 'sub 5', 'RANGE:6': '5–6', 'GE:7': '7+',
};

function pct(n?: number | null) { return n == null ? '—' : `${(n * 100).toFixed(1).replace('.', ',')}%`; }
function dec(n?: number | null) { return n == null ? '—' : n.toFixed(2).replace('.', ','); }
function selectionLabel(s: StatRow) {
  if (s.selection.startsWith('RANGE:')) return `${s.line}–${s.selection.slice(6)}`;
  const outcome = OUTCOMES[s.selection] ?? s.selection;
  if (s.selection.startsWith('LT:') || s.selection.startsWith('GE:')) return outcome;
  return s.market === 'h1_result' || s.market === 'h2_result' || s.market === 'half_most_goals'
    ? outcome : `${outcome} ${s.line}`;
}

function paperRank(x: MarketRow): number {
  const o = x.odds ?? 0;
  const corners = x.market.includes('corner') ? 2 : 0;
  const band = o >= 1.3 && o <= 2.2 ? 3 : o >= 1.2 ? 1 : 0;
  return corners * 10 + band * 5 + (o > 1 ? 2 : 0) + (x.p ?? 0);
}

export function ExperimentalMarkets({ day = null }: { day?: string | null }) {
  const today = todayRo();
  const days = useMemo(() => day ? [day] : [today, addDays(today, 1), addDays(today, 2)], [day, today]);
  const feed = useAsync(async () => Promise.all(days.map((d) => getJSON<DayDoc>(`api/experimental/${d}.json`))), [days.join('|')]);
  const stats = useAsync(() => getJSON<StatsDoc>('api/experimental/stats.json'), []);
  const [pricedOnly, setPricedOnly] = useState(true);
  const [openId, setOpenId] = useState<number | null>(null);
  const grouped = useMemo(() => (feed.data ?? []).flatMap((d) => d?.matches ?? []).map((m) => ({
    ...m,
    rows: m.markets.filter((x) => SHOWN_MARKETS.has(x.market) && (!pricedOnly || x.odds != null)).sort((a, b) => paperRank(b) - paperRank(a)),
  })).filter((m) => m.rows.length), [feed.data, pricedOnly]);
  const statRows = Object.values(stats.data?.markets ?? {}).filter((s) => SHOWN_MARKETS.has(s.market) && s.n > 0)
    .sort((a, b) => (MARKET_NAMES[a.market] ?? a.market).localeCompare(MARKET_NAMES[b.market] ?? b.market)
      || a.line - b.line || a.selection.localeCompare(b.selection));
  if (feed.loading) return <div className="card p-4 text-sm text-muted-foreground">Se încarcă predicțiile experimentale…</div>;
  return <section className="space-y-3" aria-label="Piețe experimentale">
    <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs leading-relaxed">
      <b>Hârtie, nu pont.</b> Niciuna din piețele astea nu e combinația măsurată și nu intră pe bilete. Întâi apar liniile cu cotă Superbet, cu cornerele înainte. Fără cotă înseamnă că prețul nu a fost confirmat.
    </div>
    <div className="flex gap-1.5" role="group" aria-label="Cote">
      <button type="button" className={cn('chip', pricedOnly && 'chip-on')} aria-pressed={pricedOnly} onClick={() => setPricedOnly(true)}>Cu cotă</button>
      <button type="button" className={cn('chip', !pricedOnly && 'chip-on')} aria-pressed={!pricedOnly} onClick={() => setPricedOnly(false)}>Și fără cotă</button>
    </div>
    {grouped.length ? <div className="grid gap-3 md:grid-cols-2">
      {grouped.map((m) => {
        const shown = openId === m.match_id ? m.rows : m.rows.slice(0, 3);
        return <article key={m.match_id} className="card p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><div className="truncate text-sm font-bold">{m.home} – {m.away}</div><div className="text-[11px] text-muted-foreground">{roTime(m.kickoff_utc)}</div></div>
            <span className="shrink-0 rounded-full bg-amber-500/15 px-2 py-1 text-[10px] font-bold uppercase text-amber-500">hârtie</span>
          </div>
          <div className="mt-1 divide-y">
            {shown.map((r) => <div key={`${r.market}-${r.line}-${r.selection}`} className="flex items-end justify-between gap-3 py-2">
              <div className="min-w-0"><div className="text-sm font-semibold">{r.label}</div><div className="text-[11px] text-muted-foreground">Cotă {dec(r.odds)} · corectă {dec(r.fair_odds)}{r.result ? ` · ${r.result === 'won' ? 'câștigat' : 'pierdut'}` : ''}</div></div>
              <div className="text-right text-xs text-muted-foreground">model<b className="num ml-1 text-sm text-foreground">{pct(r.p)}</b></div>
            </div>)}
          </div>
          {m.rows.length > 3 && <button type="button" className="min-h-10 text-[13px] font-semibold text-muted-foreground" onClick={() => setOpenId(openId === m.match_id ? null : m.match_id)}>{openId === m.match_id ? 'Mai puține' : `Încă ${m.rows.length - 3} linii`}</button>}
        </article>;
      })}
    </div> : <div className="card p-4 text-sm text-muted-foreground">Nu există predicții experimentale publicate pentru această zi. Oferta sau datele necesare pot lipsi.</div>}
    <details className="card px-4 py-2">
      <summary className="cursor-pointer py-1 text-sm font-bold">Performanță experimentală pe termen lung</summary>
      <p className="my-2 text-[11px] text-muted-foreground">ROI-ul este paper, calculat numai pentru selecțiile decontate care aveau cotă Superbet salvată. Nu este profit din pariuri efectuate. Prag de validare: {stats.data?.proof_rule ?? 'încărcare…'}</p>
      {statRows.length ? <div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left text-xs"><thead><tr className="border-b text-muted-foreground"><th className="py-2">Piață / selecție</th><th>n</th><th>Câștigate</th><th>Hit rate</th><th>Șansă medie</th><th>Acoperire cote</th><th>ROI paper</th></tr></thead><tbody>{statRows.map((s) => <tr key={`${s.market}-${s.line}-${s.selection}`} className="border-b border-border/50"><td className="py-2">{MARKET_NAMES[s.market] ?? s.market} · {selectionLabel(s)}</td><td>{s.n}</td><td>{s.won}/{s.n}</td><td>{pct(s.hit_rate)}</td><td>{pct(s.p_mean)}</td><td>{s.n_with_superbet_odds}/{s.n}</td><td className={s.paper_roi != null && s.paper_roi < 0 ? 'text-loss' : ''}>{pct(s.paper_roi)}</td></tr>)}</tbody></table></div> : <p className="py-2 text-xs text-muted-foreground">Nu există rezultate decontate încă.</p>}
    </details>
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-extrabold">BetBuilder — urmărire separată</h3><Link to="/builder" className="btn btn-outline min-h-9 px-3 text-xs">Vezi sugestiile</Link></div>
      <p className="text-[11px] text-muted-foreground">BetBuilder-ele folosesc trackerul și decontarea lor existente; statisticile de mai jos nu se amestecă cu piețele simple.</p>
      <BuilderStats embedded />
    </div>
  </section>;
}
