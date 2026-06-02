export interface Signal {
  event_id: number | string;
  home_team: string;
  away_team: string;
  home_team_id?: number | null;
  away_team_id?: number | null;
  league?: string;
  league_id?: number | null;
  event_date: string;
  market: string;
  market_label?: string;
  quality_grade_v6?: string;
  quality_grade?: string;
  display_score?: number;
  market_signal_score?: number;
  smartbet_score_v6?: number;
  smartbet_score?: number;
  adj_prob?: number;
  calibrated_prob?: number;
  ev_calibrated?: number;
  ev?: number;
  ev_pct?: string | number;
  edge_pp?: number;
  odds?: number;
  strategy?: string;
  engine_version?: string;
  agreement?: number;
  risk_tier?: string;
  rationale?: string;
  ai_insight?: string;
  wfv_auc?: number;
  movement?: string;
  model_vs_market_gap_pp?: number;
  most_likely_score?: string;
  poisson_score?: string;
  consensus_score?: number;
  context_score?: number;
  context_label?: string;
  xg_home?: number;
  xg_away?: number;
  strategy_label?: string;
  strategy_icon?: string;
  strategy_color?: string;
  display_grade?: string;
  clv_badge?: string;
}

export interface JournalEntry {
  event_id: number | string;
  home_team: string;
  away_team: string;
  league?: string;
  event_date: string;
  market: string;
  market_label?: string;
  strategy?: string;
  strategy_label?: string;
  odds?: number;
  status: 'pending' | 'settled' | 'voided';
  result?: 'WIN' | 'LOSS' | null;
  profit_units?: number | null;
  score_ft?: string;
  actual_score?: string;
  first_seen_at?: string;
  settled_at?: string;
  score?: number;
}

export interface ValueBet {
  event_id: number | string;
  market: string;
  edge_pct?: number;
  ev_pct?: number;
  odds?: number;
}

export interface PerformanceHeatmap {
  leagues?: Record<string, { grade?: string; roi_pct?: number; sample?: number }>;
}

export interface BetPredictData {
  signals: Signal[];
  journal: JournalEntry[];
  valueBets: ValueBet[];
  heatmap: PerformanceHeatmap;
  updatedAt: string | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}
