/**
 * Stare locală persistentă (localStorage) — setări, bilet în construcție, biletele mele,
 * jurnalul local al propunerilor Robotului și retragerile din piramidă.
 * Jurnalul oficial e pe server (pipeline); acesta e doar pentru ce face utilizatorul pe dispozitiv.
 */
import { useSyncExternalStore } from 'react';
import type { Ticket, TicketLeg, PyramidHistoryRow } from './types';

export interface Settings {
  minOdds: number;
  theme: 'dark' | 'light';
  allowEstimatedOdds: boolean;
  defaultStake: number;
  pyramid: {
    startBank: number;
    withdrawSteps: number[];
    withdrawPct: number;
    targetMultiple: number;
    targetWithdrawPct: number;
  };
  autoTickets: boolean;
}

export interface Withdrawal { date: string; amount: number; note?: string }

export interface State {
  settings: Settings;
  slip: TicketLeg[];
  myTickets: Ticket[];
  /** bilete generate de Robot și afișate local (cheie zi) — salvare automată */
  robotLog: Record<string, Ticket[]>;
  /** propunerile zilnice de piramidă generate local */
  pyramidLog: Record<string, PyramidHistoryRow & { legs?: TicketLeg[] }>;
  withdrawals: Withdrawal[];
  /** arhivă: TOATE biletele generate de Robot în aplicație (inclusiv regenerările), pentru statistici */
  robotArchive: Ticket[];
}

export const DEFAULT_SETTINGS: Settings = {
  minOdds: 1.15,
  theme: 'dark',
  allowEstimatedOdds: false,
  defaultStake: 10,
  pyramid: { startBank: 100, withdrawSteps: [3, 5, 7], withdrawPct: 0.3, targetMultiple: 8, targetWithdrawPct: 0.5 },
  autoTickets: true,
};

const KEY = 'betpredict.v3';
const listeners = new Set<() => void>();

function load(): State {
  const empty: State = { settings: DEFAULT_SETTINGS, slip: [], myTickets: [], robotLog: {}, pyramidLog: {}, withdrawals: [], robotArchive: [] };
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return empty;
    const s = JSON.parse(raw) as Partial<State>;
    return {
      ...empty, ...s,
      robotArchive: s.robotArchive ?? Object.entries(s.robotLog ?? {}).flatMap(([d, ts]) => (ts ?? []).map((t) => ({ ...t, date: t.date ?? d }))),
      settings: { ...DEFAULT_SETTINGS, ...(s.settings ?? {}), pyramid: { ...DEFAULT_SETTINGS.pyramid, ...(s.settings?.pyramid ?? {}) } },
    };
  } catch {
    return empty;
  }
}

let state: State = typeof localStorage !== 'undefined' ? load() : { settings: DEFAULT_SETTINGS, slip: [], myTickets: [], robotLog: {}, pyramidLog: {}, withdrawals: [], robotArchive: [] };

export function getState() { return state; }
export function setState(fn: (s: State) => State) {
  state = fn(state);
  // păstrăm doar ultimele 60 de zile în jurnalele locale
  const keys = Object.keys(state.robotLog).sort();
  if (keys.length > 60) {
    const keep = new Set(keys.slice(-60));
    state = { ...state, robotLog: Object.fromEntries(Object.entries(state.robotLog).filter(([k]) => keep.has(k))) };
  }
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* spațiu plin */ }
  listeners.forEach((l) => l());
}
function subscribe(l: () => void) { listeners.add(l); return () => listeners.delete(l); }

export function useStore<T>(sel: (s: State) => T): T {
  return useSyncExternalStore(subscribe, () => sel(state), () => sel(state));
}

export const actions = {
  setSettings(patch: Partial<Settings>) { setState((s) => ({ ...s, settings: { ...s.settings, ...patch } })); },
  setPyramidRules(patch: Partial<Settings['pyramid']>) { setState((s) => ({ ...s, settings: { ...s.settings, pyramid: { ...s.settings.pyramid, ...patch } } })); },
  toggleSlip(leg: TicketLeg) {
    setState((s) => {
      const same = s.slip.find((l) => l.match_id === leg.match_id && l.market === leg.market && l.line === leg.line && l.selection === leg.selection);
      if (same) return { ...s, slip: s.slip.filter((l) => l !== same) };
      // max. 1 selecție pe meci: înlocuim selecția existentă de pe același meci
      return { ...s, slip: [...s.slip.filter((l) => l.match_id !== leg.match_id), leg] };
    });
  },
  clearSlip() { setState((s) => ({ ...s, slip: [] })); },
  saveTicket(t: Ticket) { setState((s) => ({ ...s, myTickets: [t, ...s.myTickets.filter((x) => x.id !== t.id)] })); },
  removeTicket(id: Ticket['id']) { setState((s) => ({ ...s, myTickets: s.myTickets.filter((x) => x.id !== id) })); },
  updateTickets(list: Ticket[]) {
    setState((s) => {
      const byId = new Map(list.map((t) => [t.id, t]));
      return { ...s, myTickets: s.myTickets.map((t) => byId.get(t.id) ?? t) };
    });
  },
  logRobotTickets(date: string, tickets: Ticket[], replace = false) {
    setState((s) => {
      const prev = s.robotLog[date] ?? [];
      if (!replace && prev.length) return s;
      const known = new Set(s.robotArchive.map((t) => t.id));
      const add = tickets.filter((t) => !known.has(t.id)).map((t) => ({ ...t, date: t.date ?? date }));
      return { ...s, robotLog: { ...s.robotLog, [date]: tickets }, robotArchive: [...s.robotArchive, ...add].slice(-2000) };
    });
  },
  updateRobotLog(date: string, tickets: Ticket[]) { setState((s) => ({ ...s, robotLog: { ...s.robotLog, [date]: tickets } })); },
  updateArchive(list: Ticket[]) {
    setState((s) => { const byId = new Map(list.map((t) => [t.id, t])); return { ...s, robotArchive: s.robotArchive.map((t) => byId.get(t.id) ?? t) }; });
  },
  logPyramid(date: string, row: PyramidHistoryRow & { legs?: TicketLeg[] }, replace = false) {
    setState((s) => (s.pyramidLog[date] && !replace ? s : { ...s, pyramidLog: { ...s.pyramidLog, [date]: row } }));
  },
  addWithdrawal(w: Withdrawal) { setState((s) => ({ ...s, withdrawals: [...s.withdrawals, w] })); },
  removeWithdrawal(i: number) { setState((s) => ({ ...s, withdrawals: s.withdrawals.filter((_, k) => k !== i) })); },
  importState(json: string) {
    const parsed = JSON.parse(json) as Partial<State>;
    setState((s) => ({ ...s, ...parsed, settings: { ...s.settings, ...(parsed.settings ?? {}) } }));
  },
};

export function exportState(): string { return JSON.stringify(state, null, 2); }
