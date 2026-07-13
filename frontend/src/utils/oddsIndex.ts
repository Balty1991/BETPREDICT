import type { OddsBucket } from '@/types/betpredict';

interface BestOddsOutcome {
  outcome?: string;
  bookmaker_name?: string;
}

export interface BestOddsRow {
  event_id?: number | string;
  market?: string;
  home_odds?: number; draw_odds?: number; away_odds?: number;
  home_bookmaker?: string; draw_bookmaker?: string; away_bookmaker?: string;
  over_odds?: number; under_odds?: number;
  yes_odds?: number; no_odds?: number;
  best_odds?: BestOddsOutcome[];
}

/** Mirrors build_odds_index() in src/claude_analysis.py. */
export function buildOddsIndex(rows: BestOddsRow[]): Map<string, OddsBucket> {
  const idx = new Map<string, OddsBucket>();

  const bkFor = (row: BestOddsRow, outcome: string): string | undefined =>
    row.best_odds?.find(o => (o.outcome ?? '').toLowerCase() === outcome)?.bookmaker_name;

  for (const row of rows) {
    if (row.event_id == null) continue;
    const eid = String(row.event_id);
    const bucket = idx.get(eid) ?? {};

    if (row.market === '1x2') {
      if (row.home_odds) { bucket.odds_home = row.home_odds; bucket.bk_home = row.home_bookmaker ?? bkFor(row, 'home'); }
      if (row.draw_odds) { bucket.odds_draw = row.draw_odds; bucket.bk_draw = row.draw_bookmaker ?? bkFor(row, 'draw'); }
      if (row.away_odds) { bucket.odds_away = row.away_odds; bucket.bk_away = row.away_bookmaker ?? bkFor(row, 'away'); }
    } else if (row.market === 'over_under_15' || row.market === 'over_under_25' || row.market === 'over_under_35') {
      const suffix = row.market.replace('over_under_', '');
      if (row.over_odds) { (bucket as Record<string, unknown>)[`odds_over_${suffix}`] = row.over_odds; (bucket as Record<string, unknown>)[`bk_over_${suffix}`] = bkFor(row, 'over'); }
      if (row.under_odds) { (bucket as Record<string, unknown>)[`odds_under_${suffix}`] = row.under_odds; (bucket as Record<string, unknown>)[`bk_under_${suffix}`] = bkFor(row, 'under'); }
    } else if (row.market === 'btts') {
      const yes = row.over_odds ?? row.yes_odds;
      const no = row.under_odds ?? row.no_odds;
      if (yes) { bucket.odds_btts_yes = yes; bucket.bk_btts_yes = bkFor(row, 'yes') ?? bkFor(row, 'over'); }
      if (no) { bucket.odds_btts_no = no; bucket.bk_btts_no = bkFor(row, 'no') ?? bkFor(row, 'under'); }
    }
    idx.set(eid, bucket);
  }
  return idx;
}

function noVigPair(o1?: number, o2?: number): number | null {
  if (!o1 || !o2 || o1 < 1.01 || o2 < 1.01) return null;
  const implied = 1 / o1 + 1 / o2;
  return implied > 0 ? Math.round((1 / implied) * 1000) / 1000 : null;
}

const DIRECT_ODDS_KEY: Record<string, keyof OddsBucket> = {
  home_win: 'odds_home', draw: 'odds_draw', away_win: 'odds_away',
  over_15: 'odds_over_15', under_15: 'odds_under_15',
  over_25: 'odds_over_25', under_25: 'odds_under_25',
  over_35: 'odds_over_35', under_35: 'odds_under_35',
  btts_yes: 'odds_btts_yes', btts_no: 'odds_btts_no',
};
const DIRECT_BK_KEY: Record<string, keyof OddsBucket> = {
  home_win: 'bk_home', draw: 'bk_draw', away_win: 'bk_away',
  over_15: 'bk_over_15', under_15: 'bk_under_15',
  over_25: 'bk_over_25', under_25: 'bk_under_25',
  over_35: 'bk_over_35', under_35: 'bk_under_35',
  btts_yes: 'bk_btts_yes', btts_no: 'bk_btts_no',
};

export function marketOddsFor(bucket: OddsBucket | undefined, market: string): number | null {
  if (!bucket) return null;
  if (market in DIRECT_ODDS_KEY) return (bucket[DIRECT_ODDS_KEY[market]] as number | undefined) ?? null;
  if (market === 'double_chance_1x') return noVigPair(bucket.odds_home, bucket.odds_draw);
  if (market === 'double_chance_x2') return noVigPair(bucket.odds_draw, bucket.odds_away);
  if (market === 'double_chance_12') return noVigPair(bucket.odds_home, bucket.odds_away);
  return null;
}

export function marketBookmakerFor(bucket: OddsBucket | undefined, market: string): string | null {
  if (!bucket || !(market in DIRECT_BK_KEY)) return null;
  return (bucket[DIRECT_BK_KEY[market]] as string | undefined) ?? null;
}
