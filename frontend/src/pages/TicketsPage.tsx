import { History, ChevronRight, Ticket as TicketIcon } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { loadTicketsHistory } from '@/lib/data';
import { useTodayBoard } from '@/lib/hooks';
import { pickBoard } from '@/lib/board';
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
function Summary({ board, past, today }: { board: Ticket[]; past: Ticket[]; today: string }) {
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
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Bilete azi</dt><dd className="text-[22px] font-extrabold leading-tight"><CountUp value={board.length} /></dd></div>
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Cotă medie</dt><dd className="text-[22px] font-extrabold leading-tight text-primary"><CountUp value={avgOdds} digits={2} /></dd></div>
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">7 zile</dt><dd className="num text-[18px] font-extrabold leading-tight"><span className="text-win">{won.length}</span><span className="text-muted-foreground">/</span><span className="text-loss">{lost.length}</span></dd></div>
          <div><dt className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">ROI 7 zile</dt><dd className={cn('text-[18px] font-extrabold leading-tight', roi == null ? '' : roi >= 0 ? 'text-win' : 'text-loss')}><CountUp value={roi == null ? null : roi * 100} digits={1} suffix="%" signed /></dd></div>
        </dl>
      </div>
      <p className="mt-3 text-[11px] text-muted-foreground">Inelul: șansa ca cel puțin un bilet de azi să intre, din șansele Robotului. ROI la 1 unitate pe fiecare bilet decontat din lista ultimelor 7 zile.</p>
    </Panel>
  );
}

/** Doar biletele de azi. Zilele trecute și uneltele stau închise, dedesubt. */
export default function TicketsPage() {
  const today = todayRo();
  const { board, map, loading } = useTodayBoard(today);
  const history = useAsync(loadTicketsHistory, []);
  const past = pickBoard((history.data ?? []).filter((t) => (t.date ?? '') < today)).reverse();
  return (
    <div className="space-y-5">
      <header>
        <h1>Bilete</h1>
        <p className="text-sm text-muted-foreground">Azi sunt {loading ? '…' : board.length}. Până la 10, cel mult 3 meciuri comune.</p>
      </header>
      {!loading && (board.length > 0 || past.length > 0) && <Summary board={board} past={past} today={today} />}
      {loading ? <Skeleton className="h-40 w-full rounded-2xl" />
        : board.length ? <div className="stagger space-y-3">{board.map((t) => <TicketCard key={t.id} t={map.get(t.id) ?? t} compact />)}</div>
        : <Empty title="Azi nu e niciun bilet în listă" icon={<TicketIcon className="h-8 w-8" />}>Cele sigure, loteria și super biletele nu intră aici.</Empty>}
      {past.length > 0 && (
        <details className="card group">
          <summary className="flex min-h-[52px] cursor-pointer list-none items-center gap-2 px-4 font-bold">
            <History className="h-4 w-4 text-primary" /> Zilele trecute
            <span className="rounded-full bg-muted px-2 py-px text-xs text-muted-foreground">{past.length}</span>
            <ChevronRight className="ml-auto h-4 w-4 text-muted-foreground transition-transform group-open:rotate-90" />
          </summary>
          <div className="space-y-3 px-2 pb-3">{past.map((t) => <TicketCard key={t.id} t={t} compact />)}</div>
        </details>
      )}
      <section aria-label="Unelte" className="space-y-3">
        <h2 className="text-sm font-bold text-muted-foreground">Unelte</h2>
        <ManualGenerator date={today} />
        <ExposurePanel />
      </section>
    </div>
  );
}
