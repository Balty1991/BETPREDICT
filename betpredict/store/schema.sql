-- BETPREDICT 3.0 — schema SQLite v1 (vezi betpredict_plan §4).
-- Toate orele sunt UTC ISO-8601. Probabilitățile sunt 0–1. Cotele sunt zecimale.

CREATE TABLE IF NOT EXISTS league (
  id            INTEGER PRIMARY KEY,
  name          TEXT,
  country       TEXT,
  tier          INTEGER,
  is_cup        INTEGER DEFAULT 0,
  tracked       INTEGER DEFAULT 1,
  quality_score REAL,
  updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS season (
  id         INTEGER PRIMARY KEY,
  league_id  INTEGER REFERENCES league(id),
  name       TEXT,
  year_start INTEGER,
  year_end   INTEGER,
  is_current INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS team (
  id             INTEGER PRIMARY KEY,
  name           TEXT,
  country        TEXT,
  league_id      INTEGER,
  elo            REAL,
  elo_updated_at TEXT
);

-- „fixtures + results”: un rând pe meci, actualizat la decontare.
CREATE TABLE IF NOT EXISTS match (
  id           INTEGER PRIMARY KEY,
  season_id    INTEGER,
  league_id    INTEGER,
  kickoff_utc  TEXT NOT NULL,
  home_id      INTEGER,
  away_id      INTEGER,
  home_name    TEXT,
  away_name    TEXT,
  status       TEXT,
  stage        TEXT,
  round        TEXT,
  ft_home      INTEGER,
  ft_away      INTEGER,
  ht_home      INTEGER,
  ht_away      INTEGER,
  xg_home      REAL,
  xg_away      REAL,
  corners_home INTEGER,
  corners_away INTEGER,
  cards_home   INTEGER,
  cards_away   INTEGER,
  venue_id     INTEGER,
  referee_id   INTEGER,
  raw_json     TEXT,
  updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_match_kickoff ON match(kickoff_utc);
CREATE INDEX IF NOT EXISTS ix_match_league ON match(league_id, kickoff_utc);
CREATE INDEX IF NOT EXISTS ix_match_status ON match(status);

CREATE TABLE IF NOT EXISTS match_stats (
  match_id  INTEGER NOT NULL,
  team_side TEXT NOT NULL,          -- 'home' | 'away'
  key       TEXT NOT NULL,
  value     REAL,
  PRIMARY KEY (match_id, team_side, key)
);

-- Istoricul cotelor (append-only; deduplicat pe observație).
CREATE TABLE IF NOT EXISTS odds_snapshot (
  match_id         INTEGER NOT NULL,
  market           TEXT NOT NULL,    -- 1x2 | over_under | btts | double_chance | draw_no_bet | asian_handicap | total_corners ...
  line             REAL NOT NULL DEFAULT 0, -- 2.5 pentru O/U 2.5; 0 când nu se aplică (NULL ar strica UNIQUE)
  period           TEXT NOT NULL DEFAULT 'FT',
  outcome          TEXT NOT NULL,    -- HOME/DRAW/AWAY/OVER/UNDER/YES/NO/1X/12/X2
  decimal          REAL NOT NULL,
  opening_decimal  REAL,
  previous_decimal REAL,
  movement         TEXT,
  source           TEXT NOT NULL DEFAULT 'bsd_consensus',
  observed_at      TEXT NOT NULL,
  UNIQUE (match_id, market, line, period, outcome, source, observed_at)
);
CREATE INDEX IF NOT EXISTS ix_odds_match ON odds_snapshot(match_id, market);

CREATE TABLE IF NOT EXISTS team_form (
  team_id     INTEGER NOT NULL,
  as_of       TEXT NOT NULL,
  venue       TEXT NOT NULL DEFAULT 'all',
  window      INTEGER NOT NULL,
  played      INTEGER, w INTEGER, d INTEGER, l INTEGER,
  gf          INTEGER, ga INTEGER, ppm REAL,
  xg_for      REAL, xg_against REAL,
  stats_json  TEXT,
  PRIMARY KEY (team_id, as_of, venue, window)
);

CREATE TABLE IF NOT EXISTS availability (
  team_id         INTEGER NOT NULL,
  player_id       INTEGER NOT NULL,
  as_of           TEXT NOT NULL,
  status          TEXT,
  injury_type     TEXT,
  expected_return TEXT,
  importance      REAL,
  PRIMARY KEY (team_id, player_id, as_of)
);

CREATE TABLE IF NOT EXISTS feature_row (
  match_id      INTEGER NOT NULL,
  model_version TEXT NOT NULL,
  features      TEXT NOT NULL,       -- JSON: snapshotul exact folosit la predicție
  created_at    TEXT,
  PRIMARY KEY (match_id, model_version)
);

-- Probabilitățile furnizorilor externi (BSD, Polymarket) — date de intrare, NU jurnalul Robotului.
CREATE TABLE IF NOT EXISTS provider_prediction (
  match_id      INTEGER NOT NULL,
  source        TEXT NOT NULL,       -- 'bsd' | 'polymarket'
  market        TEXT NOT NULL,
  line          REAL NOT NULL DEFAULT 0,
  selection     TEXT NOT NULL,
  probability   REAL NOT NULL,
  model_version TEXT,
  fetched_at    TEXT NOT NULL,
  PRIMARY KEY (match_id, source, market, line, selection)
);

-- Jurnalul: tot ce se afișează trece întâi prin acest tabel.
CREATE TABLE IF NOT EXISTS prediction (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id       INTEGER NOT NULL,
  market         TEXT NOT NULL,
  line           REAL NOT NULL DEFAULT 0,
  period         TEXT NOT NULL DEFAULT 'FT',
  selection      TEXT NOT NULL,
  p_model        REAL,
  p_calibrated   REAL,
  p_market_novig REAL,
  odds_shown     REAL,
  odds_source    TEXT,
  edge           REAL,
  ev             REAL,
  confidence     REAL,
  grade          TEXT,
  reasons_json   TEXT,
  model_version  TEXT NOT NULL,
  created_at     TEXT NOT NULL,
  shown_on_page  TEXT,               -- 'predictii' | 'acasa' | 'piramida' | 'legacy'
  closing_odds   REAL,
  clv            REAL,
  result         TEXT,               -- won | lost | void | half_won | half_lost | NULL (în așteptare)
  settled_at     TEXT,
  profit_1u      REAL,
  legacy_key     TEXT UNIQUE,        -- cheia din selection_journal.json (import idempotent)
  UNIQUE (match_id, market, line, period, selection, model_version, shown_on_page)
);
CREATE INDEX IF NOT EXISTS ix_pred_created ON prediction(created_at);
CREATE INDEX IF NOT EXISTS ix_pred_result ON prediction(result);

CREATE TABLE IF NOT EXISTS ticket (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  kind        TEXT NOT NULL,         -- acca_50 | acca_100 | acca_500 | pyramid | manual
  variant     TEXT,                  -- echilibrat | valoare | ancora_surpriza | goluri
  created_by  TEXT NOT NULL DEFAULT 'robot',
  target_odds REAL,
  total_odds  REAL,
  p_ticket    REAL,
  ev          REAL,
  stake       REAL,
  status      TEXT NOT NULL DEFAULT 'pending', -- pending | won | lost | void
  payout      REAL,
  created_at  TEXT NOT NULL,
  settled_at  TEXT,
  notes       TEXT
);

CREATE TABLE IF NOT EXISTS ticket_leg (
  ticket_id     INTEGER NOT NULL REFERENCES ticket(id) ON DELETE CASCADE,
  prediction_id INTEGER REFERENCES prediction(id),
  match_id      INTEGER NOT NULL,
  market        TEXT NOT NULL,
  selection     TEXT NOT NULL,
  odds          REAL NOT NULL,
  result        TEXT,
  PRIMARY KEY (ticket_id, match_id, market, selection)
);

CREATE TABLE IF NOT EXISTS pyramid_run (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  start_date      TEXT NOT NULL,
  start_bank      REAL NOT NULL,
  status          TEXT NOT NULL DEFAULT 'active',
  current_step    INTEGER NOT NULL DEFAULT 0,
  current_bank    REAL NOT NULL,
  withdrawn_total REAL NOT NULL DEFAULT 0,
  rule_json       TEXT
);

CREATE TABLE IF NOT EXISTS pyramid_step (
  run_id      INTEGER NOT NULL REFERENCES pyramid_run(id) ON DELETE CASCADE,
  step_no     INTEGER NOT NULL,
  date        TEXT NOT NULL,
  ticket_id   INTEGER REFERENCES ticket(id),
  stake       REAL,
  odds        REAL,
  result      TEXT,
  bank_before REAL,
  bank_after  REAL,
  withdrawn   REAL DEFAULT 0,
  PRIMARY KEY (run_id, step_no)
);

CREATE TABLE IF NOT EXISTS model_registry (
  version      TEXT PRIMARY KEY,
  trained_at   TEXT,
  train_from   TEXT,
  train_to     TEXT,
  metrics_json TEXT,
  is_active    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS learning_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  run_at        TEXT NOT NULL,
  market        TEXT,
  league_id     INTEGER,
  change_type   TEXT,
  before        TEXT,
  after         TEXT,
  evidence_json TEXT
);

-- Stare internă a pipeline-ului (ex. ultimul updated_after pentru polling-ul de cote).
CREATE TABLE IF NOT EXISTS ingest_state (
  key        TEXT PRIMARY KEY,
  value      TEXT,
  updated_at TEXT
);
