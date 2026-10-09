import { useState } from 'react';
import { Link } from 'react-router';
import { Plus, Check, ChevronDown, ChevronUp } from 'lucide-react';
import type { Match, Prediction } from '@/lib/types';
import { odds as fo, pct, signed, roTime, roDay } from '@/lib/format';
import { isFinished, statusLabel, marketKey, marketTitle, marketOrder } from '@/lib/markets';
import { Badge, GradeBadge, ProbBar, ResultBadge, TeamLogo, SplitBar } from './kit';
import { useStore, actions } from '@/lib/store';
import { cn } from '@/lib/utils';
import { isRecommended } from '@/lib/rules';
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
    market: p.market, line: p.line, selection: p.selection, label: p.label, odds: p.odds ?? 0, p: p.p, grade: p.grade ?? null, result: null,
    reasons: p.reasons,
  };
}

export function AddButton({ m, p, small }: { m: Match; p: Prediction; small?: boolean }) {
  const inSlip = useStore((s) => s.slip.some((l) => l.match_id === m.id && l.market === p.market && l.line === p.line && l.selection === p.selection));
  const disabled = p.odds == null || m.status !== 'notstarted';
  return (
    <button disabled={disabled} title={disabled ? 'Fără cotă sau meci început' : 'Adaugă pe bilet'} onClick={(e) => { e.preventDefault(); actions.toggleSlip(toLeg(m, p)); }}
      className={cn('btn shrink-0', small ? 'h-10 w-10 p-0 md:h-7 md:w-7' : 'h-10 w-10 p-0 md:h-8 md:w-8', inSlip ? 'btn-primary' : 'btn-outline')}>
      {inSlip ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
    </button>
  );
}

export function PredLine({ m, p, showMatch }: { m: Match; p: Prediction; showMatch?: boolean }) {
  return (
    <div className="flex items-center gap-2 py-1.5">
      <div className="min-w-0 flex-1">
        {showMatch && <Link to={`/meci/${m.id}?zi=${roDay(m.kickoff_utc)}`} className="block truncate text-xs text-muted-foreground hover:underline">{roTime(m.kickoff_utc)} · {m.home.name} – {m.away.name} · {m.league.name}</Link>}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-semibold">{p.label}</span>
          <GradeBadge grade={p.grade} />
          {isRecommended(p) ? <Badge tone="win">recomandat</Badge> : p.value && p.odds != null && p.odds > 2.2 ? <Badge tone="outline">risc · cotă mare</Badge> : null}
          {p.result && <ResultBadge r={p.result} />}
        </div>
        <ProbBar p={p.p} className="mt-1 max-w-[160px] md:max-w-[220px]" />
      </div>
      <div className="w-11 text-right text-sm md:w-14"><div className="font-semibold">{pct(p.p)}</div><div className="text-[10px] text-muted-foreground">prob.</div></div>
      <div className="w-12 text-right text-sm md:w-14">
        <div className="font-semibold">{fo(p.odds)}</div>
        <div className="text-[10px] text-muted-foreground" title={p.odds_source ?? ''}>{p.odds == null ? 'fără cotă' : p.ev != null ? `EV ${signed(p.ev * 100, 0, '%')}` : 'cotă'}</div>
      </div>
      <AddButton m={m} p={p} small />
    </div>
  );
}

export function MatchCard({ m, focus }: { m: Match; focus: Prediction[] }) {
  const [open, setOpen] = useState(false);
  const main = focus[0] ?? m.predictions.find(isRecommended) ?? m.predictions.find((p) => p.is_pick) ?? m.predictions[0];
  const done = isFinished(m.status);
  const grouped = new Map<string, Prediction[]>();
  for (const p of m.predictions) { const k = marketKey(p.market, p.line); grouped.set(k, [...(grouped.get(k) ?? []), p]); }
  return (
    <div className="card card-hover overflow-hidden">
      <Link to={`/meci/${m.id}?zi=${roDay(m.kickoff_utc)}`} className="block p-3 hover:bg-accent/30">
        <div className="mb-2 flex items-center gap-2 text-[11px] text-muted-foreground">
          <TeamLogo src={m.league.logo} name={m.league.name} size={14} />
          <span className="truncate">{m.league.country ? `${m.league.country} · ` : ''}{m.league.name}</span>
          <span className="ml-auto flex items-center gap-1 whitespace-nowrap">
            {done ? 'Final' : m.status !== 'notstarted' ? statusLabel(m.status) : roTime(m.kickoff_utc)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-center gap-2"><TeamLogo src={m.home.logo} name={m.home.name} /><span className="truncate font-medium">{m.home.name}</span></div>
            <div className="flex items-center gap-2"><TeamLogo src={m.away.logo} name={m.away.name} /><span className="truncate font-medium">{m.away.name}</span></div>
          </div>
          {done && m.score?.ft && <div className="space-y-1 text-right text-base font-bold tabular-nums"><div>{m.score.ft[0]}</div><div>{m.score.ft[1]}</div></div>}
        </div>
        {(() => { const x = oneXTwo(m); return x ? <SplitBar className="mt-2.5" parts={x} /> : null; })()}
      </Link>
      {main ? (
        <div className="border-t px-3 py-1">
          {focus.length ? focus.slice(0, 2).map((p) => <PredLine key={String(p.id)} m={m} p={p} />) : <PredLine m={m} p={main} />}
          {main.reasons?.length ? <div className="pb-1 text-[11px] text-muted-foreground">{main.reasons.slice(0, 2).join(' · ')}</div> : null}
        </div>
      ) : <div className="border-t px-3 py-2 text-xs text-muted-foreground">Fără predicții publicate pentru acest meci.</div>}
      {m.predictions.length > 1 && (
        <>
          <button onClick={() => setOpen(!open)} className="flex min-h-[40px] w-full items-center justify-center gap-1 border-t py-1.5 text-xs md:min-h-0 text-muted-foreground hover:bg-accent/40">
            {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}{open ? 'Ascunde piețele' : `Toate piețele (${m.predictions.length})`}
          </button>
          {open && (
            <div className="space-y-2 border-t px-3 py-2">
              {[...grouped.entries()].sort((a, b) => marketOrder(a[0]) - marketOrder(b[0])).map(([k, ps]) => (
                <div key={k}>
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{marketTitle(k)}</div>
                  {ps.map((p) => <PredLine key={String(p.id)} m={m} p={p} />)}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
