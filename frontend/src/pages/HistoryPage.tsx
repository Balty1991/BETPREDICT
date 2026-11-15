import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useAsync } from '@/lib/fetcher';
import { loadPyramidSafe, loadTicketsHistory } from '@/lib/data';
import { addDays, longDay, odds as fo, todayRo } from '@/lib/format';
import { STATS_SINCE } from '@/lib/rules';
import { TicketCard } from '@/components/TicketCard';
import { Skeleton } from '@/components/kit';
import { cn } from '@/lib/utils';

const chipWd = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', weekday: 'short' });
const chipDm = new Intl.DateTimeFormat('ro-RO', { timeZone: 'UTC', day: 'numeric', month: 'short' });
const noon = (d: string) => new Date(`${d}T12:00:00Z`);

/** Istoric: o zi, cornerele ei și pasul de piramidă. Fără celelalte sisteme. */
export default function HistoryPage() {
  const today = todayRo();
  const [sp, setSp] = useSearchParams();
  const day = sp.get('zi') && sp.get('zi')! < today && sp.get('zi')! >= STATS_SINCE ? sp.get('zi')! : addDays(today, -1);
  const setDay = (d: string) => { sp.set('zi', d); setSp(sp, { replace: true }); };
  const history = useAsync(loadTicketsHistory, []);
  const pyr = useAsync(() => loadPyramidSafe('1.20'), []);
  const days = useMemo(() => {
    const out: string[] = [];
    for (let d = addDays(today, -1); d >= STATS_SINCE && out.length < 14; d = addDays(d, -1)) out.push(d);
    return out;
  }, [today]);
  const corners = useMemo(() => (history.data ?? []).filter((t) => t.kind === 'acca_corners' && (t.date ?? '') === day), [history.data, day]);
  const won = corners.filter((t) => t.status === 'won').length;
  const lost = corners.filter((t) => t.status === 'lost').length;
  const step = pyr.data?.history?.find((r) => r.date === day);
  const stepTxt = !step ? 'fără pas' : step.status !== 'pick' ? 'pauză' : step.result === 'won' ? 'câștigat' : step.result === 'lost' ? 'pierdut' : 'în joc';

  return (
    <div className="space-y-5">
      <header className="desk-hero">
        <p className="brand-mark">Zi de zi</p>
        <h1>Zile</h1>
        <p className="mt-1 text-[15px] text-muted-foreground">{longDay(day)}</p>
      </header>

      <div className="scrollbar-none -mx-4 flex gap-2 overflow-x-auto px-4 pb-1" role="group" aria-label="Alege ziua">
        {days.map((d) => (
          <button key={d} type="button" aria-pressed={d === day} onClick={() => setDay(d)}
            className={cn('day-chip', d === day && 'day-chip-on')}>
            <span className="block capitalize">{d === addDays(today, -1) ? 'Ieri' : chipWd.format(noon(d)).replace(/[.,]/g, '')}</span>
            <span className="block text-[13px]">{chipDm.format(noon(d)).replace(/\.$/, '')}</span>
          </button>
        ))}
      </div>

      <Link to="/piramida" className={cn('pyr-day', step?.result === 'won' && 'pyr-day-won', step?.result === 'lost' && 'pyr-day-lost')}>
        <span className="door-k">Piramida cotă 2</span>
        <strong>{pyr.loading ? '…' : stepTxt}</strong>
        <span>{step?.odds ? `cotă ${fo(step.odds)}` : 'jumătate din bancă'}</span>
      </Link>

      <section className="space-y-2.5" aria-label="Cornerele zilei">
        <div className="flex items-end justify-between">
          <h2>Cornere</h2>
          <span className="text-[12px] text-muted-foreground">{history.loading ? '…' : `${won} câștigate · ${lost} pierdute`}</span>
        </div>
        {history.loading ? <Skeleton className="h-32 w-full rounded-2xl" /> : corners.length ? (
          <div className="stagger space-y-3">{corners.map((t) => <TicketCard key={t.id} t={t} compact />)}</div>
        ) : <p className="desk-empty">Niciun bilet de cornere în ziua asta.</p>}
      </section>
    </div>
  );
}
