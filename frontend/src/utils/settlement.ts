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
