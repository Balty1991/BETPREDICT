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
  /** Import cu ÎMBINARE (nu suprascrie): biletele se unesc după id, zilele de piramidă după dată. */
  importState(json: string) {
    const parsed = JSON.parse(json) as Partial<State>;
    if (!parsed || typeof parsed !== 'object') throw new Error('format invalid');
    setState((s) => mergeState(s, parsed));
  },
};

export function exportState(): string { return JSON.stringify(state, null, 2); }

const byId = <T extends { id: string | number }>(a: T[], b: T[] = []) => { const m = new Map<string, T>(); for (const t of [...a, ...b]) m.set(String(t.id), t); return [...m.values()]; };

export function mergeState(s: State, p: Partial<State>): State {
  const robotLog = { ...s.robotLog };
  for (const [d, ts] of Object.entries(p.robotLog ?? {})) robotLog[d] = byId(robotLog[d] ?? [], ts);
  const wkey = (w: Withdrawal) => JSON.stringify(w);
  const wd = new Map(s.withdrawals.map((w) => [wkey(w), w])); for (const w of p.withdrawals ?? []) wd.set(wkey(w), w);
  return {
    ...s,
    settings: { ...s.settings, ...(p.settings ?? {}), pyramid: { ...s.settings.pyramid, ...(p.settings?.pyramid ?? {}) } },
    myTickets: byId(s.myTickets, p.myTickets),
    robotArchive: byId(s.robotArchive, p.robotArchive).slice(-2000),
    robotLog,
    pyramidLog: { ...(p.pyramidLog ?? {}), ...s.pyramidLog, ...Object.fromEntries(Object.entries(p.pyramidLog ?? {}).filter(([d, r]) => r.result && r.result !== 'pending' && !(s.pyramidLog[d]?.result && s.pyramidLog[d].result !== 'pending'))) },
    withdrawals: [...wd.values()],
  };
}

/** Cod de sincronizare (fără server, fără secrete): JSON comprimat gzip + base64url. */
export async function exportSyncCode(): Promise<string> {
  const { slip: _slip, ...rest } = state; void _slip;
  const bytes = new TextEncoder().encode(JSON.stringify(rest));
  let out: Uint8Array = bytes;
  if (typeof CompressionStream !== 'undefined') {
    out = new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
  }
  let bin = ''; for (let i = 0; i < out.length; i++) bin += String.fromCharCode(out[i]);
  return (typeof CompressionStream !== 'undefined' ? 'BP1' : 'BP0') + btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export async function importSyncCode(code: string): Promise<void> {
  const c = code.trim();
  const kind = c.slice(0, 3);
  if (kind !== 'BP1' && kind !== 'BP0') throw new Error('cod invalid');
  const b64 = c.slice(3).replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(b64 + '==='.slice((b64.length + 3) % 4));
  const bytes = Uint8Array.from(bin, (ch) => ch.charCodeAt(0));
  const txt = kind === 'BP1'
    ? await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text()
    : new TextDecoder().decode(bytes);
  actions.importState(txt);
}
