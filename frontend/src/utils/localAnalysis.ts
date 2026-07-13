import type { PredictionRow, OddsBucket, LocalPick } from '@/types/betpredict';
import { marketOddsFor, marketBookmakerFor } from './oddsIndex';

// Same keys/labels as MARKET_LABELS in src/claude_analysis.py.
const LOCAL_MARKET_LABELS: Record<string, string> = {
  home_win: 'Gazdă câștigă', draw: 'Egal', away_win: 'Oaspete câștigă',
  double_chance_1x: 'Șansă dublă 1X', double_chance_x2: 'Șansă dublă X2', double_chance_12: 'Șansă dublă 12',
  over_15: 'Over 1.5 goluri', under_15: 'Under 1.5 goluri',
  over_25: 'Over 2.5 goluri', under_25: 'Under 2.5 goluri',
  over_35: 'Over 3.5 goluri', under_35: 'Under 3.5 goluri',
  btts_yes: 'Ambele echipe marchează - Da', btts_no: 'Ambele echipe marchează - Nu',
};

interface Candidate { market: string; probability: number }

/**
 * Free, formula-only "quick take" for events Claude hasn't analyzed deeply — the same
 * math the backend uses (implied probability, no-vig double chance, edge vs market odds),
 * just picking whichever market has the strongest BSD signal. No AI call, zero cost.
 * over_15/under_35 are excluded on purpose: they're true for almost every match (nearly
 * every game has >1.5 goals, very few have >3.5), so they'd dominate the pick without
 * saying anything useful — same reasoning as best_bsd_signal() in claude_analysis.py.
 * under_15 and over_35 are the informative, rarer sides of those same two lines, so they
 * stay in the candidate pool.
 */
export function pickBestMarket(prediction?: PredictionRow, odds?: OddsBucket): LocalPick | null {
  const mr = prediction?.markets?.match_result;
  const ou = prediction?.markets?.over_under;
  const btts = prediction?.markets?.btts;
  const xg = prediction?.markets?.expected_goals;

  const candidates: Candidate[] = [];
  if (mr?.prob_home != null) candidates.push({ market: 'home_win', probability: mr.prob_home });
  if (mr?.prob_draw != null) candidates.push({ market: 'draw', probability: mr.prob_draw });
  if (mr?.prob_away != null) candidates.push({ market: 'away_win', probability: mr.prob_away });
  if (mr?.prob_home != null && mr?.prob_draw != null) candidates.push({ market: 'double_chance_1x', probability: mr.prob_home + mr.prob_draw });
  if (mr?.prob_draw != null && mr?.prob_away != null) candidates.push({ market: 'double_chance_x2', probability: mr.prob_draw + mr.prob_away });
  if (mr?.prob_home != null && mr?.prob_away != null) candidates.push({ market: 'double_chance_12', probability: mr.prob_home + mr.prob_away });
  if (ou?.prob_over_15 != null) {
    candidates.push({ market: 'under_15', probability: 100 - ou.prob_over_15 });
  }
  if (ou?.prob_over_25 != null) {
    candidates.push({ market: 'over_25', probability: ou.prob_over_25 });
    candidates.push({ market: 'under_25', probability: 100 - ou.prob_over_25 });
  }
  if (ou?.prob_over_35 != null) {
    candidates.push({ market: 'over_35', probability: ou.prob_over_35 });
  }
  if (btts?.prob_yes != null) {
    candidates.push({ market: 'btts_yes', probability: btts.prob_yes });
    candidates.push({ market: 'btts_no', probability: 100 - btts.prob_yes });
  }
  if (candidates.length === 0) return null;

  const best = candidates.reduce((a, b) => (b.probability > a.probability ? b : a));
  const marketOdds = marketOddsFor(odds, best.market);
  const bookmaker = marketOdds != null ? marketBookmakerFor(odds, best.market) : null;
  const fairOdds = best.probability > 0 ? Math.round((100 / best.probability) * 1000) / 1000 : null;

  let edgePp: number | null = null;
  let valuePct: number | null = null;
  if (marketOdds != null) {
    const impliedPct = 100 / marketOdds;
    edgePp = Math.round((best.probability - impliedPct) * 10) / 10;
    valuePct = Math.round(((best.probability / 100) * marketOdds * 100 - 100) * 10) / 10;
  }

  return {
    market: best.market,
    market_label: LOCAL_MARKET_LABELS[best.market] ?? best.market,
    probability: best.probability,
    xg_home: xg?.home ?? null,
    xg_away: xg?.away ?? null,
    odds: marketOdds ?? fairOdds,
    odds_is_market: marketOdds != null,
    bookmaker,
    fair_odds: fairOdds,
    edge_pp: edgePp,
    value_pct: valuePct,
  };
}
