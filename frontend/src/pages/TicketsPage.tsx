import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
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
  const list = tab === 'asteptare' ? waiting : tab === 'joc' ? live : done.slice(0, limit);
  const busy = loading || history.loading;
  return (
    <div className="space-y-5">
      <header>
        <h1>Bilete</h1>
        <p className="text-sm text-muted-foreground">Până la 10 bilete pe zi, cel mult 3 meciuri comune.</p>
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
      {tab === 'gata' && done.length > limit && <button type="button" className="btn btn-outline w-full" onClick={() => setLimit((n) => n + 20)}>Mai multe ({done.length - limit} rămase)</button>}
      <section aria-label="Unelte" className="space-y-3">
        <h2 className="text-sm font-bold text-muted-foreground">Unelte</h2>
        <Link to="/egaluri" className="card press flex min-h-[48px] items-center gap-2 p-4 font-bold"><Equal className="h-4 w-4 text-primary" />Proiectul Egaluri<span className="text-xs font-semibold text-muted-foreground">egaluri peste piață</span><ChevronRight className="ml-auto h-4 w-4 text-muted-foreground" /></Link>
        <ManualGenerator date={today} />
        <ExposurePanel />
      </section>
    </div>
  );
}
