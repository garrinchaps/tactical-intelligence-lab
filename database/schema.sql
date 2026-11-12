-- ============================================================================
-- TACTICAL INTELLIGENCE LAB - ESQUEMA RELACIONAL SQLITE
-- ============================================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS matches (
    match_id INTEGER PRIMARY KEY,
    competition_id INTEGER,
    competition_name TEXT NOT NULL,
    season_id INTEGER,
    season_name TEXT NOT NULL,
    match_date TEXT,
    home_team_id INTEGER,
    home_team_name TEXT NOT NULL,
    away_team_id INTEGER,
    away_team_name TEXT NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    stadium_name TEXT,
    referee_name TEXT,
    has_360_data INTEGER DEFAULT 0,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    match_id INTEGER NOT NULL,
    index_num INTEGER NOT NULL,
    period INTEGER NOT NULL,
    timestamp TEXT,
    minute INTEGER NOT NULL,
    second INTEGER NOT NULL,
    possession INTEGER,
    possession_team_id INTEGER,
    possession_team_name TEXT,
    team_id INTEGER NOT NULL,
    team_name TEXT NOT NULL,
    player_id INTEGER,
    player_name TEXT,
    position_name TEXT,
    type_name TEXT NOT NULL,
    play_pattern_name TEXT,
    under_pressure INTEGER DEFAULT 0,
    counterpress INTEGER DEFAULT 0,
    -- Coordenadas espaciais padronizadas StatsBomb (120 x 80 jardas)
    x REAL,
    y REAL,
    end_x REAL,
    end_y REAL,
    -- Atributos específicos de Passe
    pass_length REAL,
    pass_angle REAL,
    pass_recipient_id INTEGER,
    pass_recipient_name TEXT,
    pass_height_name TEXT,
    pass_body_part TEXT,
    pass_type_name TEXT,
    pass_outcome_name TEXT,
    is_pass_Switch INTEGER DEFAULT 0,
    is_pass_cross INTEGER DEFAULT 0,
    is_pass_through_ball INTEGER DEFAULT 0,
    -- Atributos específicos de Finalização (Shot)
    shot_statsbomb_xg REAL,
    shot_outcome_name TEXT,
    shot_body_part_name TEXT,
    shot_type_name TEXT,
    -- Atributos específicos de Condução (Carry) e Drible/Falta
    duel_type_name TEXT,
    duel_outcome_name TEXT,
    interception_outcome_name TEXT,
    ball_recovery_failure INTEGER DEFAULT 0,
    foul_committed_card_name TEXT,
    substitution_replacement_name TEXT,
    tactics_formation INTEGER,
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_match_team ON events(match_id, team_name);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(match_id, type_name);
CREATE INDEX IF NOT EXISTS idx_events_possession ON events(match_id, possession);

CREATE TABLE IF NOT EXISTS tactical_diagnostics_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER,
    team_name TEXT NOT NULL,
    phase_of_play TEXT NOT NULL,
    problem_title TEXT NOT NULL,
    pitch_zone TEXT,
    frequency_pct REAL,
    sample_size INTEGER,
    evidence_strength TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);