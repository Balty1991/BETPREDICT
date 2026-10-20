import { useEffect, useMemo, useState } from 'react';
import { useAsync } from './fetcher';
import { loadDay, loadMeta, loadTickets, loadTicketsHistory } from './data';
import { pickBoard, isLostTicket } from './board';
import { useStore, actions } from './store';
import { legKey, resultsFromDays, settleTicket } from './robot';
import { roDay } from './format';
import type { Day, Ticket, TicketLeg } from './types';

export function useMeta() { return useAsync(loadMeta, []); }

export function useDay(date: string) {
  const minOdds = useStore((s) => s.settings.minOdds);
  return useAsync(() => loadDay(date, minOdds), [date, minOdds]);
}

export function useDays(dates: string[]) {
  const minOdds = useStore((s) => s.settings.minOdds);
  const key = dates.join(',');
   
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
  const [now] = useState(() => Date.now());
  const dates = useMemo(() => {
    const s = new Set<string>();
    for (const t of tickets) if (t.status === 'pending' || !t.status) for (const l of t.legs) if (l.kickoff_utc && Date.parse(l.kickoff_utc) < now) s.add(roDay(l.kickoff_utc));
    return [...s].sort();
  }, [tickets, now]);
  const days = useDays(dates);
  // selecțiile fără scor simplu (cornere, cartonașe, Bet Builder, Stil) se decontează doar pe server: le luăm rezultatul
  // din istoricul biletelor Robotului (aceeași selecție, același meci), altfel copia mea ar rămâne „în curs” la nesfârșit
  const history = useAsync(() => (dates.length ? loadTicketsHistory() : Promise.resolve([] as Ticket[])), [dates.length > 0]);
  const known = useMemo(() => {
    const m = new Map<string, Pick<TicketLeg, 'result' | 'score'>>();
    for (const t of history.data ?? []) for (const l of t.legs) if (l.result) m.set(legKey(l), { result: l.result, score: l.score ?? null });
    return m;
  }, [history.data]);
  const [out, setOut] = useState<Ticket[]>(tickets);
  useEffect(() => {
    const next = !days.data && !known.size ? tickets : (() => {
      const res = resultsFromDays(days.data ?? []);
      const fill = (t: Ticket): Ticket => ({ ...t, legs: t.legs.map((l) => (l.result ? l : { ...l, ...known.get(legKey(l)) })) });
      return tickets.map((t) => (t.status === 'pending' || !t.status ? settleTicket(known.size ? fill(t) : t, res) : t));
    })();
    // array nou la fiecare render (filter) — fără comparație, setOut redeclanșează efectul la infinit (React #185) și blochează meniul
    // eslint-disable-next-line react-hooks/set-state-in-effect -- identitate stabilă cerută de consumatori; setOut e no-op când decontarea nu s-a schimbat
    setOut((prev) => (sameSettlement(prev, next) ? prev : next));
  }, [days.data, tickets, known]);
  return { tickets: out, loading: days.loading };
}

/** Persistă decontarea biletelor mele, ca rezultatele să rămână și offline. */
export function usePersistMySettlement(settled: Ticket[], original: Ticket[]) {
  useEffect(() => {
    const changed = settled.filter((t, i) => original[i] && t.id === original[i].id && (t.status !== original[i].status || t.settled_legs !== original[i].settled_legs));
    if (changed.length) actions.updateTickets(changed);
  }, [settled, original]);
}

/** Lista de bilete de azi (aceeași pe Acasă și în Bilete): fără multi-zi și fără cele deja pierdute. */
export function useTodayBoard(today: string) {
  const api = useAsync(() => loadTickets(today), [today]);
  const tickets = useMemo(() => (api.data?.tickets ?? []).filter((t) => t.variant !== 'multi_zi'), [api.data]);
  const settled = useSettledTickets(tickets);
  const map = useMemo(() => new Map(settled.tickets.map((t) => [t.id, t])), [settled.tickets]);
  // lista se alege o dată, pe toate biletele zilei (exact ce urmăresc Statisticile); cele pierdute doar se ascund,
  // altfel un bilet pierdut ar lăsa loc altuia care nu a fost niciodată în listă
  const full = useMemo(() => pickBoard(tickets), [tickets]);
  const board = useMemo(() => full.filter((t) => !isLostTicket(map.get(t.id) ?? t)), [full, map]);
  return { board, full, map, loading: api.loading };
}
