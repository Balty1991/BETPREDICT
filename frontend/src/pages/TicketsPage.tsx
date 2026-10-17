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
import { TicketMonitor } from '@/components/TicketMonitor';
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

type SPeriod = 'azi' | '7' | '30' | 'all';
const SPERIODS: Array<[SPeriod, string]> = [['azi', 'Azi'], ['7', 'Săptămână'], ['30', 'Lună'], ['all', 'Tot']];

/** Cotele, șansa și rezultatele listei, pe perioada aleasă: câștigate / pierdute, rata de câștig, ROI, profit, selecții
 *  intrate, ziua pe grafic și ce categorie merge / nu merge. Profitul e la 1 unitate pe bilet, la cota publicată. */
function Summary({ board, past, today, fresh }: { board: Ticket[]; past: Ticket[]; today: string; fresh: number }) {
  const [period, setPeriod] = useState<SPeriod>('7');
  const odds = board.map((t) => t.total_odds_published ?? t.total_odds).filter((x) => x > 0);
  const avgOdds = odds.length ? odds.reduce((a, b) => a + b, 0) / odds.length : null;
  const pTicket = board.map((t) => t.p_ticket).filter((x): x is number => x != null);
  // șansa ca măcar un bilet din listă să intre (tratate ca independente: e o estimare)
  const anyWin = pTicket.length ? 1 - pTicket.reduce((a, p) => a * (1 - p), 1) : null;
  const from = period === 'azi' ? today : period === 'all' ? '' : addDays(today, -(Number(period) - 1));
  const all = [...past, ...board];
  const inP = all.filter((t) => (t.date ?? '') >= from && (t.status === 'won' || t.status === 'lost'));
  const won = inP.filter((t) => t.status === 'won');
  const lost = inP.filter((t) => t.status === 'lost');
  const pay = (t: Ticket) => (t.total_odds_published ?? t.total_odds);
  const profit = won.reduce((a, t) => a + pay(t) - 1, 0) - lost.length;
  const n = won.length + lost.length;
  const roi = n ? profit / n : null;
  const wr = n ? won.length / n : null;
  const legs = inP.flatMap((t) => t.legs.filter((l) => l.result && l.result !== 'void'));
  const legHit = legs.length ? legs.filter((l) => l.result === 'won' || l.result === 'half_won').length / legs.length : null;
  // ultimele 14 zile: profit pe zi (bare)
  const days = Array.from({ length: 14 }, (_, i) => addDays(today, i - 13));
  const perDay = days.map((d) => {
    const ts = all.filter((t) => t.date === d && (t.status === 'won' || t.status === 'lost'));
    return { d, n: ts.length, p: ts.reduce((a, t) => a + (t.status === 'won' ? pay(t) - 1 : -1), 0) };
  });
  const maxAbs = Math.max(1, ...perDay.map((x) => Math.abs(x.p)));
  // ce merge / ce nu merge: categoriile cu destule bilete decontate în perioadă
  const cats = KINDS.filter(([k]) => k !== 'toate' && k !== 'mine').map(([k, label]) => {
    const ts = inP.filter((t) => kindOf(t) === k);
    const pr = ts.reduce((a, t) => a + (t.status === 'won' ? pay(t) - 1 : -1), 0);
    return { label, n: ts.length, roi: ts.length ? pr / ts.length : 0, won: ts.filter((t) => t.status === 'won').length };
  }).filter((c) => c.n >= 3).sort((a, b) => b.roi - a.roi);
  const best = cats[0], worst = cats.length > 1 ? cats[cats.length - 1] : undefined;
  const kpi = (label: string, v: React.ReactNode, cls = '') => (
    <div className="rounded-xl bg-[hsl(var(--elevated))] px-2.5 py-2"><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</dt><dd className={cn('num text-[18px] font-extrabold leading-tight', cls)}>{v}</dd></div>
  );
  return (
    <Panel glow="a" className="!p-4">
      <div className="flex items-center gap-4">
        <Ring value={anyWin} size={96} stroke={9} tone="primary" label="Șansa ca măcar un bilet să intre">
          <div><div className="dash-ring-v text-[19px]"><CountUp value={anyWin == null ? null : anyWin * 100} suffix="%" /></div><div className="px-2 text-[9px] font-bold uppercase leading-tight tracking-wider text-muted-foreground">măcar unul intră</div></div>
        </Ring>
        <dl className="grid min-w-0 flex-1 grid-cols-2 gap-x-3 gap-y-2">
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Active</dt><dd className="text-[22px] font-extrabold leading-tight"><CountUp value={board.length} /><span className="ml-1 align-middle text-[10px] font-semibold text-muted-foreground">{fresh} noi azi</span></dd></div>
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Cotă medie</dt><dd className="text-[22px] font-extrabold leading-tight text-primary"><CountUp value={avgOdds} digits={2} /></dd></div>
        </dl>
      </div>
      <div className="mt-3 flex gap-1 rounded-xl border bg-muted/60 p-1" role="tablist" aria-label="Perioada">
        {SPERIODS.map(([p, l]) => (
          <button key={p} type="button" role="tab" aria-selected={period === p} onClick={() => setPeriod(p)}
            className={cn('press flex-1 rounded-lg px-2 py-1.5 text-xs font-bold', period === p ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground')}>{l}</button>
        ))}
      </div>
      <dl className="mt-2 grid grid-cols-3 gap-1.5">
        {kpi('Câștigate', <><span className="text-win">{won.length}</span><span className="text-muted-foreground">/</span><span className="text-loss">{lost.length}</span></>)}
        {kpi('Win rate', wr == null ? '—' : `${(wr * 100).toFixed(0)}%`)}
        {kpi('ROI', <CountUp value={roi == null ? null : roi * 100} digits={1} suffix="%" signed />, roi == null ? '' : roi >= 0 ? 'text-win' : 'text-loss')}
        {kpi('Profit', `${profit >= 0 ? '+' : ''}${profit.toFixed(1)}u`, profit >= 0 ? 'text-win' : 'text-loss')}
        {kpi('Selecții intrate', legHit == null ? '—' : `${(legHit * 100).toFixed(0)}%`)}
        {kpi('Decontate', n)}
      </dl>
      <div className="mt-3">
        <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Profit pe zi · ultimele 14 zile</div>
        <div className="flex h-16 items-center gap-[3px]" aria-label="Profit pe zi">
          {perDay.map((x) => (
            <div key={x.d} className="flex h-full flex-1 flex-col justify-center" title={`${x.d}: ${x.n} bilete, ${x.p >= 0 ? '+' : ''}${x.p.toFixed(1)}u`}>
              <div className="flex h-1/2 items-end">{x.p > 0 && <span className="w-full rounded-t-[3px] bg-win" style={{ height: `${(x.p / maxAbs) * 100}%` }} />}</div>
              <div className="flex h-1/2 items-start border-t border-border/60">{x.p < 0 && <span className="w-full rounded-b-[3px] bg-loss/75" style={{ height: `${(-x.p / maxAbs) * 100}%` }} />}</div>
            </div>
          ))}
        </div>
        <div className="mt-0.5 flex justify-between text-[9px] text-muted-foreground"><span>{days[0].slice(8)}.{days[0].slice(5, 7)}</span><span>azi</span></div>
      </div>
      {(best || worst) && (
        <div className="mt-3 grid gap-1.5 text-[12px] sm:grid-cols-2">
          {best && <div className="rounded-xl border border-[hsl(var(--win)/0.35)] bg-win/10 px-3 py-2"><span className="text-[10px] font-bold uppercase tracking-wider text-win">Merge</span><div className="font-bold">{best.label}</div><div className="text-muted-foreground">{best.won}/{best.n} câștigate · ROI {(best.roi * 100).toFixed(0)}%</div></div>}
          {worst && worst !== best && <div className="rounded-xl border border-[hsl(var(--loss)/0.35)] bg-loss/10 px-3 py-2"><span className="text-[10px] font-bold uppercase tracking-wider text-loss">Nu merge</span><div className="font-bold">{worst.label}</div><div className="text-muted-foreground">{worst.won}/{worst.n} câștigate · ROI {(worst.roi * 100).toFixed(0)}%</div></div>}
        </div>
      )}
      <p className="mt-3 text-[11px] text-muted-foreground">Toate biletele: lista Robotului și cele jucate de tine („Îl joc”, generator). Inelul: șansa ca cel puțin un bilet activ să intre. ROI și profit la 1 unitate pe bilet decontat în perioada aleasă; „Merge / Nu merge” compară categoriile cu cel puțin 3 bilete decontate.</p>
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
      {!busy && all.length > 0 && <TicketMonitor tickets={all} kinds={KINDS} kindOf={kindOf} today={today} />}
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
