import { useEffect, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router';
import { CheckCircle2, ChevronRight, Clock, Equal, PlayCircle, Ticket as TicketIcon } from 'lucide-react';
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
import { addDays } from '@/lib/format';
import type { Ticket } from '@/lib/types';
import { cn } from '@/lib/utils';

type Kind = 'toate' | 'best' | 'p14' | 't80' | 'boost' | 'stil' | 'mine';
type Sort = 'start' | 'cota' | 'sansa';
const KINDS: Array<[Kind, string]> = [['toate', 'Toate'], ['best', '⭐ Alegerea robotului'], ['p14', '1–4 pe echipă'], ['t80', 'Tiparul 80%+'], ['boost', 'Cote mărite'], ['stil', 'Stil'], ['mine', 'Ale mele']];
const SORTS: Array<[Sort, string]> = [['start', 'Primul meci'], ['cota', 'Cotă'], ['sansa', 'Șansă']];

/** Felul biletului, pentru filtru: un bilet intră într-o singură categorie. */
function kindOf(t: Ticket): Kind {
  if (t.created_by === 'user') return 'mine';
  if (t.kind === 'acca_80') return 't80';
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

/** Cotele, șansa și rezultatele listei, pe scurt. Profitul e la 1 unitate pe bilet, la cota publicată. */
function Summary({ board, past, today, fresh }: { board: Ticket[]; past: Ticket[]; today: string; fresh: number }) {
  const odds = board.map((t) => t.total_odds_published ?? t.total_odds).filter((x) => x > 0);
  const avgOdds = odds.length ? odds.reduce((a, b) => a + b, 0) / odds.length : null;
  const pTicket = board.map((t) => t.p_ticket).filter((x): x is number => x != null);
  // șansa ca măcar un bilet din listă să intre (tratate ca independente: e o estimare)
  const anyWin = pTicket.length ? 1 - pTicket.reduce((a, p) => a * (1 - p), 1) : null;
  const week = past.filter((t) => (t.date ?? '') >= addDays(today, -7));
  const won = week.filter((t) => t.status === 'won');
  const lost = week.filter((t) => t.status === 'lost');
  const profit = won.reduce((a, t) => a + (t.total_odds_published ?? t.total_odds) - 1, 0) - lost.length;
  const roi = won.length + lost.length ? profit / (won.length + lost.length) : null;
  return (
    <Panel glow="a" className="!p-4">
      <div className="flex items-center gap-4">
        <Ring value={anyWin} size={104} stroke={9} tone="primary" label="Șansa ca măcar un bilet să intre">
          <div><div className="dash-ring-v text-[20px]"><CountUp value={anyWin == null ? null : anyWin * 100} suffix="%" /></div><div className="px-2 text-[9px] font-bold uppercase leading-tight tracking-wider text-muted-foreground">măcar unul intră</div></div>
        </Ring>
        <dl className="grid min-w-0 flex-1 grid-cols-2 gap-x-3 gap-y-2.5">
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Active</dt><dd className="text-[22px] font-extrabold leading-tight"><CountUp value={board.length} /><span className="ml-1 align-middle text-[10px] font-semibold text-muted-foreground">{fresh} noi azi</span></dd></div>
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Cotă medie</dt><dd className="text-[22px] font-extrabold leading-tight text-primary"><CountUp value={avgOdds} digits={2} /></dd></div>
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">7 zile</dt><dd className="num text-[18px] font-extrabold leading-tight"><span className="text-win">{won.length}</span><span className="text-muted-foreground">/</span><span className="text-loss">{lost.length}</span></dd></div>
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">ROI 7 zile</dt><dd className={cn('text-[18px] font-extrabold leading-tight', roi == null ? '' : roi >= 0 ? 'text-win' : 'text-loss')}><CountUp value={roi == null ? null : roi * 100} digits={1} suffix="%" signed /></dd></div>
        </dl>
      </div>
      <p className="mt-3 text-[11px] text-muted-foreground">Aici sunt toate biletele: lista Robotului și cele jucate de tine („Îl joc”, generator). Piramida are pagina ei. Active = neîncepute + în joc. Inelul: șansa ca cel puțin un bilet activ să intre, din șansele Robotului. ROI la 1 unitate pe fiecare bilet decontat din lista ultimelor 7 zile.</p>
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
  const filtered = pick(base);
  const list = tab === 'gata' ? filtered.slice(0, limit) : filtered;
  const busy = loading || history.loading;
  const loc = useLocation();
  useEffect(() => {
    if (loc.hash === '#generator') document.getElementById('generator')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [loc.hash, busy]);
  return (
    <div className="space-y-5">
      <header>
        <h1>Bilete</h1>
        <p className="text-sm text-muted-foreground">Bilete de la cota 20: cel mult unul sub 50 pe zi, restul de 80–200. Biletele 1–4 pe echipă apar mereu.</p>
      </header>
      {!busy && (active.length > 0 || past.length > 0) && <Summary board={active} past={past} today={today} fresh={todayAll.length} />}
      <div role="tablist" aria-label="Filtru bilete" className="grid grid-cols-3 gap-1 rounded-2xl border bg-muted/60 p-1">
        {([['asteptare', 'Neîncepute', Clock, waiting.length], ['joc', 'În joc', PlayCircle, live.length], ['gata', 'Terminate', CheckCircle2, done.length]] as const).map(([v, label, Icon, n]) => {
          const on = tab === v;
          return (
            <button key={v} type="button" role="tab" aria-selected={on} onClick={() => setTab(v)}
              className={cn('press flex min-w-0 flex-col items-center gap-0.5 rounded-xl px-1 py-2 font-bold transition-colors', on ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground')}>
              <span className="flex min-w-0 items-center gap-1 text-[13px]"><Icon className="h-4 w-4 shrink-0" /><span className="truncate">{label}</span></span>
              <span className="num text-lg leading-none">{busy ? '…' : n}</span>
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
        <div className="flex items-center gap-1.5 text-xs" role="group" aria-label="Ordonare">
          <span className="text-muted-foreground">Ordonate după:</span>
          {SORTS.map(([k, label]) => (
            <button key={k} type="button" aria-pressed={sort === k} onClick={() => setSort(k)}
              className={cn('press rounded-full px-2.5 py-1 font-semibold', sort === k ? 'bg-primary/15 text-primary' : 'text-muted-foreground')}>{label}</button>
          ))}
        </div>
      </div>
      <p className="-mt-2 text-xs text-muted-foreground">
        {tab === 'asteptare' ? 'Niciun meci început. Se pot juca acum, ordonate după primul meci.'
          : tab === 'joc' ? 'Au început (și cele publicate în zilele trecute). Niciun meci pierdut până acum.'
          : 'Câștigate, pierdute sau anulate, cele mai noi primele.'}
      </p>
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
