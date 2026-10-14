import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { loadSoftDraw, loadUpcomingTickets } from '@/lib/data';
import { odds as fo, roTime } from '@/lib/format';
import { TicketCard } from '@/components/TicketCard';
import { SuperbetLink } from '@/components/SuperbetLink';
import type { Ticket } from '@/lib/types';

/** Egaluri la care Superbet e peste mediana pieței. Stă în „Alte bilete”. */
export function SoftDrawCard() {
  const scan = useAsync(loadSoftDraw, []);
  const up = useAsync(loadUpcomingTickets, []);
  const events = scan.data?.events ?? [];
  const tickets = (up.data?.tickets ?? []).filter((t) => t.kind === 'acca_soft' && (t.status === 'pending' || !t.status));
  const used = new Set(tickets.flatMap((t) => t.legs.map((l) => l.match_id)));
  const rest = events.filter((e) => !used.has(e.match_id));
  const bits = [
    tickets.length ? `${tickets.length} ${tickets.length === 1 ? 'bilet' : 'bilete'}` : '',
    rest.length ? `${rest.length} ${rest.length === 1 ? 'meci' : 'meciuri'}` : '',
  ].filter(Boolean);
  return (
    <details className="group rounded-2xl bg-[hsl(var(--elevated))]">
      <summary className="flex min-h-[48px] cursor-pointer list-none items-center gap-2 px-3 text-sm font-bold">
        Egaluri peste piață
        {bits.length > 0 && <span className="text-xs font-semibold text-muted-foreground">{bits.join(' · ')}</span>}
        <ChevronRight className="ml-auto h-4 w-4 shrink-0 text-muted-foreground" />
      </summary>
      <div className="space-y-3 px-2 pb-3">
        <p className="px-1 text-xs text-muted-foreground">
          Egal 2,80–3,60, Superbet cu cel puțin 2% peste mediană. Câte un bilet de două meciuri din aceeași zi, până se termină lista.
        </p>
        {scan.loading && !scan.data ? <p className="px-1 text-sm text-muted-foreground">Se caută…</p> : null}
        {tickets.map((t) => <TicketCard key={t.id} t={t as Ticket} compact />)}
        {!scan.loading && events.length === 0 && (
          <p className="px-1 text-sm text-muted-foreground">Acum nu e niciun egal Superbet în banda asta, cu preț peste piață.</p>
        )}
        {rest.length > 0 && (
          <ul className="divide-y px-1">
            {rest.map((e) => (
              <li key={e.match_id} className="flex items-center gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <Link to={`/meci/${e.match_id}`} className="block break-words font-semibold">{e.home} – {e.away}</Link>
                  <div className="text-xs text-muted-foreground">{roTime(e.kickoff_utc)} · mediana {fo(e.median)}</div>
                </div>
                <div className="text-right">
                  <div className="num font-bold text-primary">{fo(e.odds)}</div>
                  <div className="text-[11px] text-win">+{(e.gap * 100).toFixed(1)}%</div>
                  {e.superbet_url && <SuperbetLink url={e.superbet_url} className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-[hsl(0_75%_62%)]" />}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
