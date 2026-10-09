import { useCallback, useState } from 'react';
import { Link } from 'react-router';
import { Plus, Check, ChevronRight, Star } from 'lucide-react';
import type { Match, Prediction } from '@/lib/types';
import { odds as fo, pct, roTime, roDay } from '@/lib/format';
import { isFinished, isLive, marketKey, marketTitle, marketOrder, pickHint } from '@/lib/markets';
import { ConfidenceChip, InfoTip, ProbBar, ResultBadge, TeamLogo, Sheet, SafetyMeter } from './kit';
import { useStore, actions } from '@/lib/store';
import { cn } from '@/lib/utils';
import { isRecommended } from '@/lib/rules';
import { HELP, valueInfo } from '@/lib/ui';
import type { TicketLeg } from '@/lib/types';

export function oneXTwo(m: Match) {
  const g = (s: string) => m.predictions.find((p) => p.market === '1x2' && p.selection === s)?.p;
  const h = g('HOME'), d = g('DRAW'), a = g('AWAY');
  if (h == null || d == null || a == null) return null;
  return [{ label: '1', p: h, tone: 'home' as const }, { label: 'X', p: d, tone: 'draw' as const }, { label: '2', p: a, tone: 'away' as const }];
}

export function toLeg(m: Match, p: Prediction): TicketLeg {
  return {
    prediction_id: p.id, match_id: m.id, kickoff_utc: m.kickoff_utc, league: m.league.name, home: m.home.name, away: m.away.name,
    market: p.market, line: p.line, selection: p.selection, label: p.label, odds: p.odds ?? 0, p: p.p, p_market: p.p_market ?? null, grade: p.grade ?? null, result: null,
    reasons: p.reasons,
  };
}

/** Buton de cotă (ca la casele de pariuri): atinge pentru a adăuga/scoate selecția de pe bilet. */
export function OddsButton({ m, p, className }: { m: Match; p: Prediction; className?: string }) {
  const inSlip = useStore((s) => s.slip.some((l) => l.match_id === m.id && l.market === p.market && l.line === p.line && l.selection === p.selection));
  const disabled = p.odds == null || m.status !== 'notstarted';
  return (
    <button type="button" disabled={disabled} aria-pressed={inSlip}
      aria-label={p.odds == null ? `${p.label}: fără cotă` : `${inSlip ? 'Scoate de pe bilet' : 'Adaugă pe bilet'}: ${p.label}, cotă ${fo(p.odds)}`}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); actions.toggleSlip(toLeg(m, p)); }}
      className={cn('odds-btn', inSlip && 'odds-btn-on', className)}>
      <span className="text-[15px] font-bold tabular-nums">{p.odds == null ? '—' : fo(p.odds)}</span>
      <span className={cn('mt-0.5 flex items-center gap-0.5 text-[10px] font-medium', inSlip ? 'text-primary-foreground/90' : 'text-muted-foreground')}>
        {p.odds == null ? 'fără cotă' : inSlip ? <><Check className="h-3 w-3" />pe bilet</> : <><Plus className="h-3 w-3" />bilet</>}
      </span>
    </button>
  );
}
/** Compatibilitate: vechiul buton „+”. */
export const AddButton = OddsButton;

function timeOrStatus(m: Match) {
  if (isFinished(m.status)) return 'Final';
  if (isLive(m.status)) return 'Început';
  if (m.status && m.status !== 'notstarted') return 'Amânat';
  return roTime(m.kickoff_utc);
}

/** Rând compact: selecția + șansa + cota. Fără jargon; detaliile sunt în pagina meciului. */
export function PredLine({ m, p, showMatch }: { m: Match; p: Prediction; showMatch?: boolean }) {
  const rec = isRecommended(p);
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        {showMatch && (
          <Link to={`/meci/${m.id}?zi=${roDay(m.kickoff_utc)}`} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
            <span className="font-semibold tabular-nums text-foreground/80">{timeOrStatus(m)}</span>
            <span className="truncate">{m.home.name} – {m.away.name}</span>
          </Link>
        )}
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-[15px] font-bold">{p.label}</span>
          {rec && <Star className="h-3.5 w-3.5 fill-current text-primary" aria-label="Recomandat" />}
          <ConfidenceChip grade={p.grade} compact />
          {p.result && <ResultBadge r={p.result} />}
        </div>
        <div className="mt-1.5 flex items-center gap-2">
          <ProbBar p={p.p} className="h-1 max-w-[120px]" />
          <span className="text-xs tabular-nums text-muted-foreground"><b className="text-foreground">{pct(p.p)}</b> șansă</span>
          <SafetyMeter p={p} />
        </div>
      </div>
      <OddsButton m={m} p={p} />
    </div>
  );
}

/** Toate piețele meciului, grupate, într-un panou separat (nu mai lungesc cardul). */
export function MarketsSheet({ m, open, onClose }: { m: Match; open: boolean; onClose: () => void }) {
  const grouped = new Map<string, Prediction[]>();
  for (const p of m.predictions) { const k = marketKey(p.market, p.line); grouped.set(k, [...(grouped.get(k) ?? []), p]); }
  return (
    <Sheet open={open} onClose={onClose} title={`${m.home.name} – ${m.away.name}`} subtitle={`${m.league.name} · ${timeOrStatus(m)} · ${m.predictions.length} selecții analizate`}>
      <div className="space-y-3">
        {[...grouped.entries()].sort((a, b) => marketOrder(a[0]) - marketOrder(b[0])).map(([k, ps]) => (
          <section key={k} className="rounded-2xl border bg-[hsl(var(--elevated))] px-3">
            <h3 className="eyebrow pt-2.5">{marketTitle(k)}</h3>
            <div className="divide-y">{ps.map((p) => <PredLine key={String(p.id)} m={m} p={p} />)}</div>
          </section>
        ))}
        <Link to={`/meci/${m.id}?zi=${roDay(m.kickoff_utc)}`} className="btn btn-outline w-full" onClick={onClose}>Analiza completă a meciului<ChevronRight className="h-4 w-4" /></Link>
      </div>
    </Sheet>
  );
}

function TeamRow({ name, logo, score, bold }: { name: string; logo?: string | null; score?: number | null; bold?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <TeamLogo src={logo} name={name} size={24} />
      <span className={cn('min-w-0 flex-1 truncate text-[16px] leading-tight', bold ? 'font-bold' : 'font-semibold')}>{name}</span>
      {score != null && <span className="w-6 text-right text-lg font-extrabold tabular-nums">{score}</span>}
    </div>
  );
}

/** Card de meci: echipe + oră mari, UN singur pont evidențiat, restul piețelor într-un panou. */
export function MatchCard({ m, focus }: { m: Match; focus: Prediction[] }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const main = focus[0] ?? m.predictions.find(isRecommended) ?? m.predictions.find((p) => p.is_pick) ?? m.predictions[0];
  const done = isFinished(m.status);
  const ft = done ? m.score?.ft : null;
  const v = main ? valueInfo(main.ev) : null;
  const rec = main ? isRecommended(main) : false;
  return (
    <article className="card card-hover overflow-hidden">
      <Link to={`/meci/${m.id}?zi=${roDay(m.kickoff_utc)}`} className="block px-4 pb-3 pt-3.5">
        <div className="mb-2.5 flex items-center gap-2 text-xs text-muted-foreground">
          <TeamLogo src={m.league.logo} name={m.league.name} size={16} />
          <span className="min-w-0 flex-1 truncate">{m.league.country ? `${m.league.country} · ` : ''}{m.league.name}</span>
          <span className={cn('rounded-full px-2 py-0.5 text-[13px] font-bold tabular-nums', done ? 'bg-muted text-muted-foreground' : 'bg-[hsl(var(--elevated))] text-foreground')}>{timeOrStatus(m)}</span>
        </div>
        <div className="space-y-2">
          <TeamRow name={m.home.name} logo={m.home.logo} score={ft?.[0]} bold={!!ft && ft[0] > ft[1]} />
          <TeamRow name={m.away.name} logo={m.away.logo} score={ft?.[1]} bold={!!ft && ft[1] > ft[0]} />
        </div>
      </Link>
      {main ? (
        <div className="px-3 pb-3">
          <div className="pick-panel flex items-center gap-3 p-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-primary">{rec && <Star className="h-3 w-3 fill-current" aria-hidden />}{rec ? 'Recomandat' : 'Pontul Robotului'}</div>
              <div className="mt-0.5 flex flex-wrap items-center gap-2"><span className="text-lg font-extrabold leading-tight">{main.label}</span><ConfidenceChip grade={main.grade} /></div>
              <div className="mt-0.5 truncate text-xs text-muted-foreground">{pickHint(main.market, main.line, main.selection, m.home.name, m.away.name)}</div>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>Șansă <b className="text-sm text-foreground tabular-nums">{pct(main.p)}</b></span>
                <SafetyMeter p={main} />
                {v && main.odds != null && <span className="flex items-center">Valoare <b className={cn('ml-1 text-sm tabular-nums', v.tone === 'win' ? 'text-win' : v.tone === 'loss' ? 'text-loss' : 'text-foreground')}>{v.text}</b><InfoTip text={HELP.value} label="Ce înseamnă valoarea?" /></span>}
                {main.result && <ResultBadge r={main.result} />}
              </div>
            </div>
            <OddsButton m={m} p={main} />
          </div>
        </div>
      ) : <div className="px-4 pb-3 text-xs text-muted-foreground">Fără predicții publicate pentru acest meci.</div>}
      {m.predictions.length > 1 && (
        <>
          <button onClick={() => setOpen(true)} className="flex min-h-[44px] w-full items-center justify-between border-t px-4 text-sm font-medium text-muted-foreground hover:bg-accent/40 hover:text-foreground">
            <span>Alte piețe <span className="text-xs">({m.predictions.length - 1})</span></span><ChevronRight className="h-4 w-4" />
          </button>
          {open && <MarketsSheet m={m} open={open} onClose={close} />}
        </>
      )}
    </article>
  );
}
