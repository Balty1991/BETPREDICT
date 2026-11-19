import { PageHero } from '@/components/PageHero';
import { useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import { Ticket as TicketIcon, Rocket, History, Target } from 'lucide-react';
import { getJSON, useAsync } from '@/lib/fetcher';
import { loadTicketsHistory } from '@/lib/data';
import { useSettledTickets, useTodayBoard } from '@/lib/hooks';
import { useStore } from '@/lib/store';
import { isLostTicket, pickBoard } from '@/lib/board';
import { todayRo } from '@/lib/format';
import { HeroTicket, TicketRow, tierLabel } from '@/components/TicketCard';
import { Empty, Skeleton } from '@/components/kit';
import type { Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';

// nou început (19.11.2026): biletele Robotului de dinainte nu mai apar; cele jucate de mine rămân
const TICKETS_RESET = '2026-11-19T06:45:00Z';
const afterReset = (t: Ticket) => (t.created_at ?? '') >= TICKETS_RESET;

const firstKick = (t: Ticket) => Math.min(...t.legs.map((l) => (l.kickoff_utc ? Date.parse(l.kickoff_utc) : Infinity)));
const finished = (t: Ticket) => t.status === 'won' || t.status === 'lost' || t.status === 'void' || isLostTicket(t);
const isShort = (t: Ticket) => t.kind === 'acca_super' && t.variant === 's10';
const isLong = (t: Ticket) => t.kind === 'acca_super' && t.variant !== 's10';
const mine = (t: Ticket) => t.created_by === 'user' || !!t.followed;
const dayOf = (t: Ticket) => t.date ?? t.created_at?.slice(0, 10) ?? '';
const rowTitle = (t: Ticket) => (t.kind === 'acca_super' ? `Cotă ${tierLabel(t)}` : undefined);

function Section({ icon, title, count, sub, children }: { icon: ReactNode; title: string; count?: number; sub?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-2.5" aria-label={title}>
      <div className="flex items-end justify-between gap-2 px-0.5">
        <h2 className="flex items-center gap-2 text-[15px] font-extrabold tracking-tight"><span className="text-primary">{icon}</span>{title}{count != null && <span className="num rounded-full bg-muted px-2 py-px text-[11px] font-bold text-muted-foreground">{count}</span>}</h2>
        {sub && <span className="text-[11px] text-muted-foreground">{sub}</span>}
      </div>
      {children}
    </section>
  );
}

/** Bilete: sus biletul (biletele) de ~10 de azi, apoi biletele lungi în joc, urmărirea Robotului și istoricul de la noul început. */
export default function TicketsPage() {
  const today = todayRo();
  const { full, map, loading } = useTodayBoard(today);
  const history = useAsync(loadTicketsHistory, []);
  const track = useAsync(() => getJSON<TrackDoc>('api/stats/super_tickets.json').catch(() => null), []);
  const [params] = useSearchParams();
  const [limit, setLimit] = useState(10);
  const [res, setRes] = useState<'all' | 'won' | 'lost'>('all');
  const todayAll = full.map((t) => map.get(t.id) ?? t);
  const robotPast = pickBoard((history.data ?? []).filter((t) => (t.date ?? '') < today));
  // biletele jucate de mine („Îl joc”, generator): dacă biletul e și în lista Robotului se păstrează o singură dată
  const myTickets = useStore((s) => s.myTickets);
  const mineSettled = useSettledTickets(myTickets).tickets;
  const robotIds = new Set([...todayAll, ...robotPast].map((t) => String(t.id)));
  const extra = mineSettled.filter((t) => !robotIds.has(String(t.id)));
  const all = [...todayAll, ...robotPast, ...extra]
    .filter((t) => (t.kind === 'acca_corners' || t.kind === 'acca_super' || mine(t)) && afterReset(t));
  const todayShort = all.filter((t) => isShort(t) && dayOf(t) === today)
    .sort((a, b) => Number(finished(a)) - Number(finished(b)) || (b.p_ticket ?? 0) - (a.p_ticket ?? 0));
  const shownTop = new Set(todayShort.map((t) => String(t.id)));
  const active = all.filter((t) => !finished(t) && !shownTop.has(String(t.id)));
  const longs = active.filter(isLong).sort((a, b) => (a.total_odds ?? 0) - (b.total_odds ?? 0));
  const shortOther = active.filter(isShort).sort((a, b) => firstKick(a) - firstKick(b));
  const myActive = active.filter((t) => t.kind !== 'acca_super' && t.kind !== 'acca_corners' && mine(t)).sort((a, b) => firstKick(a) - firstKick(b));
  const corners = active.filter((t) => t.kind === 'acca_corners' && !mine(t)).sort((a, b) => (a.total_odds ?? 0) - (b.total_odds ?? 0));
  const done = all.filter((t) => finished(t) && !shownTop.has(String(t.id)) && t.kind !== 'acca_corners')
    .sort((a, b) => dayOf(b).localeCompare(dayOf(a)) || String(b.id).localeCompare(String(a.id), undefined, { numeric: true }));
  const isWon = (t: Ticket) => t.status === 'won';
  const doneShown = done.filter((t) => res === 'all' || (res === 'won' ? isWon(t) : !isWon(t) && t.status !== 'void'));
  const busy = loading || history.loading;
  const focus = params.get('bilet') ?? '';
  useEffect(() => {
    if (!focus || busy) return;
    document.getElementById(`bilet-${focus}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [focus, busy]);
  const ts = track.data?.today_short;
  return (
    <div className="product-corners space-y-6">
      <PageHero eyebrow="Cotă ~10 azi · bilete lungi 1.000–10.000" title="Bilete" />
      <Section icon={<Target className="h-4 w-4" />} title="Biletul de azi" sub="cotă ~10 · meciuri de azi 10–24">
        {busy ? <Skeleton className="h-96 w-full rounded-3xl" />
          : todayShort.length ? <div className="stagger space-y-4">{todayShort.map((t, i) => <HeroTicket key={t.id} t={t} eyebrow={todayShort.length > 1 ? `Biletul ${i + 1} din ${todayShort.length} · cotă ${tierLabel(t)}` : undefined} />)}</div>
          : <Empty title="Azi fără bilet de ~10" icon={<TicketIcon className="h-8 w-8" />}>
              {ts && ts.made === 0
                ? `${ts.matches === 0 ? 'Nu e niciun meci de cluburi' : `Doar ${ts.matches} ${ts.matches === 1 ? 'meci' : 'meciuri'} de cluburi`} cu piețe recomandate între 10 și 24. Nu forțăm biletul; mâine e din nou.`
                : 'Biletul de ~10 (1–2 pe zi) apare aici după rularea de dimineață a Robotului.'}
            </Empty>}
      </Section>
      {shortOther.length > 0 && (
        <Section icon={<Target className="h-4 w-4" />} title="Cotă ~10 din alte zile" count={shortOther.length}>
          <div className="space-y-2">{shortOther.map((t) => <TicketRow key={t.id} t={t} title={rowTitle(t)} />)}</div>
        </Section>
      )}
      <Section icon={<Rocket className="h-4 w-4" />} title="Bilete lungi" count={busy ? undefined : longs.length} sub="1.000 – 10.000 · cu SuperBonus">
        {busy ? <Skeleton className="h-40 w-full rounded-2xl" />
          : longs.length ? <div className="stagger space-y-2">{longs.map((t) => <TicketRow key={t.id} t={t} title={rowTitle(t)} />)}</div>
          : <p className="card px-4 py-3 text-[12px] text-muted-foreground">Niciun bilet lung în joc. Robotul pune 4–5 și înlocuiește unul pierdut la următoarea rulare.</p>}
      </Section>
      {myActive.length > 0 && (
        <Section icon={<TicketIcon className="h-4 w-4" />} title="Ale mele" count={myActive.length}>
          <div className="space-y-2">{myActive.map((t) => <TicketRow key={t.id} t={t} />)}</div>
        </Section>
      )}
      <TrackStats d={track.data} />
      {corners.length > 0 && (
        <details className="group">
          <summary className="card flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-bold">
            <span>Alte rubrici · Cornere <span className="num text-muted-foreground">{corners.length}</span></span>
            <span className="text-xs font-semibold text-primary group-open:hidden">Arată</span><span className="hidden text-xs font-semibold text-primary group-open:inline">Ascunde</span>
          </summary>
          <p className="mt-2 px-1 text-[11px] text-muted-foreground">Peste 0,5 goluri + peste 7,5 cornere. Rubrică separată, nu intră în urmărirea de mai sus.</p>
          <div className="mt-2 space-y-2">{corners.map((t) => <TicketRow key={t.id} t={t} />)}</div>
        </details>
      )}
      <Section icon={<History className="h-4 w-4" />} title="Istoric" count={busy ? undefined : done.length} sub="de la noul început, 19 nov.">
        <div className="flex gap-1.5" role="group" aria-label="Rezultat">
          {([['all', 'Toate', done.length], ['won', 'Câștigate', done.filter(isWon).length], ['lost', 'Pierdute', done.filter((t) => !isWon(t) && t.status !== 'void').length]] as const).map(([k, label, n]) => (
            <button key={k} type="button" aria-pressed={res === k} onClick={() => { setRes(k); setLimit(10); }}
              className={cn('press shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold', res === k ? (k === 'won' ? 'border-emerald-500 bg-emerald-500/15 text-win' : k === 'lost' ? 'border-red-500 bg-red-500/15 text-loss' : 'border-primary bg-primary/15 text-primary') : 'text-muted-foreground')}>
              {label} <span className="num opacity-75">{n}</span>
            </button>
          ))}
        </div>
        {busy ? <Skeleton className="h-24 w-full rounded-2xl" />
          : doneShown.length ? <div className="space-y-2">{doneShown.slice(0, limit).map((t) => <TicketRow key={t.id} t={t} title={rowTitle(t)} />)}</div>
          : <p className="card px-4 py-3 text-[12px] text-muted-foreground">Încă nimic terminat de la noul început.</p>}
        {doneShown.length > limit && <button type="button" className="btn btn-outline w-full" onClick={() => setLimit((n) => n + 20)}>Mai multe ({doneShown.length - limit} rămase)</button>}
      </Section>
    </div>
  );
}

/** Robotul 1000+: câte bilete s-au terminat, câte au ieșit și câte erau de așteptat după șansă (pe hârtie, miză egală). */
type Agg = { n: number; won: number; lost: number; pending: number; expected: number; roi: number | null; best: number | null };
type TrackDoc = { since: string | null; short: Agg; long: Agg; all: Agg; leg_hit: number | null; legs: number;
  last: { variant: string; status: string; odds: number; day: string }[]; today_short?: { made: number; matches: number } | null };

const pct = (x: number | null) => (x == null ? '–' : `${x >= 0 ? '+' : ''}${Math.round(x * 100)}%`);

/** O familie de bilete: câștigate din jucate, bara „câștigate vs așteptat”, ROI, câte sunt în joc. */
function TrackTile({ title, emoji, a, note }: { title: string; emoji: string; a: Agg; note: string }) {
  const max = Math.max(1, a.n);
  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/5 bg-gradient-to-br from-primary/15 via-[hsl(var(--elevated))] to-[hsl(var(--elevated))] p-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{emoji} {title}</span>
        {a.pending > 0 && <span className="rounded-full bg-primary/20 px-2 py-0.5 text-[10px] font-bold text-primary">{a.pending} în joc</span>}
      </div>
      <div className="mt-1 flex items-end gap-1">
        <span className="num text-3xl font-black leading-none text-win">{a.won}</span>
        <span className="num pb-0.5 text-sm font-bold text-muted-foreground">/ {a.n} câștigate</span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-[hsl(var(--win))]" style={{ width: `${(a.won / max) * 100}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
        <span>așteptat {a.expected.toFixed(1)}</span>
        <span>ROI <b className={cn((a.roi ?? 0) >= 0 ? 'text-win' : 'text-loss')}>{pct(a.roi)}</b></span>
      </div>
      <div className="mt-1 text-[10px] text-muted-foreground">{note}</div>
    </div>
  );
}

/** Urmărirea biletelor Robotului de la noul început: ~10 și lungi, ROI la miză egală, selecții intrate, ultimele rezultate. */
function TrackStats({ d }: { d?: TrackDoc | null }) {
  if (!d?.all) return null;
  const legPct = d.leg_hit == null ? null : Math.round(d.leg_hit * 100);
  return (
    <section className="card space-y-3 p-3" aria-label="Urmărire bilete Robot">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary/15 text-base">📈</span>
          <div className="leading-tight">
            <h2 className="text-sm font-extrabold">Urmărire Robot</h2>
            <p className="text-[11px] text-muted-foreground">{d.all.n} terminate · {d.all.pending} în joc</p>
          </div>
        </div>
        {d.since && <span className="rounded-full border px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">din {new Date(d.since).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short', timeZone: 'Europe/Bucharest' })}</span>}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <TrackTile title="Cotă ~10" emoji="🎯" a={d.short} note="1–2 pe zi · iese ~1 din 11" />
        <TrackTile title="Lungi" emoji="🚀" a={d.long} note={d.long.best ? `record ${Math.round(d.long.best).toLocaleString('ro-RO')}` : '1.000 – 10.000 · cu SuperBonus'} />
      </div>
      <div className="flex items-center gap-3 rounded-xl bg-[hsl(var(--elevated))] px-3 py-2">
        <div className="min-w-0 flex-1">
          <div className="flex justify-between text-[11px]"><span className="text-muted-foreground">Selecții intrate</span><b>{legPct == null ? '–' : `${legPct}%`} <span className="font-normal text-muted-foreground">din {d.legs}</span></b></div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${legPct ?? 0}%` }} /></div>
        </div>
        {d.last.length > 0 && (
          <div className="flex shrink-0 items-center gap-1" aria-label="Ultimele rezultate">
            {d.last.slice(-8).map((x, i) => (
              <span key={i} title={`${x.day} · cotă ${x.odds}`} className={cn('flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-black text-white', x.status === 'won' ? 'bg-[hsl(var(--win))]' : 'bg-[hsl(var(--loss))]')}>{x.status === 'won' ? '✓' : '×'}</span>
            ))}
          </div>
        )}
      </div>
      <details className="text-[11px] text-muted-foreground">
        <summary className="cursor-pointer font-semibold text-primary">Cum citesc cifrele</summary>
        <p className="mt-1 leading-snug">„Câștigate / jucate” numără doar biletele terminate. „Așteptat” = câte ar fi trebuit să iasă după șansa lor: dacă cele câștigate țin pasul, regulile merg. ROI la miză egală, cu SuperBonus inclus. Un bilet de ~10 iese cam 1 din 11, unul lung foarte rar.</p>
      </details>
    </section>
  );
}

