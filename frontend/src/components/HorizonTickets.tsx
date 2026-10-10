import { Carousel } from '@/components/Carousel';
import { useMemo, useState } from 'react';
import { CalendarRange, ShieldAlert } from 'lucide-react';
import { useAsync } from '@/lib/fetcher';
import { loadUpcomingTickets } from '@/lib/data';
import { useSettledTickets } from '@/lib/hooks';
import { dayLabel, roTime, roDay } from '@/lib/format';
import { TicketCard } from './TicketCard';
import { InfoTip, Skeleton } from './kit';
import { cn } from '@/lib/utils';
import type { Ticket } from '@/lib/types';

const MULTI = 'multi';

/** Biletele Robotului pe tot orizontul (azi + 6 zile), grupate pe zi + bilete multi-zi, cu raport de expunere. */
export function HorizonTickets({ today }: { today: string }) {
  const up = useAsync(loadUpcomingTickets, []);
  const all = useMemo(() => up.data?.tickets ?? [], [up.data]);
  const settled = useSettledTickets(all);
  const byId = new Map(settled.tickets.map((t) => [t.id, t]));
  const groups = useMemo(() => {
    const g = new Map<string, Ticket[]>();
    const multi = all.filter((t) => t.variant === 'multi_zi');
    if (multi.length) g.set(MULTI, multi);
    for (const t of all) {
      if (t.variant === 'multi_zi' || !t.date || t.date <= today) continue;
      g.set(t.date, [...(g.get(t.date) ?? []), t]);
    }
    return g;
  }, [all, today]);
  const keys = [...groups.keys()];
  const [sel, setSel] = useState<string | null>(null);
  const cur = sel && groups.has(sel) ? sel : keys[0];
  const ex = up.data?.exposure;
  if (up.loading) return <Skeleton className="h-[120px] w-full rounded-2xl" />;
  if (!keys.length) return null;
  const list = (groups.get(cur!) ?? []).slice().sort((a, b) => Number(!!b.safe || b.kind === 'acca_safe') - Number(!!a.safe || a.kind === 'acca_safe') || (b.target_odds ?? 0) - (a.target_odds ?? 0));
  const value = (k: string) => (groups.get(k) ?? []).filter((t) => t.kind !== 'acca_safe').length;

  return (
    <section aria-labelledby="horizon-title">
      <div className="mb-3">
        <h2 id="horizon-title" className="flex items-center gap-1.5"><CalendarRange className="h-[18px] w-[18px] text-primary" aria-hidden />Bilete pe 7 zile</h2>
        <p className="text-xs text-muted-foreground">Cote mari (~50/100/500) pe tot programul publicat, pe zile și multi-zi. Doar valoare pozitivă.</p>
      </div>
      <Carousel label="Alege ziua" className="mb-3">
        {keys.map((k) => {
          const on = k === cur; const n = groups.get(k)!.length; const v = value(k);
          return (
            <button key={k} type="button" aria-pressed={on} onClick={() => setSel(k)}
              className={cn('press relative flex min-h-[48px] shrink-0 flex-col items-center justify-center rounded-2xl border px-3.5 leading-tight', on ? 'border-transparent text-primary-foreground' : 'bg-card/70 text-foreground')}>
              {on && <span aria-hidden className="nav-pill absolute inset-0 rounded-2xl" />}
              <span className="relative text-[13px] font-extrabold">{k === MULTI ? 'Multi-zi' : dayLabel(k)}</span>
              <span className={cn('relative text-[11px] font-semibold', on ? 'opacity-90' : 'text-muted-foreground')}>{n} {n === 1 ? 'bilet' : 'bilete'}{v ? ` · ${v} valoare` : ''}</span>
            </button>
          );
        })}
      </Carousel>
      <Carousel grid label="Bilete" className="items-start">
        {list.map((t) => <div key={t.id} className="w-[86%] max-w-[380px] shrink-0"><TicketCard t={byId.get(t.id) ?? t} compact /></div>)}
      </Carousel>
      {ex && ex.tickets > 1 && (
        <div className="card mt-3 p-3.5 text-sm">
          <div className="flex items-center gap-2 font-bold"><ShieldAlert className="h-4 w-4 text-primary" aria-hidden />Expunere controlată
            <InfoTip label="Ce înseamnă expunerea?" text={`Aceeași selecție (meci + pariu) apare în cel mult ${ex.max_tickets_per_selection} bilete active, ca o singură înfrângere să nu doboare multe bilete deodată.`} /></div>
          <dl className="mt-2 grid grid-cols-3 gap-2 text-center">
            <div><dt className="text-[11px] text-muted-foreground">Max. bilete / selecție</dt><dd className="num text-lg font-extrabold">{ex.max_tickets_on_one_selection}<span className="text-xs text-muted-foreground">/{ex.max_tickets_per_selection}</span></dd></div>
            <div><dt className="text-[11px] text-muted-foreground">Bilete independente</dt><dd className="num text-lg font-extrabold">{ex.independent_tickets}<span className="text-xs text-muted-foreground">/{ex.tickets}</span></dd></div>
            <div><dt className="text-[11px] text-muted-foreground">Perechi suprapuse</dt><dd className="num text-lg font-extrabold">{ex.shared_pairs}<span className="text-xs text-muted-foreground">/{ex.pairs_total}</span></dd></div>
          </dl>
          {ex.top.length > 0 && (
            <details className="mt-2 text-xs">
              <summary className="cursor-pointer font-semibold text-primary">Selecțiile folosite în mai multe bilete ({ex.top.length})</summary>
              <ul className="mt-1.5 divide-y">
                {ex.top.map((s, i) => (
                  <li key={i} className="flex items-center gap-2 py-1.5">
                    <span className="min-w-0 flex-1 truncate"><b>{s.label}</b> · {s.home} – {s.away} <span className="text-muted-foreground">({dayLabel(roDay(s.kickoff_utc))} {roTime(s.kickoff_utc)})</span></span>
                    <span className="num shrink-0 font-semibold">{s.tickets} bilete · {s.stake_units}u</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
