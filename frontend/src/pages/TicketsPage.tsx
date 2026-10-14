import { useMemo } from 'react';
import { useAsync } from '@/lib/fetcher';
import { loadTickets, loadTicketsHistory } from '@/lib/data';
import { useSettledTickets } from '@/lib/hooks';
import { pickBoard } from '@/lib/board';
import { todayRo } from '@/lib/format';
import { TicketCard, isLostTicket } from '@/components/TicketCard';
import { Empty, Skeleton, SectionTitle } from '@/components/kit';
import { Ticket as TicketIcon, History } from 'lucide-react';
import type { Ticket } from '@/lib/types';

/** Lista jucată: aceleași bilete ca notificarea și ca Statistici → Jucate. */
export default function TicketsPage() {
  const today = todayRo();
  const api = useAsync(() => loadTickets(today), [today]);
  const history = useAsync(loadTicketsHistory, []);
  const tickets = (api.data?.tickets ?? []).filter((t) => t.variant !== 'multi_zi');
  const settled = useSettledTickets(tickets);
  const map = useMemo(() => new Map(settled.tickets.map((t) => [t.id, t])), [settled.tickets]);
  const alive = (t: Ticket) => !isLostTicket(map.get(t.id) ?? t);
  const board = pickBoard(tickets.filter(alive));
  const past = (history.data ?? []).filter((t) => (t.date ?? '') < today && !isLostTicket(t)).slice(0, 8);
  return (
    <div className="space-y-5">
      <header>
        <h1>Bilete</h1>
        <p className="text-sm text-muted-foreground">Până la 10, publicate azi. Un bilet poate repeta cel mult 3 meciuri.</p>
      </header>
      {api.loading ? <Skeleton className="h-40 w-full rounded-2xl" />
        : board.length ? <div className="stagger space-y-3">{board.map((t) => <TicketCard key={t.id} t={map.get(t.id) ?? t} compact />)}</div>
        : <Empty title="Azi nu e niciun bilet în listă" icon={<TicketIcon className="h-8 w-8" />}>Cele sigure, loteria și super biletele nu intră aici.</Empty>}
      {past.length > 0 && (
        <section>
          <SectionTitle icon={<History className="h-5 w-5 text-primary" />} title="Zilele trecute" />
          <div className="space-y-3">{past.map((t) => <TicketCard key={t.id} t={t} compact />)}</div>
        </section>
      )}
    </div>
  );
}
