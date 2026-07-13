import type { ClaudeVerdict, ClaudeAccumulator, ClaudeAccumulatorLeg } from '@/types/betpredict';

/** Mirrors MIN_LEG_ODDS in src/claude_analysis.py. */
const MIN_LEG_ODDS = 1.10;

function serializeLegs(legs: ClaudeVerdict[]): ClaudeAccumulatorLeg[] {
  return legs.map(leg => ({
    event_id: leg.event_id, home_team: leg.home_team, away_team: leg.away_team,
    league: leg.league, event_date: leg.event_date,
    market: leg.market, market_label: leg.market_label,
    odds: leg.odds as number, probability: leg.probability, rationale: leg.rationale,
    bookmaker: leg.bookmaker,
  }));
}

function makeTicket(
  eligible: ClaudeVerdict[], label: string, riskLevel: 'safe',
  minProb: number, minLegs: number, maxLegs: number,
): ClaudeAccumulator | null {
  const legs: ClaudeVerdict[] = [];
  for (const r of eligible) {
    if (r.probability < minProb) continue;
    if (legs.length >= maxLegs) break;
    legs.push(r);
  }
  if (legs.length < minLegs) return null;
  let combinedOdds = 1;
  let combinedProb = 1;
  for (const leg of legs) {
    combinedOdds *= leg.odds as number;
    combinedProb *= leg.probability / 100;
  }
  return {
    label, risk_level: riskLevel, legs: serializeLegs(legs),
    combined_odds: Math.round(combinedOdds * 100) / 100,
    combined_probability_pct: Math.round(combinedProb * 100 * 10000) / 10000,
  };
}

/** Bilet "de amuzament" — vezi make_longshot_ticket() în src/claude_analysis.py. */
function makeLongshotTicket(
  broadPool: ClaudeVerdict[], label: string, minTotalOdds: number, minLegs: number, maxLegs: number,
): ClaudeAccumulator | null {
  const legs: ClaudeVerdict[] = [];
  let combinedOdds = 1;
  for (const r of broadPool) {
    if (legs.length >= maxLegs) break;
    legs.push(r);
    combinedOdds *= r.odds as number;
    if (legs.length >= minLegs && combinedOdds >= minTotalOdds) break;
  }
  if (legs.length < minLegs || combinedOdds < minTotalOdds) return null;
  let combinedProb = 1;
  for (const leg of legs) combinedProb *= leg.probability / 100;
  return {
    label, risk_level: 'longshot', legs: serializeLegs(legs),
    combined_odds: Math.round(combinedOdds * 100) / 100,
    combined_probability_pct: Math.round(combinedProb * 100 * 10000) / 10000,
  };
}

/** Mirrors build_accumulators() in src/claude_analysis.py — folosit pentru regenerarea
 * client-side a biletelor când utilizatorul alege o perioadă mai scurtă decât fereastra
 * completă analizată de backend (fără niciun apel Claude nou, doar aritmetică locală). */
export function buildAccumulators(results: ClaudeVerdict[]): ClaudeAccumulator[] {
  const eligible = results.filter(r => r.accumulator_eligible && r.odds)
    .sort((a, b) => b.probability - a.probability);
  const broadPool = results.filter(r => r.odds && (r.odds as number) >= MIN_LEG_ODDS)
    .sort((a, b) => b.probability - a.probability);

  const tickets: ClaudeAccumulator[] = [];
  const seen = new Set<string>();
  const addTicket = (t: ClaudeAccumulator | null) => {
    if (!t) return;
    const key = t.legs.map(l => String(l.event_id)).sort().join(',');
    if (seen.has(key)) return;
    seen.add(key);
    tickets.push(t);
  };

  addTicket(makeTicket(eligible, 'Maxim sigur', 'safe', 85, 2, 3));
  addTicket(makeTicket(eligible, 'Sigur', 'safe', 78, 4, 6));
  addTicket(makeLongshotTicket(broadPool, 'Long shot x100', 100, 15, 30));
  addTicket(makeLongshotTicket(broadPool, 'Long shot x500', 500, 20, 35));

  return tickets;
}
