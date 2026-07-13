// ── Raw, unfiltered API events (events_window.json) ──────────────────────────
export interface RawEvent {
  id: number | string;
  event_id: number | string;
  league_id?: number | null;
  league_name?: string | null;
  home_team_id?: number | null;
  away_team_id?: number | null;
  home_team: string;
  away_team: string;
  home_coach_id?: number | null;
  away_coach_id?: number | null;
  referee_id?: number | null;
  venue_id?: number | null;
  event_date: string;
  status: string;
  home_score?: number | null;
  away_score?: number | null;
  home_score_ht?: number | null;
  away_score_ht?: number | null;
  is_local_derby?: boolean;
  is_neutral_ground?: boolean;
  weather_context?: {
    code?: number;
    label?: string;
    icon?: string;
    wind_speed?: number;
    temperature_c?: number;
    pitch_condition?: string | null;
  } | null;
  image_assets?: {
    home_team_logo?: string;
    away_team_logo?: string;
    league_logo?: string;
    venue_photo?: string;
    home_manager_photo?: string;
    away_manager_photo?: string;
  } | null;
}

// ── BSD prediction engine output (predictions.json) ──────────────────────────
export interface PredictionRow {
  id: number | string;
  created_at?: string;
  event: {
    id: number | string;
    event_date?: string;
    status?: string;
    home_team_id?: number;
    home_team?: string;
    away_team_id?: number;
    away_team?: string;
    league_id?: number;
    league_name?: string;
  };
  markets?: {
    match_result?: { prob_home?: number; prob_draw?: number; prob_away?: number; predicted?: string };
    expected_goals?: { home?: number; away?: number };
    over_under?: { prob_over_15?: number; prob_over_25?: number; prob_over_35?: number };
    btts?: { prob_yes?: number };
    score?: { most_likely?: string };
  };
}

// ── Local (free, non-AI) odds index + quick-take pick, mirrors src/claude_analysis.py ──
export interface OddsBucket {
  odds_home?: number; odds_draw?: number; odds_away?: number;
  odds_over_15?: number; odds_under_15?: number;
  odds_over_25?: number; odds_under_25?: number;
  odds_over_35?: number; odds_under_35?: number;
  odds_btts_yes?: number; odds_btts_no?: number;
  odds_double_chance_1x?: number; odds_double_chance_x2?: number; odds_double_chance_12?: number;
  bk_home?: string; bk_draw?: string; bk_away?: string;
  bk_over_15?: string; bk_under_15?: string;
  bk_over_25?: string; bk_under_25?: string;
  bk_over_35?: string; bk_under_35?: string;
  bk_btts_yes?: string; bk_btts_no?: string;
  bk_double_chance_1x?: string; bk_double_chance_x2?: string; bk_double_chance_12?: string;
}

export interface LocalPick {
  market: string;
  market_label: string;
  probability: number;
  xg_home?: number | null;
  xg_away?: number | null;
  odds?: number | null;
  odds_is_market?: boolean;
  bookmaker?: string | null;
  fair_odds?: number | null;
  edge_pp?: number | null;
  value_pct?: number | null;
}

export interface TeamFormEntry {
  form_score?: number;
  form_string?: string;
  avg_goals_scored_last5?: number;
  avg_goals_conceded_last5?: number;
  btts_last5?: number;
  over15_pct?: number;
  over25_pct?: number;
  wins?: number;
  draws?: number;
  losses?: number;
  sample?: number;
  source?: string;
}

export interface H2HEntry {
  event_id: number | string;
  sample?: number;
  home_wins?: number;
  away_wins?: number;
  draws?: number;
  avg_goals?: number;
  over15_pct?: number;
  over25_pct?: number;
  btts_pct?: number;
  matches?: Array<{
    event_date?: string;
    home_team?: string;
    away_team?: string;
    league?: string;
    score?: string;
    status?: string;
  }>;
}

export interface LeagueInfo {
  id: number;
  name: string;
  country?: string;
  league_logo?: string;
}

export interface LineupPlayer {
  id: number;
  name: string;
  short_name?: string;
  position?: string;
  jersey_number?: number;
  ai_score?: number;
}

export interface EventLineups {
  lineup_status?: string;
  lineups?: {
    home?: { team_id?: number; team_name?: string; formation?: string; confidence?: number; players?: LineupPlayer[] };
    away?: { team_id?: number; team_name?: string; formation?: string; confidence?: number; players?: LineupPlayer[] };
  };
}

// ── Claude AI analysis (data/claude_predictions.json + claude_accumulators.json) ─
export interface ClaudeVerdictForm {
  form?: string | null;
  avg_scored?: number | null;
  avg_conceded?: number | null;
  over25_pct?: number | null;
  btts_pct?: number | null;
}

export interface ClaudeVerdictH2H {
  sample?: number | null;
  home_wins?: number | null;
  away_wins?: number | null;
  draws?: number | null;
  avg_goals?: number | null;
  btts_pct?: number | null;
  last_matches?: Array<{ date?: string; home?: string; away?: string; score?: string }> | null;
}

export interface ClaudeVerdictWeather {
  label?: string | null;
  temperature_c?: number | null;
  wind_speed?: number | null;
}

export interface ClaudeVerdict {
  event_id: number | string;
  home_team: string;
  away_team: string;
  league?: string;
  event_date?: string;
  market: string;
  market_label: string;
  probability: number;
  risk_tier: 'foarte_sigur' | 'sigur' | 'moderat' | 'riscant' | string;
  rationale: string;
  accumulator_eligible: boolean;
  odds?: number | null;
  odds_is_market?: boolean;
  bookmaker?: string | null;
  fair_odds?: number | null;
  edge_pp?: number | null;
  value_pct?: number | null;
  is_local_derby?: boolean | null;
  weather?: ClaudeVerdictWeather | null;
  form_home?: ClaudeVerdictForm | null;
  form_away?: ClaudeVerdictForm | null;
  h2h?: ClaudeVerdictH2H | null;
}

export interface ClaudeAccumulatorLeg {
  event_id: number | string;
  home_team: string;
  away_team: string;
  league?: string;
  event_date?: string;
  market: string;
  market_label: string;
  odds: number;
  probability: number;
  rationale: string;
  bookmaker?: string | null;
}

export interface ClaudeAccumulator {
  label: string;
  risk_level?: 'safe' | 'longshot';
  legs: ClaudeAccumulatorLeg[];
  combined_odds: number;
  combined_probability_pct: number;
}

// ── Personal placed-ticket journal (localStorage, client-side only) ──
export type SavedPredictionStatus = 'pending' | 'won' | 'lost';

export interface SavedTicketLeg {
  event_id: number | string;
  home_team: string;
  away_team: string;
  league?: string;
  event_date?: string;
  market: string;
  market_label: string;
  odds: number;
  probability: number;
}

export interface SavedTicket {
  id: string; // stable signature built from the leg set (event_id+market, sorted)
  label: string;
  risk_level?: 'safe' | 'longshot';
  legs: SavedTicketLeg[];
  combined_odds: number;
  combined_probability_pct: number;
  saved_at: string;
  status: SavedPredictionStatus;
  settled_at?: string;
}

// ── Personal saved-prediction journal (localStorage, client-side only) ──

export interface SavedPrediction {
  id: string; // `${event_id}_${market}`
  event_id: number | string;
  home_team: string;
  away_team: string;
  league?: string;
  event_date: string;
  market: string;
  market_label: string;
  probability: number;
  risk_tier: string;
  odds: number;
  odds_is_market?: boolean;
  saved_at: string;
  status: SavedPredictionStatus;
  settled_at?: string;
  final_score?: string;
}

export interface EventDeepInfo {
  lineups?: EventLineups;
  stats?: Record<string, unknown>;
  playerStats?: Record<string, unknown>;
}
