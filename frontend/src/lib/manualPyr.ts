/** Piramida manuală: tu alegi selecțiile pe fiecare treaptă din oferta zilei (api/pyramid/manual_pool.json).
 *  Totul rămâne local (localStorage, ca Banca mea) și se decontează din api/pyramid/manual_results.json. */
import { getJSON } from './fetcher';

export type MPItem = {
  id: string; match_id: number; home: string; away: string; league?: string | null; kickoff_utc: string; market: string; selection: string;
  label: string; odds: number; p: number; ev: number; src: string; group: 0 | 1 | 2;
  rec?: { n: number; hit: number; roi: number } | null; lrec?: { n: number; hit: number; roi: number } | null;
  sb_event_id?: string | null; superbet_url?: string | null;
  sb_pick?: { market: string; outcome: string; ref?: string } | null; bb_picks?: Array<{ market: string; outcome: string; ref?: string }> | null;
};
export type MPLeg = MPItem & { result?: 'w' | 'l' | 'v' };
export type MPStep = { n: number; date: string; stake: number; legs: MPLeg[]; played?: boolean; ticketId?: string };
export type MPCycle = { date: string; steps: number; result: 'lost' | 'done' | 'reset'; payout: number; start: number };
export type ManualPyr = { id: string; name: string; created: string; start: number; steps: number; target: number; history: MPStep[]; cycles: MPCycle[] };
export type MPPool = { generated_at: string; date: string; items: MPItem[]; rules: string; pin_record?: { n: number; hit: number; roi: number } | null };

export const loadManualPool = () => getJSON<MPPool>('api/pyramid/manual_pool.json');
export const loadManualResults = async () => (await getJSON<{ results: Record<string, 'w' | 'l' | 'v'> }>('api/pyramid/manual_results.json'))?.results ?? {};

export function legResult(l: MPLeg, res: Record<string, 'w' | 'l' | 'v'>, ss: Record<string, Record<string, 'w' | 'l' | 'v'>>): 'w' | 'l' | 'v' | undefined {
  return res[l.id] ?? (l.market === 'ss|0' ? ss[String(l.match_id)]?.[l.selection] : undefined) ?? l.result;
}

/** won / lost / pending pentru o treaptă + cota efectivă (selecțiile anulate ies din cotă). */
export function stepStatus(s: MPStep, res: Record<string, 'w' | 'l' | 'v'>, ss: Record<string, Record<string, 'w' | 'l' | 'v'>>) {
  const rs = s.legs.map((l) => legResult(l, res, ss));
  const odds = s.legs.reduce((a, l, i) => a * (rs[i] === 'v' ? 1 : l.odds), 1);
  const status: 'won' | 'lost' | 'pending' = rs.includes('l') ? 'lost' : rs.every((r) => r === 'w' || r === 'v') ? 'won' : 'pending';
  return { status, odds, rs, settled: rs.filter(Boolean).length };
}

export const combo = (legs: { odds: number; p: number }[]) => {
  const odds = legs.reduce((a, l) => a * l.odds, 1), p = legs.reduce((a, l) => a * l.p, 1);
  return { odds, p, ev: legs.length ? p * odds - 1 : 0 };
};

/** Starea curentă: treapta următoare și miza ei (= câștigul treptei anterioare). */
export function pyrState(mp: ManualPyr, res: Record<string, 'w' | 'l' | 'v'>, ss: Record<string, Record<string, 'w' | 'l' | 'v'>>) {
  const st = mp.history.map((s) => ({ s, ...stepStatus(s, res, ss) }));
  const last = st[st.length - 1];
  let phase: 'build' | 'pending' | 'lost' | 'done' = 'build';
  let stake = mp.start;
  if (last) {
    if (last.status === 'pending') phase = 'pending';
    else if (last.status === 'lost') phase = 'lost';
    else { stake = Math.round(last.s.stake * last.odds * 100) / 100; phase = st.length >= mp.steps ? 'done' : 'build'; }
  }
  return { st, phase, stake, next: st.length + 1, payout: phase === 'done' ? stake : 0 };
}

/** Selecțiile treptei ca picioare de bilet (cu id-urile Superbet, ca butonul „Superbet” să precompleteze biletul).
 *  Selecțiile salvate înainte de id-uri le iau din oferta zilei, dacă se mai găsesc acolo. */
export function ticketLegs(legs: MPLeg[], pool?: MPItem[] | null) {
  const by = new Map((pool ?? []).map((x) => [x.id, x]));
  return legs.map((l) => {
    const q = by.get(l.id);
    return {
      match_id: l.match_id, home: l.home, away: l.away, league: l.league ?? undefined, kickoff_utc: l.kickoff_utc, market: l.market, line: null,
      selection: l.selection, label: l.label, odds: l.odds, p: l.p, odds_source: 'superbet',
      sb_event_id: l.sb_event_id ?? q?.sb_event_id ?? null, superbet_url: l.superbet_url ?? q?.superbet_url ?? null,
      sb_pick: l.sb_pick ?? q?.sb_pick ?? null, bb_picks: l.bb_picks ?? q?.bb_picks ?? null,
    };
  });
}
