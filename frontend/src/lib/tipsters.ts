import { getJSON } from './fetcher';

/** api/supersocial/tipsters.json: biletele tipsterilor transcrise din Supersocial, puse lângă robot. */
export type TipLeg = { home: string; away: string; kickoff_utc?: string; key: string; label: string; odds: number; result: string;
  match_id: number | null; robot_p: number | null; robot_odds: number | null; corners: number | null; corners_ours: number | null; stat?: string | null };
export type TipTicket = { id: string; tipster: string; date: string; n: number; odds: number; status: string;
  p_market: number; p_robot: number | null; matched: number; robot_seen: number; legs: TipLeg[] };
export type TipMarket = { key: string; label: string; n: number; won: number; hit: number | null; implied: number | null; robot_p: number | null; robot_n: number };
export type TipDoc = { generated_at?: string; tickets: TipTicket[]; markets: TipMarket[];
  summary: { tickets: number; won: number; lost: number; only_wins: boolean };
  data_check?: { compared: number; mismatches: Array<{ home: string; away: string; their: number; ours: number }> } };

export const loadTipsters = () => getJSON<TipDoc>('api/supersocial/tipsters.json');
/** „o dată la ~483 bilete” */
export const oneIn = (p: number) => (p > 0 ? Math.round(1 / p).toLocaleString('ro-RO') : '—');
