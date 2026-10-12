import { Link } from 'react-router';
import { useAsync } from '@/lib/fetcher';
import { loadSoftDraw, loadUpcomingTickets } from '@/lib/data';
import { odds as fo, roTime } from '@/lib/format';
import { TicketCard } from '@/components/TicketCard';
import type { Ticket } from '@/lib/types';

/** Egaluri la care Superbet e peste mediana pieței, plus biletul de două meciuri. */
export function SoftDrawCard() {
  const scan = useAsync(loadSoftDraw, []);
  const up = useAsync(loadUpcomingTickets, []);
  const events = scan.data?.events ?? [];
  const tickets = (up.data?.tickets ?? []).filter((t) => t.kind === 'acca_soft' && (t.status === 'pending' || !t.status));
  const used = new Set(tickets.flatMap((t) => t.legs.map((l) => l.match_id)));
  const rest = events.filter((e) => !used.has(e.match_id));
  return (
    <section aria-labelledby="soft-draw-title" className="card p-4">
      <div className="eyebrow text-primary">Superbet</div>
      <h2 id="soft-draw-title" className="text-lg font-bold">Egaluri peste piață</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Egal cu cotă 2,80–3,60, la care Superbet e cu cel puțin 2% peste mediana celorlalte case. Biletul are două meciuri din aceeași zi.
      </p>
      {scan.loading && !scan.data ? <p className="mt-3 text-sm text-muted-foreground">Se caută…</p> : null}
      {tickets.length > 0 && (
        <div className="mt-3 space-y-3">
          {tickets.map((t) => <TicketCard key={t.id} t={t as Ticket} compact />)}
        </div>
      )}
      {!scan.loading && events.length === 0 && (
        <p className="mt-3 text-sm text-muted-foreground">Acum nu e niciun egal Superbet în banda asta, cu preț peste piață.</p>
      )}
      {rest.length > 0 && (
        <ul className="mt-3 divide-y">
          {rest.map((e) => (
            <li key={e.match_id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <Link to={`/meci/${e.match_id}`} className="block truncate font-semibold">{e.home} – {e.away}</Link>
                <div className="text-xs text-muted-foreground">{roTime(e.kickoff_utc)} · mediana {fo(e.median)}</div>
              </div>
              <div className="text-right">
                <div className="num font-bold text-primary">{fo(e.odds)}</div>
                <div className="text-[11px] text-win">+{(e.gap * 100).toFixed(1)}%</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
