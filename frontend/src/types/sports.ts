// Tipuri de date pentru API-ul BSD și predicții

export interface Team {
  id: number;
  name: string;
  country?: string;
  logo?: string;
}

export interface League {
  id: number;
  name: string;
  country: string;
  logo?: string;
}

export interface Event {
  id: number;
  home_team: Team;
  away_team: Team;
  league: League;
  start_time: string;
  status: 'upcoming' | 'live' | 'finished';
  home_score?: number;
  away_score?: number;
  minute?: number;
}

export interface OddsData {
  market: string;
  outcomes: {
    name: string;
    odds: number;
    probability?: number;
  }[];
  timestamp: string;
}

export interface MatchStats {
  home_possession: number;
  away_possession: number;
  home_shots: number;
  away_shots: number;
  home_shots_on_target: number;
  away_shots_on_target: number;
  home_corners: number;
  away_corners: number;
  home_fouls: number;
  away_fouls: number;
  home_yellow_cards: number;
  away_yellow_cards: number;
  home_red_cards: number;
  away_red_cards: number;
  home_xg?: number;
  away_xg?: number;
}

export interface StandingTeam {
  position: number;
  team_id: number;
  team_name: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  gd: number;
  pts: number;
  form: string;
  xgf?: number;
  xga?: number;
  xgd?: number;
}

export interface Prediction {
  event_id: number;
  home_team: string;
  away_team: string;
  league: string;
  match_date: string;
  market: string;
  selection: string;
  odds: number;
  probability: number;
  ev: number;
  kelly: number;
  score: number;
  grade: 'A+' | 'A' | 'B' | 'C' | 'D' | 'E';
  confidence: number;
  predicted_score?: string;
  rationale: string;
  is_premium: boolean;
  consensus_agreement?: number;
  poisson_prob?: number;
  elo_prob?: number;
  bsd_prob?: number;
  ml_prob?: number;
  calibration_state?: 'calibrated' | 'uncalibrated';
}

export interface MarketPerformance {
  market: string;
  win_rate: number;
  roi: number;
  bets_won: number;
  bets_lost: number;
  total_bets: number;
  brier_score: number;
  bias: number;
}

export interface SystemHealth {
  ml_ensemble: 'GREEN' | 'YELLOW' | 'RED';
  calibration: 'GREEN' | 'YELLOW' | 'RED';
  adaptive_thresholds: 'GREEN' | 'YELLOW' | 'RED';
  consensus: 'GREEN' | 'YELLOW' | 'RED';
  signals: 'GREEN' | 'YELLOW' | 'RED';
}

export interface DashboardKPI {
  signals_count: number;
  value_bets_count: number;
  predictions_count: number;
  win_rate: number;
  roi: number;
  brier_score: number;
}

export interface OddsMovement {
  event_id: number;
  match: string;
  market: string;
  selection: string;
  open_odds: number;
  current_odds: number;
  movement_pct: number;
  direction: 'up' | 'down';
  timestamp: string;
}

export interface PremiumCriteria {
  min_edge: number;
  min_consensus: number;
  min_smartbet_score: number;
  calibration_required: boolean;
  min_kelly: number;
  max_odds: number;
  grade_filter: ('A+' | 'A' | 'B')[];
}

export const DEFAULT_PREMIUM_CRITERIA: PremiumCriteria = {
  min_edge: 0.05,
  min_consensus: 0.7,
  min_smartbet_score: 80,
  calibration_required: true,
  min_kelly: 0.01,
  max_odds: 5.0,
  grade_filter: ['A+', 'A', 'B'],
};
