import { useState } from 'react';
import { useParams, useSearchParams, Link } from 'react-router';
import { ArrowLeft, TrendingDown, TrendingUp, Minus } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { findMatch, loadMatchContext } from '@/lib/data';
import { useStore } from '@/lib/store';
import { roDateTime, odds as fo, pct } from '@/lib/format';
import { marketKey, marketTitle, marketOrder, statusLabel, selectionLabel } from '@/lib/markets';
import { Card, Loading, Empty, Segmented, TeamLogo, Badge, Notice } from '@/components/kit';
import { PredLine } from '@/components/MatchCard';
import type { Match, Prediction, Form, Absence, Day } from '@/lib/types';
import { cn } from '@/lib/utils';

type Tab = 'pred' | 'ctx' | 'odds' | 'score';

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
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-muted/40 p-2"><div className="text-xl font-bold">{h.home_wins ?? 0}</div><div className="text-[11px] text-muted-foreground">{m.home.name}</div></div>
              <div className="rounded-lg bg-muted/40 p-2"><div className="text-xl font-bold">{h.draws ?? 0}</div><div className="text-[11px] text-muted-foreground">Egaluri</div></div>
              <div className="rounded-lg bg-muted/40 p-2"><div className="text-xl font-bold">{h.away_wins ?? 0}</div><div className="text-[11px] text-muted-foreground">{m.away.name}</div></div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span>{h.total} meciuri</span>{h.avg_goals != null && <span>· {h.avg_goals.toFixed(2)} goluri/meci</span>}
              {h.over25_rate != null && <span>· peste 2.5: {pct(h.over25_rate)}</span>}{h.btts_rate != null && <span>· GG: {pct(h.btts_rate)}</span>}
            </div>
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

function ScoreTab({ m }: { m: Match }) {
  const md = m.model;
  if (!md) return <Empty title="Matricea de scor nu e disponibilă" />;
  const max = Math.max(...(md.top_scores ?? []).map((s) => s.p), 0.01);
  return (
    <Card className="p-4">
      <div className="mb-3 grid grid-cols-2 gap-2 text-center text-sm sm:grid-cols-4">
        <div className="rounded-lg bg-muted/40 p-2"><div className="text-[11px] text-muted-foreground">Goluri așteptate gazde</div><b>{md.lambda_home?.toFixed(2) ?? '—'}</b></div>
        <div className="rounded-lg bg-muted/40 p-2"><div className="text-[11px] text-muted-foreground">Goluri așteptate oaspeți</div><b>{md.lambda_away?.toFixed(2) ?? '—'}</b></div>
        <div className="rounded-lg bg-muted/40 p-2"><div className="text-[11px] text-muted-foreground">ELO</div><b>{md.elo_home ? `${Math.round(md.elo_home)} : ${Math.round(md.elo_away ?? 0)}` : '—'}</b></div>
        <div className="rounded-lg bg-muted/40 p-2"><div className="text-[11px] text-muted-foreground">Scor probabil</div><b>{md.most_likely_score ?? '—'}</b></div>
      </div>
      <div className="space-y-1">{(md.top_scores ?? []).slice(0, 10).map((s) => (
        <div key={s.score} className="flex items-center gap-2 text-sm"><span className="w-10 font-semibold">{s.score}</span>
          <div className="h-2 flex-1 rounded bg-muted"><div className="h-2 rounded bg-primary" style={{ width: `${(s.p / max) * 100}%` }} /></div><span className="w-12 text-right text-xs">{pct(s.p, 1)}</span></div>
      ))}</div>
    </Card>
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
      <Card className="p-4">
        <div className="mb-3 flex items-center justify-center gap-2 text-xs text-muted-foreground"><TeamLogo src={m.league.logo} name={m.league.name} size={16} />{m.league.name}{m.round ? ` · ${m.round}` : ''}</div>
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-center">
          <div className="flex flex-col items-center gap-1"><TeamLogo src={m.home.logo} name={m.home.name} size={48} /><b className="text-sm sm:text-base">{m.home.name}</b></div>
          <div>{m.score?.ft ? <div className="text-3xl font-extrabold tabular-nums">{m.score.ft[0]} : {m.score.ft[1]}</div> : <div className="text-lg font-bold">{roDateTime(m.kickoff_utc)}</div>}
            <div className="text-xs text-muted-foreground">{statusLabel(m.status)}{m.score?.ht ? ` · pauză ${m.score.ht[0]}-${m.score.ht[1]}` : ''}</div></div>
          <div className="flex flex-col items-center gap-1"><TeamLogo src={m.away.logo} name={m.away.name} size={48} /><b className="text-sm sm:text-base">{m.away.name}</b></div>
        </div>
        {pick && (
          <div className="mt-4 rounded-lg border border-primary/30 bg-primary/10 p-3 text-sm">
            <div className="text-xs font-semibold uppercase text-primary">Predicția principală a Robotului</div>
            <div className="mt-1 flex flex-wrap items-center gap-2"><b className="text-base">{pick.label}</b><span>prob. {pct(pick.p)}</span><span>cotă {fo(pick.odds)}</span>{pick.grade && <Badge tone="primary">grad {pick.grade}</Badge>}</div>
            {pick.reasons?.length ? <ul className="mt-1 list-disc pl-4 text-xs text-muted-foreground">{pick.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : null}
          </div>
        )}
      </Card>
      <Segmented value={tab} onChange={setTab} options={[{ value: 'pred', label: 'Predicții' }, { value: 'ctx', label: 'Formă · H2H · Absențe' }, { value: 'odds', label: 'Cote' }, { value: 'score', label: 'Scoruri' }]} />
      {tab === 'pred' && (
        m.predictions.length ? (
          <div className="space-y-3">{[...grouped.entries()].sort((a, b) => marketOrder(a[0]) - marketOrder(b[0])).map(([k, ps]) => (
            <Card key={k} className="px-3 py-2"><div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{marketTitle(k)}</div>{ps.map((p) => <PredLine key={String(p.id)} m={m} p={p} />)}</Card>
          ))}</div>
        ) : <Empty title="Fără predicții pentru acest meci" />
      )}
      {tab === 'ctx' && <ContextTab m={m} source={day._source} />}
      {tab === 'odds' && <OddsTab m={m} />}
      {tab === 'score' && <ScoreTab m={m} />}
      {day._source === 'legacy' && <Notice>Date din pipeline-ul vechi (v2). După publicarea <code>api/</code>, pagina afișează și mișcarea cotelor, ELO și clasamentul complet.</Notice>}
    </div>
  );
}
