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
