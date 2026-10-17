import { useMemo, useState } from 'react';
import { Activity, Flame, Target, Trophy } from 'lucide-react';
import type { Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';

type Period = '7' | '30' | 'all';
const PERIODS: Array<[Period, string]> = [['7', '7 zile'], ['30', '30 zile'], ['all', 'De la început']];

type Stat = {
  key: string; label: string; n: number; won: number; lost: number; active: number; roi: number | null;
  legsWon: number; legsSettled: number; nearMiss: number; best: number | null; streak: Array<'w' | 'l'>;
};

const settledLegs = (t: Ticket) => t.legs.filter((l) => l.result && l.result !== 'void');
const isWonLeg = (r: Ticket['legs'][number]['result']) => r === 'won' || r === 'half_won';

function stat(key: string, label: string, ts: Ticket[]): Stat {
  const done = ts.filter((t) => t.status === 'won' || t.status === 'lost');
  const won = done.filter((t) => t.status === 'won');
  const legs = done.flatMap(settledLegs);
  const byDate = [...done].sort((a, b) => (a.date ?? '').localeCompare(b.date ?? '') || String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
  return {
    key, label, n: done.length, won: won.length, lost: done.length - won.length,
    active: ts.filter((t) => t.status === 'pending' || !t.status).length,
    roi: done.length ? won.reduce((a, t) => a + t.total_odds, 0) / done.length - 1 : null,
    legsWon: legs.filter((l) => isWonLeg(l.result)).length, legsSettled: legs.length,
    // pierdut la o singură selecție: biletul „a fost aproape”
    nearMiss: done.filter((t) => t.status === 'lost' && t.legs.filter((l) => l.result === 'lost').length === 1).length,
    best: won.length ? Math.max(...won.map((t) => t.total_odds)) : null,
    streak: byDate.slice(-12).map((t) => (t.status === 'won' ? 'w' : 'l')),
  };
}

const pct = (x: number | null, d = 0) => (x == null ? '—' : `${x > 0 ? '+' : ''}${(x * 100).toFixed(d)}%`);
const tone = (x: number | null) => (x == null ? 'text-muted-foreground' : x >= 0 ? 'text-win' : 'text-loss');

/** Ring cu cât intră selecțiile (din cele decontate). */
function Ring({ v, size = 54 }: { v: number | null; size?: number }) {
  const r = size / 2 - 5, c = 2 * Math.PI * r, f = v == null ? 0 : Math.max(0, Math.min(1, v));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0" aria-hidden>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth={6} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--primary))" strokeWidth={6} strokeLinecap="round"
        strokeDasharray={`${c * f} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="52%" dominantBaseline="middle" textAnchor="middle" className="fill-foreground text-[12px] font-extrabold">{v == null ? '—' : `${Math.round(f * 100)}%`}</text>
    </svg>
  );
}

function Card({ s, total }: { s: Stat; total?: boolean }) {
  const hit = s.legsSettled ? s.legsWon / s.legsSettled : null;
  const wr = s.n ? s.won / s.n : null;
  return (
    <div className={cn('rounded-2xl border p-3', total ? 'border-primary/40 bg-primary/[0.06]' : 'bg-[hsl(var(--elevated))]')}>
      <div className="flex items-start gap-3">
        <Ring v={hit} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-[14px] font-extrabold">{s.label}</span>
            <span className={cn('num text-[15px] font-extrabold', tone(s.roi))}>{pct(s.roi, 1)}</span>
          </div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">selecții intrate: <b className="text-foreground">{s.legsWon}</b> din {s.legsSettled}</div>
          {/* bara câștigate / pierdute */}
          <div className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
            <span className="bg-win" style={{ width: `${s.n ? (s.won / s.n) * 100 : 0}%` }} />
            <span className="bg-loss/80" style={{ width: `${s.n ? (s.lost / s.n) * 100 : 0}%` }} />
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px]">
            <span><b className="num text-win">{s.won}</b> câștigate</span>
            <span><b className="num text-loss">{s.lost}</b> pierdute</span>
            {s.active > 0 && <span><b className="num">{s.active}</b> active</span>}
            {wr != null && <span className="text-muted-foreground">{(wr * 100).toFixed(0)}% din bilete</span>}
          </div>
        </div>
      </div>
      {(s.nearMiss > 0 || s.best || s.streak.length > 0) && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
          {s.best ? <span className="inline-flex items-center gap-1"><Trophy className="h-3 w-3 text-win" />cel mai mare: <b className="num text-foreground">{s.best.toFixed(2)}</b></span> : null}
          {s.nearMiss > 0 && <span className="inline-flex items-center gap-1"><Target className="h-3 w-3 text-warn" /><b className="num text-foreground">{s.nearMiss}</b> pierdute la o singură selecție</span>}
          {s.streak.length > 0 && (
            <span className="ml-auto inline-flex items-center gap-0.5" aria-label="ultimele bilete decontate">
              {s.streak.map((x, i) => <span key={i} className={cn('h-2.5 w-2.5 rounded-[3px]', x === 'w' ? 'bg-win' : 'bg-loss/70')} />)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/** Bilete › Monitorizare: pe fiecare categorie, câte bilete, câte câștigate / pierdute, câte selecții au intrat,
 *  ROI la 1 unitate pe bilet, pierdute la o singură selecție, cel mai mare câștig și ultimele rezultate. */
export function TicketMonitor({ tickets, kinds, kindOf, today }: {
  tickets: Ticket[]; kinds: Array<[string, string]>; kindOf: (t: Ticket) => string; today: string;
}) {
  const [period, setPeriod] = useState<Period>('7');
  const stats = useMemo(() => {
    const from = period === 'all' ? '' : new Date(Date.parse(today) - (Number(period) - 1) * 86400000).toISOString().slice(0, 10);
    const ts = tickets.filter((t) => (t.date ?? t.created_at?.slice(0, 10) ?? '') >= from);
    const cats = kinds.filter(([k]) => k !== 'toate').map(([k, label]) => stat(k, label, ts.filter((t) => kindOf(t) === k || (k === 'mine' && t.followed))))
      .filter((s) => s.n || s.active);
    return { total: stat('toate', 'Toate biletele', ts), cats };
  }, [tickets, kinds, kindOf, period, today]);
  return (
    <details className="card group p-4" open>
      <summary className="flex min-h-[40px] cursor-pointer list-none items-center gap-2 font-bold">
        <Activity className="h-4 w-4 text-primary" />Monitorizare pe categorii
        <Flame className="ml-auto h-4 w-4 text-muted-foreground transition-transform group-open:rotate-12" />
      </summary>
      <div className="mt-2 flex gap-1 rounded-xl border bg-muted/60 p-1">
        {PERIODS.map(([p, l]) => (
          <button key={p} type="button" aria-pressed={period === p} onClick={() => setPeriod(p)}
            className={cn('press flex-1 rounded-lg px-2 py-1.5 text-xs font-bold', period === p ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground')}>{l}</button>
        ))}
      </div>
      <div className="mt-3 space-y-2">
        <Card s={stats.total} total />
        <div className="grid gap-2 sm:grid-cols-2">{stats.cats.map((s) => <Card key={s.key} s={s} />)}</div>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">Inelul: cât din selecțiile decontate au intrat. ROI la 1 unitate pe bilet. Pătrățelele: ultimele bilete decontate (verde câștigat, roșu pierdut).</p>
    </details>
  );
}
