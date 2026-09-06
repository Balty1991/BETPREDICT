import type { PredictionRow, OddsBucket, LocalPick } from '@/types/betpredict';
import { marketOddsFor, marketBookmakerFor } from './oddsIndex';
import {
  isBlacklistedMarket, isVolumeOver15,
  MIN_QUALIFIED_ODDS, MAX_QUALIFIED_ODDS, MIN_EDGE_PP,
} from './filters';

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
 * Edge v8: pick the market with the strongest edge inside the 1.50–3.30 window.
 * V7 picked highest probability → Over 1.5 / favorite @1.14. That's the −ROI machine.
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
    candidates.push({ market: 'over_15', probability: ou.prob_over_15 });
    candidates.push({ market: 'under_15', probability: 100 - ou.prob_over_15 });
  }
  if (ou?.prob_over_25 != null) {
    candidates.push({ market: 'over_25', probability: ou.prob_over_25 });
    candidates.push({ market: 'under_25', probability: 100 - ou.prob_over_25 });
  }
  if (ou?.prob_over_35 != null) {
    candidates.push({ market: 'over_35', probability: ou.prob_over_35 });
    candidates.push({ market: 'under_35', probability: 100 - ou.prob_over_35 });
  }
  if (btts?.prob_yes != null) {
    candidates.push({ market: 'btts_yes', probability: btts.prob_yes });
    candidates.push({ market: 'btts_no', probability: 100 - btts.prob_yes });
  }
  if (candidates.length === 0) return null;

  const scored = candidates.map((c) => {
    const marketOdds = marketOddsFor(odds, c.market);
    const bookmaker = marketOdds != null ? marketBookmakerFor(odds, c.market) : null;
    const fairOdds = c.probability > 0 ? Math.round((100 / c.probability) * 1000) / 1000 : null;
    const o = marketOdds ?? fairOdds;
    let edgePp: number | null = null;
    let valuePct: number | null = null;
    if (marketOdds != null) {
      const impliedPct = 100 / marketOdds;
      edgePp = Math.round((c.probability - impliedPct) * 10) / 10;
      valuePct = Math.round(((c.probability / 100) * marketOdds * 100 - 100) * 10) / 10;
    }
    const pass = o != null
      && o >= MIN_QUALIFIED_ODDS && o <= MAX_QUALIFIED_ODDS
      && !isBlacklistedMarket(c.market)
      && !isVolumeOver15(c.market, o)
      && (edgePp == null || edgePp >= MIN_EDGE_PP);
    return { ...c, marketOdds, bookmaker, fairOdds, o, edgePp, valuePct, pass };
  });

  const passing = scored.filter((s) => s.pass).sort((a, b) => (b.edgePp ?? -999) - (a.edgePp ?? -999));
  const windowed = scored
    .filter((s) => s.o != null && s.o >= MIN_QUALIFIED_ODDS && s.o <= MAX_QUALIFIED_ODDS
      && !isBlacklistedMarket(s.market) && !isVolumeOver15(s.market, s.o))
    .sort((a, b) => (b.edgePp ?? -999) - (a.edgePp ?? -999));
  const best = passing[0] ?? windowed[0] ?? scored.reduce((a, b) => (b.probability > a.probability ? b : a));

  return {
    market: best.market,
    market_label: LOCAL_MARKET_LABELS[best.market] ?? best.market,
    probability: best.probability,
    xg_home: xg?.home ?? null,
    xg_away: xg?.away ?? null,
    odds: best.o ?? best.fairOdds,
    odds_is_market: best.marketOdds != null,
    bookmaker: best.bookmaker,
    fair_odds: best.fairOdds,
    edge_pp: best.edgePp,
    value_pct: best.valuePct,
  };
}
