import { KindSparks } from '@/components/KindSparks';
import { PageHero } from '@/components/PageHero';
import { useEffect, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router';
import { ChevronDown, ChevronRight, Equal, Ticket as TicketIcon } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { loadTicketsHistory } from '@/lib/data';
import { useSettledTickets, useTodayBoard } from '@/lib/hooks';
import { useStore } from '@/lib/store';
import { isLostTicket, pickBoard, isBest } from '@/lib/board';
import { todayRo } from '@/lib/format';
import { TicketCard } from '@/components/TicketCard';
import { ManualGenerator } from '@/components/ManualGenerator';
import { ExposurePanel } from '@/components/HorizonTickets';
import { Empty, Skeleton } from '@/components/kit';
import { CountUp, Panel, Ring } from '@/components/dash';
import type { Ticket } from '@/lib/types';
import { TicketMonitor } from '@/components/TicketMonitor';
import { cn } from '@/lib/utils';

type Kind = 'toate' | 'best' | 'p14' | 't80' | 'seg' | 'mono' | 'boost' | 'stil' | 'mine';
type Sort = 'start' | 'cota' | 'sansa';
const KINDS: Array<[Kind, string]> = [['toate', 'Toate'], ['best', '⭐ Robot'], ['p14', '1–4 echipă'], ['t80', '80%+'], ['seg', 'Potrivite'], ['mono', 'O piață'], ['boost', 'Cote mărite'], ['stil', 'Stil'], ['mine', 'Ale mele']];
const SORTS: Array<[Sort, string]> = [['start', 'Primul meci'], ['cota', 'Cotă'], ['sansa', 'Șansă']];

/** Felul biletului, pentru filtru: un bilet intră într-o singură categorie. */
function kindOf(t: Ticket): Kind {
  if (t.created_by === 'user') return 'mine';
  if (t.kind === 'acca_80') return 't80';
  if (t.kind === 'acca_seg') return 'seg';
  if (t.kind === 'acca_mono') return 'mono';
  if (isBest(t)) return 'best';
  if ((t.variant_label ?? '').includes('1–4 & R1')) return 'p14';
  if (t.kind === 'acca_boost' || t.legs.some((l) => l.market === 'boost')) return 'boost';
  return 'stil';
}

function sortBy(list: Ticket[], s: Sort, first: (t: Ticket) => number): Ticket[] {
  if (s === 'start') return list;
  const k = s === 'cota' ? (t: Ticket) => -(t.total_odds ?? 0) : (t: Ticket) => -(t.p_ticket ?? 0);
  return [...list].sort((a, b) => k(a) - k(b) || first(a) - first(b));
}

/** Biletele active, pe scurt: câte sunt, cota medie și șansa ca măcar unul să intre. Rezultatele pe perioade sunt în
 *  Monitorizare (sub file). */
function Summary({ board, fresh }: { board: Ticket[]; fresh: number }) {
  const odds = board.map((t) => t.total_odds_published ?? t.total_odds).filter((x) => x > 0);
  const avgOdds = odds.length ? odds.reduce((a, b) => a + b, 0) / odds.length : null;
  const pTicket = board.map((t) => t.p_ticket).filter((x): x is number => x != null);
  // șansa ca măcar un bilet din listă să intre (tratate ca independente: e o estimare)
  const anyWin = pTicket.length ? 1 - pTicket.reduce((a, p) => a * (1 - p), 1) : null;
  const [open, setOpen] = useState(() => { try { return localStorage.getItem('bp.sum.open') === '1'; } catch { return false; } });
  const toggle = () => setOpen((v) => { try { localStorage.setItem('bp.sum.open', v ? '0' : '1'); } catch { /* fără stocare */ } return !v; });
  return (
    <Panel glow="a" className="!p-3">
      <button type="button" onClick={toggle} aria-expanded={open} className="press flex w-full items-center gap-3 text-left">
        <Ring value={anyWin} size={open ? 84 : 58} stroke={open ? 8 : 6} tone="primary" label="Șansa ca măcar un bilet activ să intre">
          <div className={cn('dash-ring-v', open ? 'text-[17px]' : 'text-[12px]')}><CountUp value={anyWin == null ? null : anyWin * 100} suffix="%" /></div>
        </Ring>
        <dl className="grid min-w-0 flex-1 grid-cols-2 gap-x-3">
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Active</dt><dd className="text-[20px] font-extrabold leading-tight"><CountUp value={board.length} /><span className="ml-1 align-middle text-[10px] font-semibold text-muted-foreground">{fresh} noi</span></dd></div>
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Cotă medie</dt><dd className="text-[20px] font-extrabold leading-tight text-primary"><CountUp value={avgOdds} digits={2} /></dd></div>
        </dl>
        <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open && <p className="mt-2 text-[11px] text-muted-foreground">Inelul: șansa ca măcar un bilet activ să intre, din șansele Robotului. Active = neîncepute + în joc, din lista Robotului și cele jucate de tine. Rezultatele pe zile, săptămâni și categorii sunt în Monitorizare.</p>}
    </Panel>
  );
}

type Tab = 'asteptare' | 'joc' | 'gata';
const TABS: Tab[] = ['asteptare', 'joc', 'gata'];

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
  const all = [...todayAll, ...past, ...extra.filter((t) => extraDay(t) >= today)];
  const active = all.filter((t) => !finished(t));
  // „Alegerea robotului” sus, apoi după primul meci
  const waiting = active.filter((t) => !started(t, now)).sort((a, b) => Number(isBest(b)) - Number(isBest(a)) || firstKick(a) - firstKick(b));
  const live = active.filter((t) => started(t, now)).sort((a, b) => firstKick(a) - firstKick(b));
  const done = all.filter(finished).sort((a, b) => (b.date ?? '').localeCompare(a.date ?? '') || String(b.id).localeCompare(String(a.id), undefined, { numeric: true }));
  const asked = params.get('f') as Tab | null;
  const tab: Tab = asked && TABS.includes(asked) ? asked : waiting.length || !live.length ? 'asteptare' : 'joc';
  const setTab = (v: Tab) => { setLimit(20); setParams((p) => { p.set('f', v); return p; }, { replace: true }); };
  const [kind, setKind] = useState<Kind>('toate');
  const [sort, setSort] = useState<Sort>('start');
  const pick = (xs: Ticket[]) => sortBy(kind === 'toate' ? xs : xs.filter((t) => kindOf(t) === kind || (kind === 'mine' && t.followed)), sort, firstKick);
  const base = tab === 'asteptare' ? waiting : tab === 'joc' ? live : done;
  const counts = Object.fromEntries(KINDS.map(([k]) => [k, k === 'toate' ? base.length : base.filter((t) => kindOf(t) === k || (k === 'mine' && t.followed)).length]));
  // la Terminate: toate / câștigate / pierdute
  const [res, setRes] = useState<'all' | 'won' | 'lost'>('all');
  const byRes = (xs: Ticket[]) => (tab !== 'gata' || res === 'all' ? xs : xs.filter((t) => (res === 'won' ? t.status === 'won' : t.status === 'lost' || isLostTicket(t))));
  const resCounts = { all: pick(base).length, won: pick(base).filter((t) => t.status === 'won').length, lost: pick(base).filter((t) => t.status === 'lost' || isLostTicket(t)).length };
  const filtered = byRes(pick(base));
  const list = tab === 'gata' ? filtered.slice(0, limit) : filtered;
  const busy = loading || history.loading;
  const loc = useLocation();
  useEffect(() => {
    if (loc.hash === '#generator') document.getElementById('generator')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [loc.hash, busy]);
  return (
    <div className="space-y-5">
      <PageHero eyebrow="Robotul · doar Superbet" title="Bilete" stats={busy ? undefined : [{ label: 'neîncepute', value: waiting.length, tone: 'primary' }, { label: 'în joc', value: live.length }, { label: 'terminate', value: done.length }]} />
      {!busy && all.length > 0 && (
        <details className="card px-4 py-1">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between text-sm font-bold">Statistici bilete<span className="text-xs text-muted-foreground">▾</span></summary>
          <div className="space-y-3 pb-3">
            {(active.length > 0 || past.length > 0) && <Summary board={active} fresh={todayAll.length} />}
            <TicketMonitor tickets={all} kinds={KINDS} kindOf={kindOf} today={today} />
          </div>
        </details>
      )}
      {!busy && <KindSparks tickets={done} kinds={KINDS.filter(([k]) => k !== 'toate' && k !== 'mine')} kindOf={kindOf} />}
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
        <div className="flex gap-1.5 overflow-x-auto pb-1" role="group" aria-label="Felul biletului">
          {KINDS.filter(([k]) => k === 'toate' || counts[k]).map(([k, label]) => (
            <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}
              className={cn('press shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold', kind === k ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}>
              {label} <span className="num opacity-75">{counts[k]}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
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
        </div>
      </div>
      {busy ? <Skeleton className="h-40 w-full rounded-2xl" />
        : list.length ? <div className="stagger space-y-3">{list.map((t) => <TicketCard key={t.id} t={t} compact />)}</div>
        : <Empty title={tab === 'asteptare' ? 'Niciun bilet neînceput' : tab === 'joc' ? 'Niciun bilet în joc' : 'Niciun bilet terminat'} icon={<TicketIcon className="h-8 w-8" />}>
            {tab === 'asteptare' ? 'Biletele noi apar dimineața. Cele sigure, loteria și super biletele nu intră aici.' : 'Vezi celelalte file.'}
          </Empty>}
      {tab === 'gata' && filtered.length > limit && <button type="button" className="btn btn-outline w-full" onClick={() => setLimit((n) => n + 20)}>Mai multe ({filtered.length - limit} rămase)</button>}
      <section aria-label="Unelte" className="space-y-3">
        <h2 className="text-sm font-bold text-muted-foreground">Unelte</h2>
        <Link to="/egaluri" className="card press flex min-h-[48px] items-center gap-2 p-4 font-bold"><Equal className="h-4 w-4 text-primary" />Proiectul Egaluri<span className="text-xs font-semibold text-muted-foreground">egaluri peste piață</span><ChevronRight className="ml-auto h-4 w-4 text-muted-foreground" /></Link>
        <div id="generator" className="scroll-mt-20"><ManualGenerator date={today} /></div>
        <ExposurePanel />
      </section>
    </div>
  );
}
