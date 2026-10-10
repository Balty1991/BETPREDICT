import { useState } from 'react';
import { useParams, useSearchParams, Link } from 'react-router';
import { ArrowLeft, TrendingDown, TrendingUp, Minus } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { findMatch, loadMatchContext } from '@/lib/data';
import { useStore } from '@/lib/store';
import { roDateTime, odds as fo, pct } from '@/lib/format';
import { marketKey, marketTitle, marketOrder, statusLabel, selectionLabel, isFinished } from '@/lib/markets';
import { Card, Loading, Empty, Segmented, TeamLogo, Badge, Notice, ProbRing, SplitBar, GradeBadge } from '@/components/kit';
import { PredLine, oneXTwo } from '@/components/MatchCard';
import { MatchBuilder } from '@/pages/BuilderPage';
import { getJSON } from '@/lib/fetcher';
import type { BuilderDay } from '@/lib/types';
import type { Match, Prediction, Form, Absence, Day } from '@/lib/types';
import { cn } from '@/lib/utils';

type Tab = 'pred' | 'ctx' | 'odds' | 'score' | 'bb';

function FormBox({ title, f }: { title: string; f?: Form | null }) {
  if (!f) return <div className="rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground">{title}: formă indisponibilă</div>;
  return (
    <div className="rounded-lg bg-muted/40 p-3">
      <div className="mb-1 text-xs font-semibold">{title}</div>
      <div className="flex gap-1">{(f.sequence ?? '').split('').map((c, i) => (
        <span key={i} className={cn('flex h-6 w-6 items-center justify-center rounded text-[11px] font-bold', c === 'W' ? 'bg-win text-win' : c === 'L' ? 'bg-loss text-loss' : 'bg-warn text-warn')}>{c === 'W' ? 'V' : c === 'L' ? 'Î' : 'E'}</span>
      ))}</div>
      <div className="mt-2 grid grid-cols-3 gap-1 text-center text-[11px]">
        <div><div className="text-muted-foreground">V-E-Î</div><b>{f.w ?? '—'}-{f.d ?? '—'}-{f.l ?? '—'}</b></div>
        <div><div className="text-muted-foreground">Goluri</div><b>{f.gf ?? '—'}:{f.ga ?? '—'}</b></div>
        <div><div className="text-muted-foreground">Pct/meci</div><b>{f.ppm != null ? f.ppm.toFixed(2) : '—'}</b></div>
      </div>
      {f.venue?.ppm != null && <div className="mt-1 text-[11px] text-muted-foreground">Acasă/deplasare: {f.venue.ppm.toFixed(2)} pct/meci ({f.venue.played} meciuri)</div>}
    </div>
  );
}

/** Mini-grafic: goluri totale în ultimele meciuri directe, cu linia 2.5. */
function H2HGoals({ recent }: { recent: Array<{ score?: string | null; date?: string | null }> }) {
  const rows = recent.slice(0, 10).map((r) => { const [a, b] = String(r.score ?? '').split(/[-:]/).map(Number); return Number.isFinite(a) && Number.isFinite(b) ? { t: a + b, d: r.date?.slice(0, 10) ?? '' } : null; }).filter(Boolean).reverse() as Array<{ t: number; d: string }>;
  if (rows.length < 2) return null;
  const max = Math.max(5, ...rows.map((r) => r.t));
  return (
    <div className="mt-3" aria-label="Goluri pe meci în H2H">
      <div className="label mb-1">Goluri / meci (linia = 2.5)</div>
      <div className="relative flex h-16 items-end gap-1">
        <div className="absolute inset-x-0 border-t border-dashed border-muted-foreground/50" style={{ bottom: `${(2.5 / max) * 100}%` }} />
        {rows.map((r, i) => <div key={i} title={`${r.d}: ${r.t} goluri`} className={cn('flex-1 rounded-t', r.t > 2.5 ? 'bg-primary/80' : 'bg-muted-foreground/40')} style={{ height: `${Math.max(4, (r.t / max) * 100)}%` }} />)}
      </div>
    </div>
  );
}

function AbsList({ title, list }: { title: string; list?: Absence[] }) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold">{title} ({list?.length ?? 0})</div>
      {!list?.length ? <div className="text-xs text-muted-foreground">Nicio absență raportată</div> : (
        <ul className="space-y-1 text-xs">{list.map((a) => (
          <li key={a.player} className="flex justify-between gap-2"><span>{a.player}{a.position ? ` (${a.position})` : ''}</span>
            <span className={cn(a.status === 'injured' ? 'text-loss' : a.status === 'suspended' ? 'text-warn' : 'text-muted-foreground')}>{a.status === 'injured' ? 'accidentat' : a.status === 'suspended' ? 'suspendat' : a.status === 'doubtful' ? 'incert' : a.status}{a.return ? ` · revine ${a.return}` : ''}</span></li>
        ))}</ul>
      )}
    </div>
  );
}

function ContextTab({ m, source }: { m: Match; source: Day['_source'] }) {
  const ctx = useAsync(() => loadMatchContext(m, source), [m.id, source]);
  if (ctx.loading) return <Loading text="Încarc forma, H2H și absențele…" />;
  const c = ctx.data ?? {};
  const h = c.h2h;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h3 className="mb-2 font-semibold">Formă (ultimele meciuri)</h3>
        <div className="grid gap-2 sm:grid-cols-2"><FormBox title={m.home.name} f={c.form?.home} /><FormBox title={m.away.name} f={c.form?.away} /></div>
      </Card>
      <Card className="p-4">
        <h3 className="mb-2 font-semibold">Meciuri directe (H2H)</h3>
        {!h || !h.total ? <p className="text-sm text-muted-foreground">Nu există meciuri directe în date.</p> : (
          <>
            <SplitBar className="mb-3" parts={[{ label: 'V gazde', p: h.home_wins ?? 0, tone: 'home' }, { label: 'Egal', p: h.draws ?? 0, tone: 'draw' }, { label: 'V oaspeți', p: h.away_wins ?? 0, tone: 'away' }]} />
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-muted/40 p-2"><div className="text-xl font-bold">{h.home_wins ?? 0}</div><div className="text-[11px] text-muted-foreground">{m.home.name}</div></div>
              <div className="rounded-lg bg-muted/40 p-2"><div className="text-xl font-bold">{h.draws ?? 0}</div><div className="text-[11px] text-muted-foreground">Egaluri</div></div>
              <div className="rounded-lg bg-muted/40 p-2"><div className="text-xl font-bold">{h.away_wins ?? 0}</div><div className="text-[11px] text-muted-foreground">{m.away.name}</div></div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span>{h.total} meciuri</span>{h.avg_goals != null && <span>· {h.avg_goals.toFixed(2)} goluri/meci</span>}
              {h.over25_rate != null && <span>· peste 2.5: {pct(h.over25_rate)}</span>}{h.btts_rate != null && <span>· GG: {pct(h.btts_rate)}</span>}
            </div>
            {h.recent?.length ? <H2HGoals recent={h.recent} /> : null}
            {h.recent?.length ? <ul className="mt-2 divide-y text-sm">{h.recent.slice(0, 8).map((r, i) => <li key={i} className="flex justify-between py-1"><span className="text-xs text-muted-foreground">{r.date?.slice(0, 10)}</span><span className="truncate px-2">{r.home} – {r.away}</span><b>{r.score}</b></li>)}</ul> : null}
          </>
        )}
      </Card>
      <Card className="p-4">
        <h3 className="mb-2 font-semibold">Clasament și motivație</h3>
        {c.standings?.home || c.standings?.away ? (
          <div className="grid grid-cols-2 gap-2 text-sm">
            {(['home', 'away'] as const).map((s) => { const r = c.standings?.[s]; return (
              <div key={s} className="rounded-lg bg-muted/40 p-2"><div className="text-xs text-muted-foreground">{m[s].name}</div>
                {r ? <div><b>Locul {r.position ?? '—'}</b> · {r.points ?? '—'} pct · {r.played ?? '—'} meciuri</div> : '—'}
                {(s === 'home' ? c.standings?.zone_home : c.standings?.zone_away) && <Badge tone="primary">{s === 'home' ? c.standings?.zone_home : c.standings?.zone_away}</Badge>}
              </div>); })}
          </div>
        ) : <p className="text-sm text-muted-foreground">Clasament indisponibil (cupă sau ligă fără tabel în date).</p>}
      </Card>
      <Card className="p-4">
        <h3 className="mb-2 font-semibold">Absențe</h3>
        <div className="grid gap-4 sm:grid-cols-2"><AbsList title={m.home.name} list={c.absences?.home} /><AbsList title={m.away.name} list={c.absences?.away} /></div>
      </Card>
    </div>
  );
}

function OddsTab({ m }: { m: Match }) {
  const keys = Object.keys(m.odds ?? {});
  if (!keys.length) return <Empty title="Fără cote publicate">Pe planul BSD Free, cotele de consens apar pentru o parte din meciuri; restul rămân „fără cotă” și nu intră în bilete.</Empty>;
  return (
    <div className="space-y-3">
      {keys.map((k) => {
        const [market, line] = k.startsWith('over_under_') ? ['over_under', Number(k.slice(11))] : [k, null];
        return (
          <Card key={k} className="p-3">
            <div className="mb-2 text-sm font-semibold">{marketTitle(k)}</div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Object.entries(m.odds![k]).map(([sel, v]) => {
                const mv = m.odds_movement?.[k]?.[sel];
                const bsd = m.bsd_probabilities?.[k]?.[sel];
                const pr = m.predictions.find((p) => marketKey(p.market, p.line) === k && p.selection === sel);
                return (
                  <div key={sel} className="rounded-lg bg-muted/40 p-2">
                    <div className="text-xs text-muted-foreground">{selectionLabel(market, line as number | null, sel)}</div>
                    <div className="flex items-center gap-1 text-lg font-bold">{fo(v)}
                      {mv?.open != null && (mv.dir === 'SHORTENING' || (mv.now ?? v) < mv.open ? <TrendingDown className="h-4 w-4 text-win" /> : (mv.now ?? v) > mv.open ? <TrendingUp className="h-4 w-4 text-loss" /> : <Minus className="h-4 w-4" />)}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      implicit {pct(1 / v)}{mv?.open != null && ` · deschidere ${fo(mv.open)}`}
                      {bsd != null && ` · BSD ${pct(bsd)}`}{pr && ` · Robot ${pct(pr.p)}`}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        );
      })}
      <p className="text-[11px] text-muted-foreground">Săgeată verde = cota scade (banii intră pe selecție). Sursa: {m.predictions.find((p) => p.odds_source)?.odds_source ?? 'consens BSD'}.</p>
    </div>
  );
}

function poisson(l: number, k: number) { let f = 1; for (let i = 2; i <= k; i++) f *= i; return Math.exp(-l) * l ** k / f; }

/** Matricea de scoruri (Poisson pe λ ale modelului) ca heatmap 0–5 × 0–5. */
function ScoreTab({ m }: { m: Match }) {
  const md = m.model;
  if (!md) return <Empty title="Matricea de scor nu e disponibilă" />;
  const lh = md.lambda_home, la = md.lambda_away;
  const N = 6;
  const grid = lh != null && la != null ? Array.from({ length: N }, (_, h) => Array.from({ length: N }, (_, a) => poisson(lh, h) * poisson(la, a))) : null;
  const mx = grid ? Math.max(...grid.flat()) : 1;
  const top = (md.top_scores ?? []).slice(0, 6);
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card className="p-4">
        <h3 className="text-sm font-semibold">Matricea scorurilor</h3>
        <p className="mb-3 text-xs text-muted-foreground">Rânduri = goluri {m.home.name}, coloane = goluri {m.away.name}. Cu cât e mai luminos, cu atât e mai probabil.</p>
        {grid ? (
          <div className="overflow-x-auto"><table className="score-grid mx-auto border-separate" style={{ borderSpacing: 4 }}>
            <thead><tr><th />{grid[0].map((_, a) => <th key={a} className="text-[11px] font-semibold text-muted-foreground">{a}</th>)}</tr></thead>
            <tbody>{grid.map((row, h) => <tr key={h}><th className="pr-1 text-[11px] font-semibold text-muted-foreground">{h}</th>{row.map((v, a) => (
              <td key={a} title={`${h}-${a}: ${(v * 100).toFixed(1)}%`} className="num h-10 w-12 rounded-lg text-center text-[11px] font-bold sm:h-11 sm:w-14"
                style={{ background: `hsl(var(--primary) / ${0.06 + 0.8 * (v / mx)})`, color: v / mx > 0.55 ? 'hsl(var(--primary-foreground))' : undefined, boxShadow: v === mx ? '0 0 18px hsl(var(--primary) / 0.6)' : undefined }}>
                {(v * 100).toFixed(v < 0.01 ? 1 : 0)}%</td>))}</tr>)}</tbody></table></div>
        ) : <p className="text-sm text-muted-foreground">Lipsesc golurile așteptate.</p>}
      </Card>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-2 text-center">
          {[['xG gazde', lh?.toFixed(2)], ['xG oaspeți', la?.toFixed(2)], ['ELO', md.elo_home ? `${Math.round(md.elo_home)}:${Math.round(md.elo_away ?? 0)}` : null], ['Scor probabil', md.most_likely_score]].map(([k, v]) => (
            <div key={k as string} className="card p-3"><div className="text-[11px] text-muted-foreground">{k}</div><div className="num text-lg font-extrabold">{v ?? '—'}</div></div>
          ))}
        </div>
        {!!top.length && <Card className="p-3"><h3 className="mb-2 text-sm font-semibold">Cele mai probabile scoruri</h3>{top.map((x) => (
          <div key={x.score} className="flex items-center gap-2 py-0.5 text-sm"><span className="num w-10 font-bold">{x.score}</span><div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-gradient-to-r from-[hsl(var(--primary))] to-[hsl(var(--primary-2))]" style={{ width: `${(x.p / top[0].p) * 100}%` }} /></div><span className="num w-12 text-right text-xs">{pct(x.p, 1)}</span></div>
        ))}</Card>}
      </div>
    </div>
  );
}

export default function MatchPage() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const minOdds = useStore((s) => s.settings.minOdds);
  const res = useAsync(() => findMatch(Number(id), sp.get('zi'), minOdds), [id, minOdds]);
  const [tab, setTab] = useState<Tab>('pred');
  if (res.loading) return <Loading />;
  if (!res.data) return <Empty title="Meciul nu a fost găsit">Poate e în afara ferestrei publicate (−3 / +7 zile). <Link className="text-primary underline" to="/predictii">Înapoi la predicții</Link></Empty>;
  const { match: m, day } = res.data;
  const grouped = new Map<string, Prediction[]>();
  for (const p of m.predictions) { const k = marketKey(p.market, p.line); grouped.set(k, [...(grouped.get(k) ?? []), p]); }
  const pick = m.predictions.find((p) => p.is_pick || p.id === m.pick_id);
  return (
    <div className="space-y-4">
      <Link to={`/predictii?zi=${day.date}`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Predicții</Link>
      <section className="match-hero relative overflow-hidden rounded-[28px] border p-4 sm:p-6">
        <div aria-hidden className="match-hero-glow" />
        <div className="relative mb-4 flex items-center justify-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground"><TeamLogo src={m.league.logo} name={m.league.name} size={16} />{m.league.name}{m.round ? ` · ${m.round}` : ''}</div>
        <div className="relative grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-center">
          <div className="flex flex-col items-center gap-2"><span className="team-orb"><TeamLogo src={m.home.logo} name={m.home.name} size={56} /></span><b className="text-sm leading-tight sm:text-lg">{m.home.name}</b>{m.model?.lambda_home != null && <span className="num text-[11px] text-muted-foreground">xG {m.model.lambda_home.toFixed(2)}</span>}</div>
          <div className="min-w-[96px]">{isFinished(m.status) && m.score?.ft ? <div className="num text-4xl font-extrabold">{m.score.ft[0]}<span className="mx-1 text-muted-foreground">:</span>{m.score.ft[1]}</div> : <div className="num text-xl font-extrabold sm:text-2xl">{roDateTime(m.kickoff_utc)}</div>}
            <div className="mt-1 inline-block rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">{statusLabel(m.status)}{m.score?.ht ? ` · pauză ${m.score.ht[0]}-${m.score.ht[1]}` : ''}</div></div>
          <div className="flex flex-col items-center gap-2"><span className="team-orb"><TeamLogo src={m.away.logo} name={m.away.name} size={56} /></span><b className="text-sm leading-tight sm:text-lg">{m.away.name}</b>{m.model?.lambda_away != null && <span className="num text-[11px] text-muted-foreground">xG {m.model.lambda_away.toFixed(2)}</span>}</div>
        </div>
        {(() => { const x = oneXTwo(m); return x ? <SplitBar className="relative mt-5" parts={x} /> : null; })()}
        {pick && (
          <div className="pick-panel relative mt-5 rounded-2xl p-3.5 text-sm">
            <div className="flex items-center gap-3">
              <ProbRing p={pick.p} size={56} label="Probabilitate Robot" />
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-primary">Pontul Robotului</div>
                <div className="mt-0.5 flex flex-wrap items-center gap-2"><b className="text-xl">{pick.label}</b><GradeBadge grade={pick.grade} />{pick.recommended && <Badge tone="win">recomandat</Badge>}</div>
              </div>
              <div className="text-right"><div className="text-[11px] text-muted-foreground">{pick.bookmaker ?? 'cotă'}</div><div className="num text-gradient-primary text-2xl font-extrabold">{fo(pick.odds)}</div>{pick.ev != null && <div className={cn('num text-[11px] font-semibold', pick.ev >= 0 ? 'text-win' : 'text-loss')}>EV {(pick.ev * 100).toFixed(1)}%</div>}</div>
            </div>
            {pick.reasons?.length ? <ul className="mt-2 space-y-0.5 border-t border-[hsl(var(--glass-border))] pt-2 text-xs text-muted-foreground">{pick.reasons.map((r) => <li key={r} className="flex gap-1.5"><span className="text-primary">›</span>{r}</li>)}</ul> : null}
          </div>
        )}
      </section>
      <Segmented value={tab} onChange={setTab} options={[{ value: 'pred', label: 'Predicții' }, { value: 'ctx', label: 'Formă · H2H · Absențe' }, { value: 'odds', label: 'Cote' }, { value: 'score', label: 'Scoruri' }, { value: 'bb', label: 'Bet Builder' }]} />
      {tab === 'pred' && (
        m.predictions.length ? (
          <div className="grid gap-3 lg:grid-cols-2">{[...grouped.entries()].sort((a, b) => marketOrder(a[0]) - marketOrder(b[0])).map(([k, ps]) => (
            <Card key={k} className="px-3.5 py-2.5"><div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_8px_hsl(var(--primary))]" />{marketTitle(k)}</div>{ps.map((p) => <PredLine key={String(p.id)} m={m} p={p} />)}</Card>
          ))}</div>
        ) : <Empty title="Fără predicții pentru acest meci" />
      )}
      {tab === 'ctx' && <ContextTab m={m} source={day._source} />}
      {tab === 'odds' && <OddsTab m={m} />}
      {tab === 'score' && <ScoreTab m={m} />}
      {tab === 'bb' && <MatchBuilderTab id={m.id} date={day.date} />}
      {day._source === 'legacy' && <Notice>Date din pipeline-ul vechi (v2). După publicarea <code>api/</code>, pagina afișează și mișcarea cotelor, ELO și clasamentul complet.</Notice>}
    </div>
  );
}

function MatchBuilderTab({ id, date }: { id: number; date: string }) {
  const res = useAsync(() => getJSON<BuilderDay>(`api/builder/${date}.json`), [date]);
  if (res.loading) return <Loading />;
  const bm = res.data?.matches?.find((x) => x.match_id === id);
  if (!bm) return <Empty title="Fără sugestii Bet Builder pentru acest meci" />;
  return <><Notice><b>Experimental.</b> {res.data?.rule}</Notice><MatchBuilder m={bm} only={false} /></>;
}
