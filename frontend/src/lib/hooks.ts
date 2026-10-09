import { useEffect, useMemo, useState } from 'react';
import { useAsync } from './fetcher';
import { loadDay, loadMeta } from './data';
import { useStore, actions } from './store';
import { resultsFromDays, settleTicket } from './robot';
import { roDay } from './format';
import type { Day, Ticket } from './types';

export function useMeta() { return useAsync(loadMeta, []); }

export function useDay(date: string) {
  const minOdds = useStore((s) => s.settings.minOdds);
  return useAsync(() => loadDay(date, minOdds), [date, minOdds]);
}

export function useDays(dates: string[]) {
  const minOdds = useStore((s) => s.settings.minOdds);
  const key = dates.join(',');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useAsync(async () => Promise.all(dates.map((d) => loadDay(d, minOdds))) as Promise<Array<Day | null>>, [key, minOdds]);
}

/** Decontează automat biletele (rezultatele vin din fișierele zilelor). */
export function useSettledTickets(tickets: Ticket[]): { tickets: Ticket[]; loading: boolean } {
  const dates = useMemo(() => {
    const s = new Set<string>();
    for (const t of tickets) if (t.status === 'pending' || !t.status) for (const l of t.legs) if (l.kickoff_utc && Date.parse(l.kickoff_utc) < Date.now()) s.add(roDay(l.kickoff_utc));
    return [...s].sort();
  }, [tickets]);
  const days = useDays(dates);
  const [out, setOut] = useState<Ticket[]>(tickets);
  useEffect(() => {
    if (!days.data) { setOut(tickets); return; }
    const res = resultsFromDays(days.data);
    setOut(tickets.map((t) => (t.status === 'pending' || !t.status ? settleTicket(t, res) : t)));
  }, [days.data, tickets]);
  return { tickets: out, loading: days.loading };
}

/** Persistă decontarea biletelor mele, ca rezultatele să rămână și offline. */
export function usePersistMySettlement(settled: Ticket[], original: Ticket[]) {
  useEffect(() => {
    const changed = settled.filter((t, i) => original[i] && (t.status !== original[i].status || t.settled_legs !== original[i].settled_legs));
    if (changed.length) actions.updateTickets(changed);
  }, [settled, original]);
}
