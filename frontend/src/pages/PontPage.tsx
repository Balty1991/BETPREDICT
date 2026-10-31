import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { CalendarDays, ChevronRight } from 'lucide-react';
import { PageHero } from '@/components/PageHero';
import { PontStats } from '@/components/PontStats';
import { TicketCard } from '@/components/TicketCard';
import { Skeleton } from '@/components/kit';
import { useAsync } from '@/lib/fetcher';
import { loadTickets, loadTicketsHistory } from '@/lib/data';
import { addDays, longDay, todayRo } from '@/lib/format';
import type { Ticket } from '@/lib/types';

const ticketDay = (t: Ticket) => t.date ?? t.created_at?.slice(0, 10) ?? '';

/** Rubrica dedicată Pontului zilei: selecția publicată azi/următoarea și arhiva ei, fără filtrul general al biletelor. */
export default function PontPage() {
  const today = todayRo();
  const tomorrow = addDays(today, 1);
  const [now] = useState(() => Date.now());
  const current = useAsync(() => loadTickets(today), [today]);
  const next = useAsync(() => loadTickets(tomorrow), [tomorrow]);
  const archive = useAsync(loadTicketsHistory, []);
  const points = useMemo(() => {
    const byId = new Map<string, Ticket>();
    for (const t of [...(archive.data ?? []), ...(current.data?.tickets ?? []), ...(next.data?.tickets ?? [])]) {
      if (t.kind !== 'acca_pont') continue;
      const date = ticketDay(t);
      byId.set(`${date}:${t.id}`, { ...t, date });
    }
    return [...byId.values()].sort((a, b) => ticketDay(b).localeCompare(ticketDay(a)) || String(b.id).localeCompare(String(a.id), undefined, { numeric: true }));
  }, [archive.data, current.data, next.data]);
  // Show the next ticket the user can still place, not an already-settled or
  // already-started pick from today. This makes tomorrow's pick visible after
  // today's match has begun, even while today's result remains in the archive.
  const unstarted = (t: Ticket) => t.status === 'pending' && t.legs.length > 0
    && t.legs.every((leg) => !leg.kickoff_utc || Date.parse(leg.kickoff_utc) > now);
  const todayPoints = points.filter((t) => ticketDay(t) === today && unstarted(t));
  const tomorrowPoints = points.filter((t) => ticketDay(t) === tomorrow && unstarted(t));
  const featured = todayPoints.length ? todayPoints : tomorrowPoints;
  const loading = current.loading || next.loading || archive.loading;

  return (
    <div className="space-y-4">
      <PageHero eyebrow="Selecția zilei · rezultate și istoric" title="Pontul zilei"
        right={<Link to="/bilete" className="btn btn-outline min-h-10 px-3 text-xs">Toate biletele</Link>} />

      <section aria-label="Pont publicat" className="space-y-2">
        <h2 className="flex items-center gap-2 text-base font-bold"><CalendarDays className="h-4 w-4 text-primary" />
          {todayPoints.length ? `Pontul publicat · ${longDay(today)}` : `Următorul Pont · ${longDay(tomorrow)}`}
        </h2>
        {loading ? <Skeleton className="h-40 w-full rounded-2xl" /> : featured.length ? (
          <div className="space-y-3">{featured.map((t) => <TicketCard key={`${ticketDay(t)}:${t.id}`} t={t} compact />)}</div>
        ) : (
          <div className="card p-4 text-sm text-muted-foreground">
            Nu este publicat încă un Pont pentru azi sau mâine. Când apare, va fi afișat aici și păstrat în istoricul de mai jos.
          </div>
        )}
      </section>

      <PontStats tickets={points} title="Bilanț și istoric complet" fullHistory />

      <Link to="/istoric" className="card press flex min-h-12 items-center gap-2 p-4 text-sm font-semibold">
        <CalendarDays className="h-4 w-4 text-primary" />Istoricul tuturor biletelor, pe zile
        <ChevronRight className="ml-auto h-4 w-4 text-muted-foreground" />
      </Link>
    </div>
  );
}
