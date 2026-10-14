import type { JournalRow, Match, Prediction, Ticket } from './types';
import { isFinished, isStarted, VOID_STATUSES } from './markets';

/** Calcule pentru panoul de pe Acasă. Fără React, ca să fie ușor de verificat. */

export type Scope = 'toate' | 'p80' | 'rec';

export interface DayPerf {
  date: string;
  n: number; won: number; lost: number; void: number; pending: number;
  /** câștigate / (câștigate + pierdute) */
  winRate: number | null;
  /** profit / miză, doar pe selecțiile decontate care au avut cotă (1u fiecare) */
  roi: number | null;
  profit: number;
  staked: number;
}

const WON = new Set(['won', 'half_won']);
const LOST = new Set(['lost', 'half_lost']);

export function inScope(r: JournalRow, s: Scope): boolean {
  if (s === 'p80') return (r.p ?? 0) >= 0.8;
  if (s === 'rec') return r.source === 'recomandată';
  return true;
}

export function perfOf(date: string, rows: JournalRow[]): DayPerf {
  const d: DayPerf = { date, n: rows.length, won: 0, lost: 0, void: 0, pending: 0, winRate: null, roi: null, profit: 0, staked: 0 };
  for (const r of rows) {
    if (r.result === 'pending' || r.result == null) d.pending += 1;
    else if (WON.has(r.result)) d.won += 1;
    else if (LOST.has(r.result)) d.lost += 1;
    else d.void += 1;
    if (r.result !== 'pending' && r.result != null && r.profit != null && r.odds) { d.profit += r.profit; d.staked += 1; }
  }
  d.winRate = d.won + d.lost ? d.won / (d.won + d.lost) : null;
  d.roi = d.staked ? d.profit / d.staked : null;
  return d;
}

/** Performanța pe fiecare zi cerută (zilele fără rânduri apar cu n = 0). */
export function perfByDay(rows: JournalRow[], dates: string[], scope: Scope): DayPerf[] {
  const by = new Map<string, JournalRow[]>();
  for (const r of rows) if (inScope(r, scope)) { const l = by.get(r.date) ?? []; l.push(r); by.set(r.date, l); }
  return dates.map((d) => perfOf(d, by.get(d) ?? []));
}

export function sumPerf(days: DayPerf[]): DayPerf {
  const t: DayPerf = { date: '', n: 0, won: 0, lost: 0, void: 0, pending: 0, winRate: null, roi: null, profit: 0, staked: 0 };
  for (const d of days) { t.n += d.n; t.won += d.won; t.lost += d.lost; t.void += d.void; t.pending += d.pending; t.profit += d.profit; t.staked += d.staked; }
  t.winRate = t.won + t.lost ? t.won / (t.won + t.lost) : null;
  t.roi = t.staked ? t.profit / t.staked : null;
  return t;
}

export interface TodayPulse {
  matches: number; live: number; upcoming: number; finished: number;
  preds: number; available: number; p80: number; p80Available: number; rec: number; value: number;
  /** câte predicții pe fiecare piață */
  markets: Array<{ key: string; label: string; n: number }>;
  /** câte predicții în fiecare treaptă de șansă */
  bands: Array<{ key: string; n: number }>;
  /** câte meciuri încep în fiecare oră (ora României) */
  hours: Array<{ h: number; n: number }>;
  next: Match | null;
  top: Array<{ m: Match; p: Prediction }>;
  settled: { won: number; lost: number };
}

const MARKET_LABEL: Record<string, string> = { over_under: 'Goluri', double_chance: 'Șansă dublă', btts: 'GG / NG', draw_no_bet: 'Egal anulat', '1x2': '1X2', corners: 'Cornere' };
const BANDS: Array<[string, number, number]> = [['<50', 0, 0.5], ['50+', 0.5, 0.6], ['60+', 0.6, 0.7], ['70+', 0.7, 0.8], ['80+', 0.8, 0.9], ['90+', 0.9, 1.01]];
const hourFmt = new Intl.DateTimeFormat('ro-RO', { timeZone: 'Europe/Bucharest', hour: '2-digit', hourCycle: 'h23' });

export function todayPulse(matches: Match[], isRec: (p: Prediction) => boolean): TodayPulse {
  const out: TodayPulse = { matches: matches.length, live: 0, upcoming: 0, finished: 0, preds: 0, available: 0, p80: 0, p80Available: 0, rec: 0, value: 0, markets: [], bands: BANDS.map(([key]) => ({ key, n: 0 })), hours: [], next: null, top: [], settled: { won: 0, lost: 0 } };
  const mk = new Map<string, number>();
  const hours = new Map<number, number>();
  const top: Array<{ m: Match; p: Prediction }> = [];
  for (const m of matches) {
    const started = isStarted(m);
    if (isFinished(m.status)) out.finished += 1;
    else if (started && !VOID_STATUSES.has(m.status)) out.live += 1;
    else if (!started) {
      out.upcoming += 1;
      if (!out.next || Date.parse(m.kickoff_utc) < Date.parse(out.next.kickoff_utc)) out.next = m;
    }
    const t = Date.parse(m.kickoff_utc);
    if (Number.isFinite(t)) { const h = Number(hourFmt.format(t)); hours.set(h, (hours.get(h) ?? 0) + 1); }
    let best: Prediction | null = null;
    for (const p of m.predictions) {
      out.preds += 1;
      if (!started) out.available += 1;
      if (p.p >= 0.8) { out.p80 += 1; if (!started) out.p80Available += 1; }
      if (isRec(p)) out.rec += 1;
      if (p.value || (p.ev ?? 0) > 0) out.value += 1;
      if (p.result === 'won' || p.result === 'half_won') out.settled.won += 1;
      else if (p.result === 'lost' || p.result === 'half_lost') out.settled.lost += 1;
      mk.set(p.market, (mk.get(p.market) ?? 0) + 1);
      const b = BANDS.findIndex(([, lo, hi]) => p.p >= lo && p.p < hi);
      if (b >= 0) out.bands[b].n += 1;
      // pentru „cele mai sigure”: doar cu cotă reală și peste 1.15, altfel sus ar sta mereu „Peste 0.5”
      if (!started && p.odds != null && p.odds >= 1.15 && (!best || p.p > best.p)) best = p;
    }
    if (best && best.p >= 0.7) top.push({ m, p: best });
  }
  out.markets = [...mk.entries()].map(([key, n]) => ({ key, label: MARKET_LABEL[key] ?? key, n })).sort((a, b) => b.n - a.n);
  out.hours = [...hours.entries()].map(([h, n]) => ({ h, n })).sort((a, b) => a.h - b.h);
  out.top = top.sort((a, b) => b.p.p - a.p.p).slice(0, 5);
  return out;
}

export interface TicketDay { date: string; n: number; won: number; lost: number; pending: number }

export function ticketsByDay(tickets: Ticket[], dates: string[]): TicketDay[] {
  return dates.map((date) => {
    const ts = tickets.filter((t) => (t.date ?? t.created_at?.slice(0, 10)) === date);
    return {
      date, n: ts.length,
      won: ts.filter((t) => t.status === 'won').length,
      lost: ts.filter((t) => t.status === 'lost').length,
      pending: ts.filter((t) => !t.status || t.status === 'pending').length,
    };
  });
}
