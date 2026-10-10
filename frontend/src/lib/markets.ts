import type { LegResult, Prediction } from './types';

/** Cheie compactă de piață, conform contractului: 1x2, over_under_2.5 etc. */
export function marketKey(market: string, line: number | null | undefined): string {
  if (line == null || Number.isNaN(line)) return market;
  return `${market}_${Number(line)}`;
}

/** Grupuri de filtre afișate în pagina Predicții. */
export const MARKET_GROUPS: Array<{ id: string; label: string; match: (p: Pick<Prediction, 'market' | 'line'>) => boolean }> = [
  { id: 'all', label: 'Toate', match: () => true },
  { id: '1x2', label: '1X2', match: (p) => p.market === '1x2' },
  { id: 'double_chance', label: 'Șansă dublă', match: (p) => p.market === 'double_chance' },
  { id: 'draw_no_bet', label: 'DNB', match: (p) => p.market === 'draw_no_bet' },
  { id: 'ou15', label: 'Goluri 1.5', match: (p) => p.market === 'over_under' && p.line === 1.5 },
  { id: 'ou25', label: 'Goluri 2.5', match: (p) => p.market === 'over_under' && p.line === 2.5 },
  { id: 'ou35', label: 'Goluri 3.5', match: (p) => p.market === 'over_under' && p.line === 3.5 },
  { id: 'ou_other', label: 'Goluri (alte linii)', match: (p) => p.market === 'over_under' && ![1.5, 2.5, 3.5].includes(Number(p.line)) },
  { id: 'btts', label: 'GG/NG', match: (p) => p.market === 'btts' },
  { id: 'other', label: 'Altele (HT, AH, cornere)', match: (p) => !['1x2', 'double_chance', 'draw_no_bet', 'over_under', 'btts'].includes(p.market) },
];

const ORDER = ['1x2', 'double_chance', 'draw_no_bet', 'over_under_0.5', 'over_under_1.5', 'over_under_2.5', 'over_under_3.5', 'over_under_4.5', 'btts'];
/** Ordinea canonică a piețelor în pagini (1X2 → DC → DNB → goluri → GG → restul). */
export function marketOrder(key: string): number { const i = ORDER.indexOf(key); return i === -1 ? 100 + key.charCodeAt(0) : i; }

export function selectionLabel(market: string, line: number | null, selection: string): string {
  const s = selection.toUpperCase();
  switch (market) {
    case '1x2': return s === 'HOME' ? '1' : s === 'DRAW' ? 'X' : s === 'AWAY' ? '2' : s;
    case 'double_chance': return s;
    case 'draw_no_bet': return s === 'HOME' ? 'DNB 1' : 'DNB 2';
    case 'over_under': return `${s === 'OVER' ? 'Peste' : 'Sub'} ${line}`;
    case 'btts': return s === 'YES' ? 'GG (ambele marchează)' : 'NG';
    case 'corners': return `Cornere ${s === 'OVER' ? 'peste' : 'sub'} ${line}`;
    default: return `${market} ${line ?? ''} ${selection}`.trim();
  }
}

/** Etichetă în română clară pentru o selecție de bilet, ex. „Ambele nu marchează (NG)”. */
export function plainPick(market: string, line: number | null | undefined, selection: string, fallback?: string): string {
  const s = (selection || '').toUpperCase();
  const ln = line == null ? '' : String(Number(line));
  switch (market) {
    case '1x2':
      if (s === 'HOME' || s === '1') return 'Victorie gazde (1)';
      if (s === 'DRAW' || s === 'X') return 'Egal (X)';
      if (s === 'AWAY' || s === '2') return 'Victorie oaspeți (2)';
      break;
    case 'double_chance':
      if (s === '1X') return 'Gazdele nu pierd (1X)';
      if (s === 'X2') return 'Oaspeții nu pierd (X2)';
      if (s === '12') return 'Nu se termină egal (12)';
      break;
    case 'draw_no_bet':
      if (s === 'HOME') return 'Gazdele câștigă, egal = anulat (DNB 1)';
      if (s === 'AWAY') return 'Oaspeții câștigă, egal = anulat (DNB 2)';
      break;
    case 'over_under':
      if (s === 'OVER') return `Peste ${ln} goluri în meci`;
      if (s === 'UNDER') return `Sub ${ln} goluri în meci`;
      break;
    case 'btts':
      if (s === 'YES') return 'Ambele marchează (GG)';
      if (s === 'NO') return 'Ambele nu marchează (NG)';
      break;
    case 'corners':
      if (s === 'OVER') return `Peste ${ln} cornere`;
      if (s === 'UNDER') return `Sub ${ln} cornere`;
      break;
  }
  return fallback || selectionLabel(market, line ?? null, selection);
}

export function marketTitle(key: string): string {
  if (key === '1x2') return 'Rezultat final (1X2)';
  if (key === 'double_chance') return 'Șansă dublă';
  if (key === 'draw_no_bet') return 'Egal = pariu anulat (DNB)';
  if (key === 'btts') return 'Ambele echipe marchează';
  const m = key.match(/^over_under_(.+)$/);
  if (m) return `Total goluri ${m[1]}`;
  const c = key.match(/^corners_(.+)$/);
  if (c) return `Cornere ${c[1]}`;
  // chei vechi din jurnal
  const legacy: Record<string, string> = {
    homeWin: '1 (gazde)', awayWin: '2 (oaspeți)', draw: 'X', over15: 'Peste 1.5', over25: 'Peste 2.5',
    over35: 'Peste 3.5', under25: 'Sub 2.5', under35: 'Sub 3.5', btts: 'GG', bttsNo: 'NG',
  };
  return legacy[key] ?? key;
}

/** Decontare a unei selecții pe scorul final. Piețele necunoscute rămân în așteptare (nu „pierdute”). */
export function settleSelection(market: string, line: number | null, selection: string, h: number, a: number): LegResult {
  const s = selection.toUpperCase();
  const total = h + a;
  switch (market) {
    case '1x2':
      if (s === 'HOME') return h > a ? 'won' : 'lost';
      if (s === 'DRAW') return h === a ? 'won' : 'lost';
      if (s === 'AWAY') return a > h ? 'won' : 'lost';
      return null;
    case 'double_chance':
      if (s === '1X') return h >= a ? 'won' : 'lost';
      if (s === 'X2') return a >= h ? 'won' : 'lost';
      if (s === '12') return h !== a ? 'won' : 'lost';
      return null;
    case 'draw_no_bet':
      if (h === a) return 'void';
      if (s === 'HOME') return h > a ? 'won' : 'lost';
      if (s === 'AWAY') return a > h ? 'won' : 'lost';
      return null;
    case 'over_under': {
      if (line == null) return null;
      if (total === line) return 'void';
      if (s === 'OVER') return total > line ? 'won' : 'lost';
      if (s === 'UNDER') return total < line ? 'won' : 'lost';
      return null;
    }
    case 'btts': {
      const both = h > 0 && a > 0;
      if (s === 'YES') return both ? 'won' : 'lost';
      if (s === 'NO') return !both ? 'won' : 'lost';
      return null;
    }
    default:
      return null;
  }
}

export const VOID_STATUSES = new Set(['postponed', 'cancelled', 'canceled', 'abandoned', 'suspended', 'interrupted']);
export const LIVE_STATUSES = new Set(['inprogress', '1st_half', '2nd_half', 'halftime', 'extra_time', 'penalties', 'live']);
export function isFinished(status?: string | null) { return status === 'finished' || status === 'ended' || status === 'ft'; }
export function isLive(status?: string | null) { return !!status && LIVE_STATUSES.has(status); }
export function statusLabel(status?: string | null): string {
  if (!status) return '';
  if (isFinished(status)) return 'Final';
  if (status === 'notstarted') return 'Urmează';
  if (isLive(status)) return 'Început'; // fără UI live: rezultatul apare după final
  if (VOID_STATUSES.has(status)) return 'Amânat/anulat';
  return status;
}

export function profitFor(result: LegResult | 'pending' | undefined, oddsV: number): number | null {
  switch (result) {
    case 'won': return oddsV - 1;
    case 'lost': return -1;
    case 'void': return 0;
    case 'half_won': return (oddsV - 1) / 2;
    case 'half_lost': return -0.5;
    default: return null;
  }
}

export function resultLabel(r: LegResult | 'pending' | undefined): string {
  switch (r) {
    case 'won': return 'Câștigat';
    case 'lost': return 'Pierdut';
    case 'void': return 'Anulat';
    case 'half_won': return '½ câștigat';
    case 'half_lost': return '½ pierdut';
    default: return 'În așteptare';
  }
}

/** Explicația selecției în limbaj simplu („Cel mult 3 goluri în meci”). */
export function pickHint(market: string, line: number | null | undefined, selection: string, home: string, away: string): string {
  const s = selection.toUpperCase();
  const l = Number(line ?? 0);
  switch (market) {
    case '1x2': return s === 'HOME' ? `Câștigă ${home}` : s === 'AWAY' ? `Câștigă ${away}` : 'Meciul se termină egal';
    case 'double_chance': return s === '1X' ? `${home} nu pierde` : s === 'X2' ? `${away} nu pierde` : s === '12' ? 'Nu se termină egal' : s;
    case 'draw_no_bet': return `Câștigă ${s === 'HOME' ? home : away} · la egal primești miza înapoi`;
    case 'over_under': return s === 'OVER' ? `Cel puțin ${Math.floor(l) + 1} ${Math.floor(l) + 1 === 1 ? 'gol' : 'goluri'} în meci` : Math.floor(l) === 0 ? 'Fără goluri în meci' : `Cel mult ${Math.floor(l)} ${Math.floor(l) === 1 ? 'gol' : 'goluri'} în meci`;
    case 'btts': return s === 'YES' ? 'Ambele echipe marchează' : 'Cel puțin o echipă nu marchează';
    default: return '';
  }
}

/** Meci început: după status SAU după ora de start (statusul din JSON poate întârzia până la următorul refresh). */
export function isStarted(m: { status?: string | null; kickoff_utc: string }) {
  return (m.status != null && m.status !== 'notstarted') || Date.parse(m.kickoff_utc) <= Date.now();
}
