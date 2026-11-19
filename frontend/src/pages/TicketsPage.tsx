import { PageHero } from '@/components/PageHero';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import { Ticket as TicketIcon } from 'lucide-react';
import { getJSON, useAsync } from '@/lib/fetcher';
import { loadTicketsHistory } from '@/lib/data';
import { useSettledTickets, useTodayBoard } from '@/lib/hooks';
import { useStore } from '@/lib/store';
import { isLostTicket, pickBoard, isBest } from '@/lib/board';
import { todayRo } from '@/lib/format';
import { TicketCard, waitingCorners } from '@/components/TicketCard';
import { Empty, Skeleton } from '@/components/kit';
import type { Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';

type Kind = 'toate' | 'best' | 'super' | 's10' | 'long' | 'corners' | 'mine';
type Sort = 'start' | 'cota' | 'sansa';
const KINDS: Array<[Kind, string]> = [['toate', 'Toate'], ['s10', 'Cotă ~10'], ['long', 'Bilete lungi'], ['corners', 'Cornere'], ['mine', 'Ale mele']];
const SORTS: Array<[Sort, string]> = [['start', 'Primul meci'], ['cota', 'Cotă'], ['sansa', 'Șansă']];

/** Felul biletului, pentru filtru: un bilet intră într-o singură categorie. */
function kindOf(t: Ticket): Kind {
  if (t.created_by === 'user') return 'mine';
  if (t.variant === 't100' || t.variant === 't1000' || t.variant === 't10000') return 'best';
  if (t.kind === 'acca_corners') return 'corners';
  if (t.kind === 'acca_super') return t.variant === 's10' ? 's10' : 'long';
  return 'toate';
}


function sortBy(list: Ticket[], s: Sort, first: (t: Ticket) => number): Ticket[] {
  if (s === 'start') return list;
  const k = s === 'cota' ? (t: Ticket) => -(t.total_odds ?? 0) : (t: Ticket) => -(t.p_ticket ?? 0);
  return [...list].sort((a, b) => k(a) - k(b) || first(a) - first(b));
}


type Tab = 'asteptare' | 'joc' | 'gata';
const TABS: Tab[] = ['asteptare', 'joc', 'gata'];
// nou început (19.11.2026): biletele Robotului de dinainte nu mai apar; cele jucate de mine rămân
const TICKETS_RESET = '2026-11-19T06:45:00Z';
const afterReset = (t: Ticket) => (t.created_at ?? '') >= TICKETS_RESET;

/** A început măcar un meci de pe bilet. */
function started(t: Ticket, now: number): boolean {
  return t.legs.some((l) => l.kickoff_utc && Date.parse(l.kickoff_utc) <= now);
}
const firstKick = (t: Ticket) => Math.min(...t.legs.map((l) => (l.kickoff_utc ? Date.parse(l.kickoff_utc) : Infinity)));
const finished = (t: Ticket) => t.status === 'won' || t.status === 'lost' || t.status === 'void' || isLostTicket(t);

/** Biletele din listă, pe trei file: încă neîncepute, în joc (inclusiv din zilele trecute), terminate. */
export default function TicketsPage() {
  const today = todayRo();
  const { full, map, loading } = useTodayBoard(today);
  const history = useAsync(loadTicketsHistory, []);
  const [params, setParams] = useSearchParams();
  const [limit, setLimit] = useState(20);
  // ora curentă, reîmprospătată la minut: un bilet trece singur din „Neîncepute” în „În joc”
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 60_000); return () => clearInterval(id); }, []);
  const todayAll = full.map((t) => map.get(t.id) ?? t);
  const robotPast = pickBoard((history.data ?? []).filter((t) => (t.date ?? '') < today));
  // biletele jucate de mine („Îl joc”, generator) intră în aceleași file; dacă biletul e și în lista Robotului se
  // păstrează o singură dată, iar unul înlocuit între timp de Robot rămâne cu copia mea (decontată din rezultate)
  const myTickets = useStore((s) => s.myTickets);
  const mineSettled = useSettledTickets(myTickets).tickets;
  const robotIds = new Set([...todayAll, ...robotPast].map((t) => String(t.id)));
  const extra = mineSettled.filter((t) => !robotIds.has(String(t.id)));
  const extraDay = (t: Ticket) => t.date ?? t.created_at?.slice(0, 10) ?? '';
  const past = [...robotPast, ...extra.filter((t) => extraDay(t) < today)];
  const all = [...todayAll, ...past, ...extra.filter((t) => extraDay(t) >= today)].filter((t) => (t.kind === 'acca_corners' || t.kind === 'acca_super' || t.created_by === 'user' || t.followed) && afterReset(t));
  const active = all.filter((t) => !finished(t));
  // „Alegerea robotului” sus, apoi după primul meci
  const waiting = active.filter((t) => !started(t, now)).sort((a, b) => Number(isBest(b)) - Number(isBest(a)) || firstKick(a) - firstKick(b));
  const held = active.filter((t) => waitingCorners(t, now)).sort((a, b) => firstKick(b) - firstKick(a));
  const live = active.filter((t) => started(t, now) && !waitingCorners(t, now)).sort((a, b) => firstKick(a) - firstKick(b));
  const done = all.filter(finished).sort((a, b) => (b.date ?? '').localeCompare(a.date ?? '') || String(b.id).localeCompare(String(a.id), undefined, { numeric: true }));
  const asked = params.get('f') as Tab | null;
  const tab: Tab = asked && TABS.includes(asked) ? asked : waiting.length || !live.length ? 'asteptare' : 'joc';
  const [kind, setKind] = useState<Kind>('toate');
  const setTab = (v: Tab) => { setLimit(20); setKind('toate'); setParams((p) => { p.set('f', v); return p; }, { replace: true }); };
  const [sort, setSort] = useState<Sort>('start');
  const pick = (xs: Ticket[]) => {
    // „Toate”: din Robot doar alegerea zilei (biletele de ~10 + cel mai bun pe fiecare cotă mare), restul la filtrul lor
    // „Toate”: doar biletele Robotului (1–2 de ~10 pe zi + 4–5 lungi în joc) și ale mele; restul rubricilor la filtrele lor
    const f = kind === 'toate' ? xs.filter((t) => t.kind === 'acca_super' || t.created_by === 'user' || t.followed) : xs.filter((t) => (kindOf(t) === kind || (kind === 'mine' && t.followed)));
    return kind === 'super' && sort === 'start' ? sortBy(f, 'sansa', firstKick) : sortBy(f, sort, firstKick);
  };
  const base = tab === 'asteptare' ? waiting : tab === 'joc' ? live : done;
  const counts = Object.fromEntries(KINDS.map(([k]) => [k, k === 'toate' ? base.filter((t) => t.kind === 'acca_super' || t.created_by === 'user' || t.followed).length : base.filter((t) => kindOf(t) === k || (k === 'mine' && t.followed)).length]));
  // la Terminate: toate / câștigate / pierdute
  const [res, setRes] = useState<'all' | 'won' | 'lost'>('all');
  const byRes = (xs: Ticket[]) => (tab !== 'gata' || res === 'all' ? xs : xs.filter((t) => (res === 'won' ? t.status === 'won' : t.status === 'lost' || isLostTicket(t))));
  const resCounts = { all: pick(base).length, won: pick(base).filter((t) => t.status === 'won').length, lost: pick(base).filter((t) => t.status === 'lost' || isLostTicket(t)).length };
  const filtered = byRes(pick(base));
  const heldShown = tab === 'joc' ? pick(held) : [];
  const list = tab === 'gata' ? filtered.slice(0, limit) : filtered;
  const busy = loading || history.loading;
  const focus = params.get('bilet') ?? '';
  useEffect(() => {
    if (!focus || busy) return;
    const t = all.find((x) => String(x.id) === focus);
    if (!t) return;
    const k = kindOf(t);
    // deep-link: fila se aliniază la biletul deschis din link
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reacție la ?bilet=, nu la o randare oarecare
    if (k !== 'toate') setKind(k);
    const which: Tab = finished(t) ? 'gata' : started(t, now) ? 'joc' : 'asteptare';
    setParams((p) => { if (p.get('f') === which) return p; p.set('f', which); return p; }, { replace: true });
  }, [focus, busy, now]);
  useEffect(() => {
    if (!focus || busy) return;
    const el = document.getElementById(`bilet-${focus}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [focus, busy, kind, tab, list.length]);
  return (
    <div className="product-corners space-y-5">
      <PageHero eyebrow="Din predicțiile recomandate · cotă ~10 și cote mari" title="Bilete" />
      <TrackStats />
      <div role="tablist" aria-label="Filtru bilete" className="grid grid-cols-3 gap-1 rounded-2xl border bg-muted/60 p-1">
        {([['asteptare', 'Neîncepute', waiting.length], ['joc', 'În joc', live.length], ['gata', 'Terminate', done.length]] as const).map(([v, label, n]) => {
          const on = tab === v;
          return (
            <button key={v} type="button" role="tab" aria-selected={on} onClick={() => setTab(v)}
              className={cn('press flex min-h-10 min-w-0 items-center justify-center gap-1.5 rounded-xl px-1 text-[13px] font-bold transition-colors', on ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground')}>
              <span className="truncate">{label}</span><span className="num opacity-80">{busy ? '…' : n}</span>
            </button>
          );
        })}
      </div>
      <div className="-mt-1 space-y-2">
        {(() => { const ks = KINDS.filter(([k]) => k === 'toate' || k === 's10' || k === 'long' || counts[k]); return (
        <div className={cn('grid gap-1.5', ks.length >= 5 ? 'grid-cols-5' : ks.length === 4 ? 'grid-cols-4' : 'grid-cols-3')} role="group" aria-label="Felul biletului">
          {ks.map(([k, label]) => (
            <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}
              className={cn('press flex min-h-12 min-w-0 flex-col items-center justify-center rounded-xl border px-1 py-1 leading-tight', kind === k ? 'border-primary bg-primary/15 text-primary' : 'text-muted-foreground')}>
              <span className="w-full truncate text-center text-[12px] font-bold">{label}</span>
              <span className="num text-[11px] opacity-75">{counts[k]}</span>
            </button>
          ))}
        </div>); })()}
        {kind === 'corners' && <p className="text-[11px] text-muted-foreground">Rubrica Cornere: peste 0,5 goluri + peste 7,5 cornere. Nu intră în „Toate”.</p>}
        {<div className="flex flex-wrap items-center justify-between gap-2">
          {tab === 'gata' ? (
            <div className="flex gap-1.5" role="group" aria-label="Rezultat">
              {([['all', 'Toate'], ['won', 'Câștigate'], ['lost', 'Pierdute']] as const).map(([k, label]) => (
                <button key={k} type="button" aria-pressed={res === k} onClick={() => { setRes(k); setLimit(20); }}
                  className={cn('press shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold', res === k ? (k === 'won' ? 'border-emerald-500 bg-emerald-500/15 text-win' : k === 'lost' ? 'border-red-500 bg-red-500/15 text-loss' : 'border-primary bg-primary/15 text-primary') : 'text-muted-foreground')}>
                  {label} <span className="num opacity-75">{resCounts[k]}</span>
                </button>
              ))}
            </div>
          ) : <span />}
          <select aria-label="Ordonare" className="input h-9 min-h-0 w-auto py-0 text-xs" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
            {SORTS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
        </div>}
      </div>
      {busy ? <Skeleton className="h-40 w-full rounded-2xl" />
        : list.length ? <div className="stagger space-y-3">{list.map((t) => <TicketCard key={t.id} t={t} compact />)}</div>
        : heldShown.length ? null
        : <Empty title={tab === 'asteptare' ? 'Niciun bilet neînceput' : tab === 'joc' ? 'Niciun bilet în joc' : 'Niciun bilet terminat'} icon={<TicketIcon className="h-8 w-8" />}>
            {tab === 'asteptare' ? 'Biletele noi (1–2 de ~10 pe zi și 4–5 lungi) apar aici după următoarea rulare a Robotului.' : 'Vezi celelalte file.'}
          </Empty>}
      {heldShown.length > 0 && (
        <section className="space-y-3" aria-label="Bilete fără cornere">
          <h2 className="text-sm font-bold">Terminate, încă nedecontate <span className="num text-muted-foreground">{heldShown.length}</span></h2>
          <p className="text-[11px] text-muted-foreground">Meciul s-a terminat. Nu le număr la „în joc”. Le marchez câștigate sau pierdute când scorul ajunge să închidă fiecare selecție.</p>
          <div className="stagger space-y-3">{heldShown.map((t) => <TicketCard key={t.id} t={t} compact />)}</div>
        </section>
      )}
      {!busy && !list.length && base.length > 0 && kind !== 'toate' && (
        <button type="button" className="btn btn-outline w-full" onClick={() => setKind('toate')}>
          Arată toate cele {base.length} bilete din această filă
        </button>
      )}
      {tab === 'gata' && filtered.length > limit && <button type="button" className="btn btn-outline w-full" onClick={() => setLimit((n) => n + 20)}>Mai multe ({filtered.length - limit} rămase)</button>}
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
function TrackStats() {
  const q = useAsync(() => getJSON<TrackDoc>('api/stats/super_tickets.json').catch(() => null), []);
  const d = q.data;
  if (!d?.all) return null;
  const ts = d.today_short;
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
      {ts && ts.made === 0 && (
        <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-[12px] leading-snug text-amber-600 dark:text-amber-400">
          Azi fără bilet de ~10: {ts.matches === 0 ? 'nu e niciun meci de cluburi' : `doar ${ts.matches} ${ts.matches === 1 ? 'meci' : 'meciuri'} de cluburi`} cu piețe recomandate între 10 și 24. Nu forțăm biletul; mâine e din nou.
        </p>
      )}
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

