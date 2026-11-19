import { useState } from 'react';
import { useParams, useSearchParams, Link } from 'react-router';
import { ArrowLeft, TrendingDown, TrendingUp, Minus, ShieldAlert, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';
import { useAsync, getJSON } from '@/lib/fetcher';
import { findMatch, loadMatchContext } from '@/lib/data';
import { useStore } from '@/lib/store';
import { roTime, roDay, dayLabel, odds as fo, pct } from '@/lib/format';
import { marketKey, marketTitle, marketOrder, statusLabel, selectionLabel, isFinished } from '@/lib/markets';
import { Card, Loading, Empty, Segmented, TeamLogo, Badge, Notice, ProbRing, SplitBar, GradeBadge } from '@/components/kit';
import { MatchPickNote, PredLine, oneXTwo } from '@/components/MatchCard';
import type { Match, Prediction, Form, Absence, Day } from '@/lib/types';
import { cn } from '@/lib/utils';

type Tab = 'an' | 'pred' | 'ctx' | 'odds' | 'score';

/* ---------------------------------------------------------------- analiza publicată: api/match/<id>.json */
type MarketKey = 'H2G13' | 'H2G12' | 'H1U15' | 'OVER' | 'YES' | 'HOME' | 'DRAW' | 'AWAY';
type AnMarket = {
  key: MarketKey; label: string; price: number; implied_p: number; fair_p: number | null; fair_odds: number | null;
  overround: number | null; margin: number | null; data_p: number | null; pinnacle_p: number | null; p_robot?: number;
  window: [number, number] | null; measured: { n: number; roi: number | null; days: number; off: boolean } | null;
  status: 'recommended' | 'caution' | 'avoid'; why: string[]; caution: string[]; data_note?: string;
};
type Rate = { hit: number; n: number };
type AnForm = {
  played: number; w: number; d: number; l: number; gf: number; ga: number; ppm: number | null; h1_avg: number | null; h2_avg: number | null;
  last: Array<{ date: string; opponent: string; venue: 'H' | 'A'; score: string; ht: string | null; result: 'W' | 'D' | 'L'; league?: string | null }>;
  rates: Partial<Record<MarketKey | 'WIN' | 'LOSS', Rate>>;
};
type Profile = { n: number; n_ht: number; avg_goals?: number; h1_avg?: number | null; h2_avg?: number | null; h2_share?: number | null; rates?: Partial<Record<MarketKey, number>> };
type MatchAnalysis = {
  schema: string; generated_at: string; verdict: string; note: string;
  match: { id: number; kickoff_utc: string; day: string | null; home: string; away: string; league: string | null; intl: boolean; night: boolean };
  markets: AnMarket[]; form: { home: AnForm; away: AnForm };
  h2h: { n: number; home_wins: number; draws: number; away_wins: number; avg_goals: number | null; over15: number; btts: number; recent: Array<{ date: string; home: string; away: string; score: string; ht: string | null }> };
  league_profile: Profile & { days: number; all: Profile };
  risk: Array<{ code: string; level: 'high' | 'medium' | 'low'; text: string }>;
};

const ST = {
  recommended: { t: 'Recomandat', tone: 'win' as const, Icon: CheckCircle2 },
  caution: { t: 'Cu atenție', tone: 'warn' as const, Icon: AlertTriangle },
  avoid: { t: 'Evitat', tone: 'muted' as const, Icon: XCircle },
};
const RES = { W: ['V', 'bg-win text-win'], D: ['E', 'bg-warn text-warn'], L: ['Î', 'bg-loss text-loss'] } as const;
const PROFILE_ROWS: Array<[MarketKey, string]> = [['H2G13', 'Repriza 2: 1–3 goluri'], ['H2G12', 'Repriza 2: 1–2 goluri'], ['H1U15', 'Repriza 1: sub 1.5'], ['OVER', 'Peste 1.5 goluri'], ['YES', 'GG']];
const shortDate = (d: string) => d.slice(5).split('-').reverse().join('.');

function MarketRow({ m }: { m: AnMarket }) {
  const s = ST[m.status];
  return (
    <div className="py-3 first:pt-1 last:pb-1">
      <div className="flex items-start gap-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5"><b className="text-[15px] leading-tight">{m.label}</b><Badge tone={s.tone}><s.Icon className="h-3 w-3" />{s.t}</Badge></div>
        <span className="num shrink-0 rounded-xl border bg-card px-2.5 py-1 text-base font-extrabold">{fo(m.price)}</span>
      </div>
      <dl className="mt-2 grid grid-cols-3 gap-1.5 text-center">
        <div className="rounded-lg bg-muted/40 px-1 py-1.5"><dt className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Șansă corectă</dt><dd className="num text-sm font-extrabold">{pct(m.fair_p)}</dd><dd className="num text-[10px] text-muted-foreground">cotă corectă {fo(m.fair_odds)}</dd></div>
        <div className="rounded-lg bg-muted/40 px-1 py-1.5"><dt className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Marja pieței</dt><dd className={cn('num text-sm font-extrabold', (m.overround ?? 0) >= 0.08 && 'text-warn')}>{m.overround != null ? `${(m.overround * 100).toFixed(1)}%` : '—'}</dd><dd className="num text-[10px] text-muted-foreground">{m.margin != null ? `costul tău ${(m.margin * 100).toFixed(1)}%` : '—'}</dd></div>
        <div className="rounded-lg bg-muted/40 px-1 py-1.5"><dt className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Istoric</dt><dd className="num text-sm font-extrabold">{pct(m.data_p)}</dd><dd className="num text-[10px] text-muted-foreground">liga + echipe</dd></div>
      </dl>
      {m.fair_p != null && (
        <div className="mt-2" aria-label={`Cota cere ${pct(m.implied_p)}, șansa corectă ${pct(m.fair_p)}`}>
          <div className="relative h-1.5 overflow-hidden rounded-full bg-muted">
            <div className="absolute inset-y-0 left-0 rounded-full bg-primary/80" style={{ width: `${Math.min(100, m.fair_p * 100)}%` }} />
            <div className="absolute inset-y-0 w-0.5 bg-foreground" style={{ left: `${Math.min(99.5, m.implied_p * 100)}%` }} />
          </div>
          <div className="mt-0.5 flex justify-between gap-2 text-[10px] text-muted-foreground"><span>bara = șansa corectă</span><span>linia = cât cere cota ({pct(m.implied_p)})</span></div>
        </div>
      )}
      <ul className="mt-2 space-y-0.5 text-xs leading-snug text-muted-foreground">{m.why.map((w) => <li key={w}>{w}</li>)}</ul>
      {m.caution.length > 0 && <ul className="mt-1 space-y-0.5 text-xs font-semibold leading-snug text-warn">{m.caution.map((w) => <li key={w}>{w}</li>)}</ul>}
      {(m.window || m.measured || m.pinnacle_p != null) && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {m.window && <Badge tone="outline">fereastră {m.window[0].toFixed(2)}–{m.window[1].toFixed(2)}</Badge>}
          {m.measured && m.measured.roi != null && m.measured.n >= 30 && <Badge tone={m.measured.off ? 'loss' : 'outline'}>{m.measured.days} zile: {m.measured.roi >= 0 ? '+' : ''}{Math.round(m.measured.roi * 100)}% pe {m.measured.n}</Badge>}
          {m.pinnacle_p != null && <Badge tone="outline">Pinnacle {pct(m.pinnacle_p)}</Badge>}
        </div>
      )}
      {m.data_note && <p className="mt-1 text-[11px] italic leading-snug text-muted-foreground">{m.data_note}</p>}
    </div>
  );
}

function TeamForm({ name, f }: { name: string; f: AnForm }) {
  return (
    <div className="rounded-xl bg-muted/40 p-3">
      <div className="flex items-center justify-between gap-2"><b className="min-w-0 truncate text-sm">{name}</b>
        <div className="flex shrink-0 gap-1" aria-label="Ultimele rezultate, cel mai recent primul">{f.last.map((r, i) => <span key={i} title={`${r.date} · ${r.venue === 'H' ? 'acasă' : 'deplasare'} · ${r.opponent} ${r.score}`} className={cn('flex h-6 w-6 items-center justify-center rounded text-[11px] font-bold', RES[r.result][1])}>{RES[r.result][0]}</span>)}</div>
      </div>
      {f.played ? (
        <>
          <div className="mt-2 grid grid-cols-4 gap-1 text-center text-[11px]">
            <div><div className="text-muted-foreground">V-E-Î</div><b className="num">{f.w}-{f.d}-{f.l}</b></div>
            <div><div className="text-muted-foreground">Goluri</div><b className="num">{f.gf}:{f.ga}</b></div>
            <div><div className="text-muted-foreground">Pct/meci</div><b className="num">{f.ppm?.toFixed(2) ?? '—'}</b></div>
            <div><div className="text-muted-foreground">R1 / R2</div><b className="num">{f.h1_avg?.toFixed(1) ?? '—'} / {f.h2_avg?.toFixed(1) ?? '—'}</b></div>
          </div>
          <ul className="mt-2 divide-y divide-border/60 text-xs">{f.last.map((r, i) => (
            <li key={i} className="flex items-center gap-2 py-1"><span className="num w-10 shrink-0 text-muted-foreground">{shortDate(r.date)}</span>
              <span className="w-3 shrink-0 text-center text-[10px] font-bold text-muted-foreground" title={r.venue === 'H' ? 'acasă' : 'deplasare'}>{r.venue === 'H' ? 'A' : 'D'}</span>
              <span className="min-w-0 flex-1 truncate">{r.opponent}</span><b className="num shrink-0">{r.score}</b>{r.ht && <span className="num w-9 shrink-0 text-right text-muted-foreground">({r.ht})</span>}</li>
          ))}</ul>
        </>
      ) : <p className="mt-2 text-xs text-muted-foreground">Fără meciuri terminate în date.</p>}
    </div>
  );
}

function AnalysisPanel({ a }: { a: MatchAnalysis }) {
  const shown = a.markets.filter((m) => m.status !== 'avoid');
  const avoided = a.markets.filter((m) => m.status === 'avoid');
  const lp = a.league_profile;
  const h = a.h2h;
  const nForm = Math.max(a.form.home.last.length, a.form.away.last.length);
  return (
    <div className="space-y-3">
      <Card className="p-4">
        <div className="label mb-1">Verdictul analistului</div>
        <p className="text-[15px] font-bold leading-snug">{a.verdict}</p>
        {a.risk.length > 0 && (
          <ul className="mt-3 space-y-1.5" aria-label="Riscuri">{a.risk.map((r) => (
            <li key={r.code} className={cn('flex gap-2 rounded-lg px-2.5 py-2 text-xs leading-snug', r.level === 'high' ? 'bg-loss text-loss' : r.level === 'medium' ? 'bg-warn text-warn' : 'bg-muted/50 text-muted-foreground')}>
              <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{r.text}</span></li>
          ))}</ul>
        )}
      </Card>
      <Card className="px-3.5 py-3">
        <h3 className="font-semibold">Preț Superbet vs șansa corectă</h3>
        <p className="mb-1 text-[11px] leading-snug text-muted-foreground">Șansa corectă = prețurile Superbet fără marjă. Marja e reală: „costul tău” e cât pierzi în medie la prețul corect.</p>
        {shown.length ? <div className="divide-y">{shown.map((m) => <MarketRow key={m.key} m={m} />)}</div> : <p className="py-2 text-sm text-muted-foreground">Nicio piață nu trece filtrele Robotului pe acest meci.</p>}
        {avoided.length > 0 && (
          <details className="mt-1 border-t pt-1">
            <summary className="flex min-h-[44px] cursor-pointer items-center text-sm font-bold text-primary">Evitate ({avoided.length}) · de ce nu</summary>
            <div className="divide-y">{avoided.map((m) => <MarketRow key={m.key} m={m} />)}</div>
          </details>
        )}
      </Card>
      <Card className="p-3.5">
        <h3 className="mb-2 font-semibold">Forma{nForm ? ` (ultimele ${nForm} meciuri)` : ''}</h3>
        <div className="grid gap-2 sm:grid-cols-2"><TeamForm name={a.match.home} f={a.form.home} /><TeamForm name={a.match.away} f={a.form.away} /></div>
        <p className="mt-1.5 text-[11px] text-muted-foreground">A = acasă, D = deplasare. Scorul e din perspectiva echipei (date–primite), în paranteză la pauză. R1 / R2 = goluri pe repriză în ultimele 10 meciuri.</p>
      </Card>
      <Card className="p-3.5">
        <h3 className="mb-2 font-semibold">Meciuri directe</h3>
        {!h.n ? <p className="text-sm text-muted-foreground">Nu s-au mai întâlnit în ultimii ani (în date).</p> : (
          <>
            <SplitBar parts={[{ label: 'Gazde', p: h.home_wins, tone: 'home' }, { label: 'Egal', p: h.draws, tone: 'draw' }, { label: 'Oaspeți', p: h.away_wins, tone: 'away' }]} />
            <div className="mt-1 text-xs text-muted-foreground">{h.n} meciuri · {h.avg_goals?.toFixed(1) ?? '—'} goluri/meci · peste 1.5: {h.over15}/{h.n} · GG: {h.btts}/{h.n}</div>
            <ul className="mt-2 divide-y text-xs">{h.recent.map((r, i) => (
              <li key={i} className="flex items-center gap-2 py-1"><span className="num w-[4.6rem] shrink-0 text-muted-foreground">{r.date.split('-').reverse().join('.')}</span><span className="min-w-0 flex-1 truncate">{r.home} – {r.away}</span><b className="num shrink-0">{r.score}</b>{r.ht && <span className="num shrink-0 text-muted-foreground">({r.ht})</span>}</li>
            ))}</ul>
          </>
        )}
      </Card>
      <Card className="p-3.5">
        <h3 className="font-semibold">Profilul ligii pe reprize</h3>
        <p className="mb-2 text-[11px] text-muted-foreground">{a.match.league ?? 'Liga'} · ultimele {lp.days} de zile · {lp.n_ht} meciuri cu scor la pauză{lp.n_ht < 60 ? ' (puține: procentele sunt trase spre media generală)' : ''}</p>
        {lp.h1_avg != null && lp.h2_avg != null && (
          <div className="mb-3">
            <div className="flex h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-[hsl(var(--info))]" style={{ width: `${(1 - (lp.h2_share ?? 0.5)) * 100}%` }} /><div className="h-full bg-primary" style={{ width: `${(lp.h2_share ?? 0.5) * 100}%` }} /></div>
            <div className="mt-1 flex justify-between text-[11px] tabular-nums text-muted-foreground"><span><b className="text-foreground">R1</b> {lp.h1_avg.toFixed(2)}</span><span>{lp.avg_goals?.toFixed(2)} goluri / meci</span><span><b className="text-foreground">R2</b> {lp.h2_avg.toFixed(2)}</span></div>
          </div>
        )}
        <table className="w-full text-sm">
          <thead><tr className="text-[10px] uppercase tracking-wide text-muted-foreground"><th className="py-1 text-left font-bold">Piață</th><th className="text-right font-bold">Liga</th><th className="text-right font-bold">Toate ligile</th></tr></thead>
          <tbody className="divide-y">{PROFILE_ROWS.map(([k, label]) => {
            const v = lp.rates?.[k], g = lp.all?.rates?.[k];
            return <tr key={k}><td className="py-1.5">{label}</td><td className={cn('num text-right font-bold', v != null && g != null && (v - g >= 0.03 ? 'text-win' : g - v >= 0.03 ? 'text-loss' : ''))}>{pct(v)}</td><td className="num text-right text-muted-foreground">{pct(g)}</td></tr>;
          })}</tbody>
        </table>
      </Card>
      <p className="px-1 text-[11px] leading-snug text-muted-foreground">{a.note} Generată {new Date(a.generated_at).toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest', dateStyle: 'short', timeStyle: 'short' })}.</p>
    </div>
  );
}

/** Pagina meciului când ziua nu (mai) e publicată, dar analiza există. */
function AnalysisOnly({ a }: { a: MatchAnalysis }) {
  return (
    <div className="space-y-4">
      <Link to="/predictii" className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Predicții</Link>
      <section className="match-hero relative overflow-hidden rounded-[28px] border p-4">
        <div className="relative mb-3 text-center text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{a.match.league}</div>
        <div className="relative grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-center">
          <b className="break-words text-[15px] font-extrabold leading-tight">{a.match.home}</b>
          <div><div className="num text-3xl font-extrabold leading-none">{roTime(a.match.kickoff_utc)}</div><div className="mt-1 text-xs font-semibold text-muted-foreground">{dayLabel(roDay(a.match.kickoff_utc))}</div></div>
          <b className="break-words text-[15px] font-extrabold leading-tight">{a.match.away}</b>
        </div>
      </section>
      <AnalysisPanel a={a} />
    </div>
  );
}

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
            {h.recent?.length ? <ul className="mt-2 divide-y text-sm">{h.recent.slice(0, 8).map((r, i) => <li key={i} className="flex justify-between py-1"><span className="text-xs text-muted-foreground">{r.date?.slice(0, 10)}</span><span className="min-w-0 flex-1 break-words px-2 text-center">{r.home} – {r.away}</span><b>{r.score}</b></li>)}</ul> : null}
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
  const an = useAsync(() => getJSON<MatchAnalysis>(`api/match/${Number(id)}.json`).then((d) => (d?.markets ? d : null)), [id]);
  const [picked, setTab] = useState<Tab | null>(null);
  if (res.loading || an.loading) return <Loading />;
  const tab: Tab = picked ?? (an.data ? 'an' : 'pred');
  if (!res.data && an.data) return <AnalysisOnly a={an.data} />;
  if (!res.data) return <Empty title="Meciul nu a fost găsit">Poate e în afara ferestrei publicate (−3 / +7 zile). <Link className="text-primary underline" to="/bilete">Înapoi la bilete</Link></Empty>;
  const { match: m, day } = res.data;
  const grouped = new Map<string, Prediction[]>();
  for (const p of m.predictions) { const k = marketKey(p.market, p.line); grouped.set(k, [...(grouped.get(k) ?? []), p]); }
  const sorted = [...grouped.entries()].sort((a, b) => marketOrder(a[0]) - marketOrder(b[0]));
  const CORE = ['1x2', 'double_chance', 'draw_no_bet', 'over_under', 'btts'];
  const core = sorted.filter(([, ps]) => CORE.includes(ps[0].market));
  const rest = sorted.filter(([, ps]) => !CORE.includes(ps[0].market));
  const pick = m.predictions.find((p) => p.is_pick || p.id === m.pick_id);
  return (
    <div className="space-y-4">
      <Link to="/bilete" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Bilete</Link>
      <section className="match-hero relative overflow-hidden rounded-[28px] border p-4 sm:p-6">
        <div aria-hidden className="match-hero-glow" />
        <div className="relative mb-4 flex items-center justify-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground"><TeamLogo src={m.league.logo} name={m.league.name} size={16} /><span className="break-words text-center">{m.league.name}{m.round && !/regular season/i.test(m.round) ? ` · ${m.round}` : ''}</span></div>
        <div className="relative grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-center">
          <div className="flex flex-col items-center gap-2"><span className="team-orb"><TeamLogo src={m.home.logo} name={m.home.name} size={56} /></span><b className="break-words text-[15px] font-extrabold leading-tight">{m.home.name}</b>{m.model?.lambda_home != null && <span className="num text-[11px] text-muted-foreground">xG {m.model.lambda_home.toFixed(2)}</span>}</div>
          <div className="min-w-[96px]">{isFinished(m.status) && m.score?.ft ? <div className="num text-4xl font-extrabold">{m.score.ft[0]}<span className="mx-1 text-muted-foreground">:</span>{m.score.ft[1]}</div> : <div><div className="num text-3xl font-extrabold leading-none">{roTime(m.kickoff_utc)}</div><div className="mt-1 text-xs font-semibold text-muted-foreground">{dayLabel(roDay(m.kickoff_utc))}</div></div>}
            <div className="mt-1 inline-block rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">{statusLabel(m.status)}{m.score?.ht ? ` · pauză ${m.score.ht[0]}-${m.score.ht[1]}` : ''}</div></div>
          <div className="flex flex-col items-center gap-2"><span className="team-orb"><TeamLogo src={m.away.logo} name={m.away.name} size={56} /></span><b className="break-words text-[15px] font-extrabold leading-tight">{m.away.name}</b>{m.model?.lambda_away != null && <span className="num text-[11px] text-muted-foreground">xG {m.model.lambda_away.toFixed(2)}</span>}</div>
        </div>
        {(() => { const x = oneXTwo(m); return x ? <SplitBar className="relative mt-5" parts={x} /> : null; })()}
        <GoalsStrip m={m} />
        <MatchPickNote m={m} pick={m.market_pick} />
        {pick && (
          <div className="pick-panel relative mt-5 rounded-2xl p-3.5 text-sm">
            <div className="flex items-center gap-3">
              <ProbRing p={pick.p} size={56} label="Probabilitate Robot" />
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-primary">Pontul Robotului</div>
                <div className="mt-0.5 flex flex-wrap items-center gap-2"><b className="text-xl">{pick.label}</b><GradeBadge grade={pick.grade} />{pick.recommended && <Badge tone="win">recomandat</Badge>}</div>
              </div>
              <div className="slip-odds shrink-0 rounded-2xl px-3 py-2 text-center">
                <div className="text-[10px] font-extrabold uppercase tracking-wider text-primary-foreground/75">Cotă</div>
                <div className="num text-[28px] font-extrabold leading-none text-primary-foreground">{fo(pick.odds)}</div>
                {pick.ev != null && <div className="num text-[11px] font-bold text-primary-foreground/80">EV {(pick.ev * 100).toFixed(1)}%</div>}
              </div>
            </div>
            {pick.reasons?.length ? (
              <details className="mt-2 border-t border-[hsl(var(--glass-border))] pt-1.5">
                <summary className="cursor-pointer text-xs font-semibold text-primary">De ce</summary>
                <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">{pick.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              </details>
            ) : null}
          </div>
        )}
      </section>
      <Segmented size="sm" className="w-full" value={tab} onChange={setTab} options={[...(an.data ? [{ value: 'an' as Tab, label: 'Analiză' }] : []), { value: 'pred' as Tab, label: 'Ponturi' }, { value: 'ctx' as Tab, label: 'Formă' }, { value: 'odds' as Tab, label: 'Cote' }, { value: 'score' as Tab, label: 'Scor' }]} />
      {tab === 'an' && an.data && <AnalysisPanel a={an.data} />}
      {tab === 'pred' && (
        m.predictions.length ? (
          <>
          <div className="grid gap-3 lg:grid-cols-2">{core.map(([k, ps]) => (
            <Card key={k} className="px-3.5 py-2.5"><div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_8px_hsl(var(--primary))]" />{marketTitle(k)}</div>{ps.map((p) => <PredLine key={String(p.id)} m={m} p={p} cmp />)}</Card>
          ))}</div>
          {rest.length > 0 && (
            <details className="card px-3.5 py-2.5">
              <summary className="flex min-h-[40px] cursor-pointer items-center text-sm font-bold text-primary">Alte piețe ({rest.reduce((a, [, ps]) => a + ps.length, 0)}) · reprize, handicap, cornere</summary>
              <div className="mt-1 divide-y">{rest.map(([k, ps]) => (
                <div key={k} className="py-1.5"><div className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground">{marketTitle(k)}</div>{ps.map((p) => <PredLine key={String(p.id)} m={m} p={p} cmp />)}</div>
              ))}</div>
            </details>
          )}
          </>
        ) : <Empty title="Fără predicții pentru acest meci">Robotul publică predicții doar când are destule date (formă, cote). Revino mai aproape de start.</Empty>
      )}
      {tab === 'ctx' && <ContextTab m={m} source={day._source} />}
      {tab === 'odds' && <OddsTab m={m} />}
      {tab === 'score' && <ScoreTab m={m} />}
      {day._source === 'legacy' && <Notice>Date din pipeline-ul vechi (v2). După publicarea <code>api/</code>, pagina afișează și mișcarea cotelor, ELO și clasamentul complet.</Notice>}
    </div>
  );
}

/** Goluri dintr-o privire: Peste 1.5 / Peste 2.5 / GG (probabilitatea Robotului). */
function GoalsStrip({ m }: { m: Match }) {
  const find = (mk: string, sel: string, line?: number) => m.predictions.find((p) => p.market === mk && p.selection.toUpperCase() === sel && (line == null || Number(p.line) === line))?.p;
  const items = [
    { k: 'Peste 1.5', p: find('over_under', 'OVER', 1.5) },
    { k: 'Peste 2.5', p: find('over_under', 'OVER', 2.5) },
    { k: 'GG', p: find('btts', 'YES') },
  ].filter((x) => x.p != null) as Array<{ k: string; p: number }>;
  if (!items.length) return null;
  return (
    <div className="relative mt-4 grid grid-cols-3 gap-2" aria-label="Goluri">
      {items.map((x) => (
        <div key={x.k} className="rounded-xl bg-[hsl(var(--elevated))] px-2 py-2 text-center">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{x.k}</div>
          <div className="num text-lg font-extrabold">{pct(x.p)}</div>
          <div className="mx-auto mt-1 h-1 w-full overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${Math.round(x.p * 100)}%` }} /></div>
        </div>
      ))}
    </div>
  );
}
