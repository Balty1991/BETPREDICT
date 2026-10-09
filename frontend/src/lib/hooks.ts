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
function sameSettlement(a: Ticket[], b: Ticket[]) {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] === b[i]) continue;
    if (a[i].id !== b[i].id || a[i].status !== b[i].status || a[i].settled_legs !== b[i].settled_legs) return false;
  }
  return true;
}

export function useSettledTickets(tickets: Ticket[]): { tickets: Ticket[]; loading: boolean } {
  const dates = useMemo(() => {
    const s = new Set<string>();
    for (const t of tickets) if (t.status === 'pending' || !t.status) for (const l of t.legs) if (l.kickoff_utc && Date.parse(l.kickoff_utc) < Date.now()) s.add(roDay(l.kickoff_utc));
    return [...s].sort();
  }, [tickets]);
  const days = useDays(dates);
  const [out, setOut] = useState<Ticket[]>(tickets);
  useEffect(() => {
    const next = !days.data ? tickets : (() => {
      const res = resultsFromDays(days.data);
      return tickets.map((t) => (t.status === 'pending' || !t.status ? settleTicket(t, res) : t));
    })();
    // array nou la fiecare render (filter) — fără comparație, setOut redeclanșează efectul la infinit (React #185) și blochează meniul
    setOut((prev) => (sameSettlement(prev, next) ? prev : next));
  }, [days.data, tickets]);
  return { tickets: out, loading: days.loading };
}

/** Persistă decontarea biletelor mele, ca rezultatele să rămână și offline. */
export function usePersistMySettlement(settled: Ticket[], original: Ticket[]) {
  useEffect(() => {
    const changed = settled.filter((t, i) => original[i] && t.id === original[i].id && (t.status !== original[i].status || t.settled_legs !== original[i].settled_legs));
    if (changed.length) actions.updateTickets(changed);
  }, [settled, original]);
}
