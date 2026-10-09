// Tipuri pentru contractul de date BETPREDICT 3.0 (docs/data-contract.md, schema v1).
// Toate probabilitățile sunt 0–1, cotele zecimale, orele UTC ISO.

export type LegResult = 'won' | 'lost' | 'void' | 'half_won' | 'half_lost' | null;
export type MarketKind = '1x2' | 'double_chance' | 'draw_no_bet' | 'over_under' | 'btts' | 'corners' | string;

export interface Team { id: number | null; name: string; logo?: string | null }
export interface League { id: number | null; name: string; country?: string | null; logo?: string | null }

export interface Prediction {
  id: number | string;
  match_id: number;
  market: MarketKind;
  line: number | null;
  selection: string;
  label: string;
  p: number;
  p_model?: number | null;
  p_bsd?: number | null;
  p_market?: number | null;
  odds: number | null;
  odds_source?: string | null;
  fair_odds?: number | null;
  edge?: number | null;
  ev?: number | null;
  value?: boolean;
  grade?: string | null;
  confidence?: number | null;
  is_pick?: boolean;
  recommended?: boolean;
  robot_version?: string;
  market_healthy?: boolean;
  reasons?: string[];
  result?: LegResult;
  profit?: number | null;
  model_version?: string;
  created_at?: string;
}

export interface Form {
  last?: number; played?: number; w?: number; d?: number; l?: number;
  gf?: number; ga?: number; ppm?: number; sequence?: string;
  venue?: { played?: number; ppm?: number } | null;
}

export interface H2H {
  total?: number; home_wins?: number; draws?: number; away_wins?: number;
  avg_goals?: number | null; over25_rate?: number | null; btts_rate?: number | null;
  recent?: Array<{ date?: string; home?: string; away?: string; score?: string }>;
}

export interface Absence { player: string; status?: string; return?: string | null; position?: string | null }

export interface MatchContext {
  form?: { home?: Form | null; away?: Form | null } | null;
  h2h?: H2H | null;
  standings?: {
    home?: { position?: number; points?: number; played?: number } | null;
    away?: { position?: number; points?: number; played?: number } | null;
    zone_home?: string | null; zone_away?: string | null;
  } | null;
  absences?: { home?: Absence[]; away?: Absence[] } | null;
}

export interface OddsMove { open?: number; now?: number; dir?: string }

export interface Match {
  id: number;
  kickoff_utc: string;
  status: string;
  league: League;
  home: Team;
  away: Team;
  round?: string | null;
  score?: { ft?: [number, number] | null; ht?: [number, number] | null } | null;
  minute?: number | null;
  odds?: Record<string, Record<string, number>>;
  odds_movement?: Record<string, Record<string, OddsMove>>;
  bsd_probabilities?: Record<string, Record<string, number>>;
  model?: {
    lambda_home?: number; lambda_away?: number; elo_home?: number; elo_away?: number;
    most_likely_score?: string; top_scores?: Array<{ score: string; p: number }>;
  } | null;
  context?: MatchContext | null;
  predictions: Prediction[];
  pick_id?: number | string | null;
}

export interface Day {
  schema?: string;
  date: string;
  timezone?: string;
  generated_at?: string;
  model_version?: string;
  min_odds?: number;
  odds_source?: string;
  count?: number;
  markets?: string[];
  matches: Match[];
  /** sursa folosită de frontend: contract nou sau adaptor pentru fișierele vechi */
  _source?: 'api' | 'legacy';
}

export interface TicketLeg {
  p_market?: number | null; // probabilitatea pieței fără marjă (pentru miza prudentă)
  prediction_id?: number | string | null;
  match_id: number;
  kickoff_utc?: string;
  league?: string;
  home: string;
  away: string;
  market: MarketKind;
  line: number | null;
  selection: string;
  label: string;
  odds: number;
  p?: number | null;
  grade?: string | null;
  result?: LegResult;
  score?: string | null;
  reasons?: string[];
}

export type TicketStatus = 'pending' | 'won' | 'lost' | 'void';

export interface Ticket {
  id: number | string;
  kind: string; // acca_safe | acca_50 | acca_100 | acca_500 | pyramid | manual
  /** „Bilet sigur” (cote mici, publicat mereu, poate avea EV negativ) */
  safe?: boolean;
  variant?: string;
  variant_label?: string;
  created_by?: 'robot' | 'user' | string;
  date?: string;
  created_at?: string;
  target_odds?: number | null;
  total_odds: number;
  p_ticket?: number | null;
  ev?: number | null;
  status?: TicketStatus;
  settled_legs?: number;
  legs_count?: number;
  effective_odds?: number;
  legs: TicketLeg[];
  reasons?: string[];
  stake?: number;
  /** miză sugerată de Robot, în unități (1u = 1% din bancă), ¼ Kelly plafonat */
  stake_units?: number | null;
  /** copie a unui bilet al Robotului, marcată „jucat de mine” */
  followed?: boolean;
}

export interface TicketsFile {
  schema?: string; date: string; generated_at?: string; targets?: number[];
  tickets: Ticket[]; notes?: string[]; _source?: 'api' | 'robot-local';
}

export interface PyramidRules {
  target_odds: number; band: [number, number]; max_legs: number; min_p: number; min_ev: number;
  start_bank: number; withdraw_steps: number[]; withdraw_pct: number;
  target_multiple: number; target_withdraw_pct: number;
}

export interface PyramidHistoryRow {
  date: string; ticket_id?: number | string | null; odds?: number | null; p?: number | null;
  result?: LegResult | 'pending'; status: 'pick' | 'no_bet' | string; label?: string;
}

export interface PyramidState {
  schema?: string; generated_at?: string; date: string;
  rules: PyramidRules;
  today: { status: 'pick' | 'no_bet'; reason?: string; main?: Ticket | null; alternatives?: Ticket[] };
  run?: { id?: number; start_date?: string; status?: string; step?: number; bank?: number; start_bank?: number; withdrawn?: number } | null;
  history: PyramidHistoryRow[];
  runs?: Array<{ id?: number; start_date?: string; end_date?: string; steps?: number; max_bank?: number; withdrawn?: number; status?: string }>;
  reach_probability?: Array<{ step: number; p: number }>;
  _source?: 'api' | 'legacy';
}

export interface StatBlock {
  key?: string; name?: string;
  n: number; won: number; lost: number; void?: number; pending?: number;
  win_rate: number | null; roi_pct: number | null; profit: number;
  avg_odds?: number | null; avg_p?: number | null; brier?: number | null; logloss?: number | null;
}

export interface Recommendation { severity: 'info' | 'warn' | 'critical' | string; text: string; evidence?: Record<string, unknown> }

export interface StatsSummary {
  schema?: string; generated_at?: string; scope?: string;
  overall: StatBlock; picks?: StatBlock; value?: StatBlock; recommended?: StatBlock; robot_version?: string; since?: string;
  by_market: StatBlock[]; by_league: StatBlock[]; by_odds_band: StatBlock[];
  by_grade?: StatBlock[]; by_p_band?: StatBlock[];
  tickets?: Array<{ kind: string; variant?: string; n: number; won: number; lost: number; void?: number; pending?: number; roi_pct: number | null; profit: number }>;
  pyramid?: { days?: number; picks?: number; no_bet?: number; won?: number; lost?: number; win_rate?: number | null; runs?: number; best_step?: number };
  legacy?: { n: number; win_rate: number; roi_pct: number } | null;
  recommendations: Recommendation[];
  _source?: 'api' | 'legacy';
}

export interface SeriesRow extends StatBlock { key: string }
export interface StatsSeries { rows: SeriesRow[] }

export interface CalibrationMarket {
  key: string; n: number; ece: number | null; healthy?: boolean;
  bins: Array<{ lo: number; hi: number; n: number; p_avg: number; hit_rate: number }>;
}

export interface Learning {
  model?: { version?: string; trained_at?: string; matches?: number; half_life_days?: number };
  walk_forward?: Array<Record<string, number | string>>;
  params?: { excluded_markets?: string[]; blend?: Record<string, Record<string, number>> };
  log?: Array<{ run_at?: string; change_type?: string; market?: string; before?: unknown; after?: unknown; evidence?: Record<string, unknown> }>;
}

export interface Meta {
  generated_at?: string; day?: string; model_version?: string; app_version?: string;
  status?: 'ok' | 'degraded' | 'stale' | string;
  quota?: { effective_remaining?: number; daily_quota?: number; exhausted?: boolean };
  last_steps?: Record<string, string>;
  warnings?: string[];
  _source?: 'api' | 'legacy';
}

/** O selecție din jurnalul de statistici (rând plat, decontat sau nu). */
export interface JournalRow {
  date: string; // zi RO
  match_id: number;
  match: string;
  league: string;
  market: string;
  label: string;
  odds: number;
  p: number | null;
  result: LegResult | 'pending';
  profit: number | null;
  grade?: string | null;
  source?: string;
  score?: string | null;
}

export interface BtMetrics { n: number; logloss: number; brier: number; ece: number }
export interface BtRoi { n: number; roi: number | null; hit: number | null; avg_odds: number | null; se?: number | null }
export interface RobotDoc {
  model_label: string; db_key?: string; engine?: string; stats_since?: string; days_ahead?: number | null;
  model?: { version?: string; trained_at?: string | null; train_to?: string | null; matches?: number; n_train?: number; half_life_days?: number;
    oos?: Record<string, Record<string, number> | number> | null };
  backtest?: { generated_at?: string; history_matches?: number; eval_from?: string; odds_matches?: number; odds_from?: string | null;
    markets: Array<{ key: string; title: string; v1: BtMetrics | null; v2: BtMetrics | null; market: BtMetrics | null; v2_market: BtMetrics | null; roi_rec: BtRoi | null; roi_ev3: BtRoi | null }> } | null;
  thresholds?: Array<{ key: string; min_ev: number | null; source: string; n?: number | null; roi?: number | null; blocked_leagues?: number }>;
  excluded_markets?: string[]; params_updated_at?: string | null;
  walk_forward?: Array<Record<string, number | string>>;
  log?: Array<{ run_at?: string; change_type?: string; market?: string | null; before?: unknown; after?: unknown; evidence?: Record<string, unknown> }>;
  schedule?: { retrain?: string; next_retrain_utc?: string; daily?: string; refresh?: string };
  generated_at?: string;
}
