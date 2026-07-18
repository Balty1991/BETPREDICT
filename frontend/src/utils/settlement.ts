export type SettlementOutcome = 'won' | 'lost';

/** Decide win/loss for a saved market pick given the final score of its match. */
export function settleMarket(market: string, homeScore: number, awayScore: number): SettlementOutcome {
  const total = homeScore + awayScore;
  const btts = homeScore > 0 && awayScore > 0;
  switch (market) {
    case 'home_win': return homeScore > awayScore ? 'won' : 'lost';
    case 'draw': return homeScore === awayScore ? 'won' : 'lost';
    case 'away_win': return awayScore > homeScore ? 'won' : 'lost';
    case 'double_chance_1x': return homeScore >= awayScore ? 'won' : 'lost';
    case 'double_chance_x2': return awayScore >= homeScore ? 'won' : 'lost';
    case 'double_chance_12': return homeScore !== awayScore ? 'won' : 'lost';
    case 'over_15': return total > 1.5 ? 'won' : 'lost';
    case 'under_15': return total < 1.5 ? 'won' : 'lost';
    case 'over_25': return total > 2.5 ? 'won' : 'lost';
    case 'under_25': return total < 2.5 ? 'won' : 'lost';
    case 'over_35': return total > 3.5 ? 'won' : 'lost';
    case 'under_35': return total < 3.5 ? 'won' : 'lost';
    case 'btts_yes': return btts ? 'won' : 'lost';
    case 'btts_no': return !btts ? 'won' : 'lost';
    default: return 'lost';
  }
}

/** Profit in units for a flat 1-unit stake per pick. */
export function profitUnits(status: 'won' | 'lost', odds: number): number {
  return status === 'won' ? odds - 1 : -1;
}

export interface FinishedResult {
  status: string;
  home_score: number | null;
  away_score: number | null;
}

/**
 * Settle a whole accumulator: lost the moment any single leg loses (matches how bookmakers
 * settle combos — no point waiting for the rest), pending until every leg has finished,
 * won only if every leg won.
 */
export function settleTicket(
  legs: Array<{ event_id: number | string; market: string }>,
  resultsByEvent: Map<string, FinishedResult>
): 'pending' | 'won' | 'lost' {
  let anyPending = false;
  for (const leg of legs) {
    const res = resultsByEvent.get(String(leg.event_id));
    if (!res || res.status !== 'finished' || res.home_score == null || res.away_score == null) {
      anyPending = true;
      continue;
    }
    if (settleMarket(leg.market, res.home_score, res.away_score) === 'lost') return 'lost';
  }
  return anyPending ? 'pending' : 'won';
}

/**
 * Decontare individuala per picior — spre deosebire de settleTicket (care da doar
 * verdictul agregat), asta arata exact ce s-a intamplat la fiecare meci din bilet,
 * inclusiv cand biletul intreg e inca "pending" (unele picioare pot fi deja WIN/LOSS
 * inainte ca ultimul meci sa se termine).
 */
export function settleLegDetail(
  leg: { event_id: number | string; market: string },
  resultsByEvent: Map<string, FinishedResult>
): { status: 'pending' | 'won' | 'lost'; final_score?: string } {
  const res = resultsByEvent.get(String(leg.event_id));
  if (!res || res.status !== 'finished' || res.home_score == null || res.away_score == null) {
    return { status: 'pending' };
  }
  return {
    status: settleMarket(leg.market, res.home_score, res.away_score),
    final_score: `${res.home_score}-${res.away_score}`,
  };
}
