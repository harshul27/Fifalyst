-- FIFA World Cup 2026 - PostgreSQL Schema Initialization
-- Multi-Agent Fitness System Database

-- ============================================
-- 1. MASTER PLAYER DATA
-- ============================================
CREATE TABLE IF NOT EXISTS players (
    player_id SERIAL PRIMARY KEY,
    player_name VARCHAR(255) NOT NULL,
    team_id INTEGER NOT NULL,
    position VARCHAR(10) NOT NULL, -- GK, CB, LB, RB, CM, RM, LM, ST, LW, RW
    club VARCHAR(255),
    appearances INTEGER DEFAULT 0,
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    minutes_played INTEGER DEFAULT 0,
    rating NUMERIC(3,1) DEFAULT 0.0,
    injury_risk NUMERIC(3,2) DEFAULT 0.0,
    recovery_days INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_name, team_id)
);

CREATE INDEX idx_players_team ON players(team_id);
CREATE INDEX idx_players_position ON players(position);

-- ============================================
-- 2. TEAM MASTER DATA
-- ============================================
CREATE TABLE IF NOT EXISTS teams (
    team_id SERIAL PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL UNIQUE,
    region VARCHAR(50), -- North America, South America, Europe, Africa, Asia
    squad_size INTEGER DEFAULT 23,
    baseline_pes NUMERIC(5,2) DEFAULT 75.0,
    status VARCHAR(20), -- ELITE, STRONG, COMPETITIVE, DEVELOPING
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_teams_region ON teams(region);

-- ============================================
-- 3. SEASONAL FITNESS BASELINE (Pre-Tournament)
-- ============================================
CREATE TABLE IF NOT EXISTS player_fitness_baseline (
    fitness_id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    baseline_fitness NUMERIC(5,2) NOT NULL, -- [0, 100]
    confidence NUMERIC(3,2) DEFAULT 0.85,
    injury_risk NUMERIC(3,2) DEFAULT 0.0,
    recovery_days INTEGER DEFAULT 0,
    predicted_fatigue_threshold NUMERIC(5,2) DEFAULT 75.0,
    model_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id)
);

CREATE INDEX idx_fitness_baseline_team ON player_fitness_baseline(team_id);

-- ============================================
-- 4. MATCH MASTER DATA
-- ============================================
CREATE TABLE IF NOT EXISTS matches (
    match_id SERIAL PRIMARY KEY,
    match_external_id VARCHAR(100) UNIQUE, -- ESPN match ID
    home_team_id INTEGER NOT NULL REFERENCES teams(team_id),
    away_team_id INTEGER NOT NULL REFERENCES teams(team_id),
    match_date TIMESTAMP NOT NULL,
    status VARCHAR(20), -- SCHEDULED, LIVE_1ST, HALFTIME, LIVE_2ND, FINISHED, ARCHIVED
    home_score INTEGER DEFAULT 0,
    away_score INTEGER DEFAULT 0,
    current_minute INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_matches_date ON matches(match_date);
CREATE INDEX idx_matches_status ON matches(status);
CREATE INDEX idx_matches_external_id ON matches(match_external_id);

-- ============================================
-- 5. MATCH LINEUPS (Current)
-- ============================================
CREATE TABLE IF NOT EXISTS match_lineups (
    lineup_id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(match_id),
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    is_starter BOOLEAN DEFAULT true,
    minutes_on_field INTEGER DEFAULT 0,
    substituted_in_minute INTEGER,
    substituted_out_minute INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, team_id, player_id)
);

CREATE INDEX idx_lineups_match_team ON match_lineups(match_id, team_id);

-- ============================================
-- 6. LIVE METRICS (Per 5-min interval)
-- ============================================
CREATE TABLE IF NOT EXISTS live_metrics (
    metric_id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(match_id),
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    minute INTEGER NOT NULL,
    distance_km NUMERIC(5,2) DEFAULT 0.0,
    passes INTEGER DEFAULT 0,
    pass_accuracy NUMERIC(5,2) DEFAULT 0.0,
    tackles INTEGER DEFAULT 0,
    clearances INTEGER DEFAULT 0,
    shots INTEGER DEFAULT 0,
    shot_accuracy NUMERIC(5,2) DEFAULT 0.0,
    fouls INTEGER DEFAULT 0,
    yellow_cards INTEGER DEFAULT 0,
    player_rating NUMERIC(3,1) DEFAULT 0.0,
    running_load_pct NUMERIC(5,2) DEFAULT 0.0,
    performance_index NUMERIC(5,2) DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, player_id, minute)
);

CREATE INDEX idx_metrics_match_minute ON live_metrics(match_id, minute);
CREATE INDEX idx_metrics_player_match ON live_metrics(player_id, match_id);

-- ============================================
-- 7. REAL-TIME FITNESS SCORES (Per player, updated every 5 min)
-- ============================================
CREATE TABLE IF NOT EXISTS live_player_fitness (
    fitness_id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(match_id),
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    minute INTEGER NOT NULL,
    baseline_fitness NUMERIC(5,2) NOT NULL,
    current_fitness NUMERIC(5,2) NOT NULL,
    fatigue_pct NUMERIC(5,2) NOT NULL,
    fatigue_status VARCHAR(20), -- PEAK, FRESH, FAIR, ELEVATED, CRITICAL
    running_load_km NUMERIC(5,2) DEFAULT 0.0,
    substitution_risk NUMERIC(3,2) DEFAULT 0.0,
    injury_risk NUMERIC(3,2) DEFAULT 0.0,
    recommendation_ready BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, player_id, minute)
);

CREATE INDEX idx_fitness_match_minute ON live_player_fitness(match_id, minute);
CREATE INDEX idx_fitness_player_fatigue ON live_player_fitness(player_id, fatigue_pct);

-- ============================================
-- 8. SUBSTITUTION HISTORY
-- ============================================
CREATE TABLE IF NOT EXISTS substitution_history (
    sub_id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(match_id),
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    player_out_id INTEGER NOT NULL REFERENCES players(player_id),
    player_in_id INTEGER NOT NULL REFERENCES players(player_id),
    minute_substituted INTEGER NOT NULL,
    reason VARCHAR(100), -- FATIGUE, INJURY, TACTICAL, PRECAUTIONARY
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_subs_match_team ON substitution_history(match_id, team_id);

-- ============================================
-- 9. RECOMMENDATIONS LOG
-- ============================================
CREATE TABLE IF NOT EXISTS recommendations_log (
    rec_id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(match_id),
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    minute INTEGER NOT NULL,
    off_player_id INTEGER NOT NULL REFERENCES players(player_id),
    on_player_id INTEGER NOT NULL REFERENCES players(player_id),
    confidence NUMERIC(3,2) NOT NULL,
    impact NUMERIC(5,2) NOT NULL,
    reasons TEXT, -- JSON array of reasons
    was_accepted BOOLEAN DEFAULT NULL,
    actual_impact NUMERIC(5,2), -- Measured after the fact
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_recs_match_team ON recommendations_log(match_id, team_id);
CREATE INDEX idx_recs_accuracy ON recommendations_log(was_accepted, actual_impact);

-- ============================================
-- 10. MODEL METADATA
-- ============================================
CREATE TABLE IF NOT EXISTS model_metadata (
    model_id SERIAL PRIMARY KEY,
    model_type VARCHAR(50), -- XGBOOST, NEURAL_NETWORK, RULE_BASED
    model_version VARCHAR(50),
    accuracy_benchmark NUMERIC(5,3),
    cv_score_mean NUMERIC(5,3),
    cv_score_stddev NUMERIC(5,3),
    feature_count INTEGER,
    training_date TIMESTAMP,
    artifact_location VARCHAR(255), -- Path in MinIO
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 11. AGENT HEALTH & MONITORING
-- ============================================
CREATE TABLE IF NOT EXISTS agent_metrics (
    metric_id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100), -- DATA_COLLECTION, FITNESS_MODEL, LIVE_MATCH, RECOMMENDATION, FEEDBACK
    cycle_timestamp TIMESTAMP NOT NULL,
    cycle_duration_ms INTEGER,
    tool_calls_count INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    cache_hit_rate NUMERIC(5,3),
    status VARCHAR(20), -- SUCCESS, WARNING, ERROR
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_agent_metrics_timestamp ON agent_metrics(cycle_timestamp);
CREATE INDEX idx_agent_metrics_agent ON agent_metrics(agent_name);

-- ============================================
-- 12. GRANT PERMISSIONS
-- ============================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO fifa_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO fifa_admin;

-- Create read-only user for reporting
CREATE USER fifa_reader WITH PASSWORD 'fifa_reader_password';
GRANT CONNECT ON DATABASE fifa_wc_2026 TO fifa_reader;
GRANT USAGE ON SCHEMA public TO fifa_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO fifa_reader;

-- ============================================
-- 13. INITIAL DATA: Load 48 World Cup Teams
-- ============================================
INSERT INTO teams (team_name, region, status) VALUES
-- North America (3)
('United States', 'North America', 'COMPETITIVE'),
('Mexico', 'North America', 'COMPETITIVE'),
('Canada', 'North America', 'DEVELOPING'),
-- South America (6)
('Argentina', 'South America', 'ELITE'),
('Brazil', 'South America', 'ELITE'),
('Colombia', 'South America', 'STRONG'),
('Ecuador', 'South America', 'COMPETITIVE'),
('Paraguay', 'South America', 'COMPETITIVE'),
('Uruguay', 'South America', 'STRONG'),
-- Europe (16)
('England', 'Europe', 'STRONG'),
('France', 'Europe', 'ELITE'),
('Germany', 'Europe', 'ELITE'),
('Spain', 'Europe', 'STRONG'),
('Portugal', 'Europe', 'STRONG'),
('Italy', 'Europe', 'STRONG'),
('Netherlands', 'Europe', 'STRONG'),
('Belgium', 'Europe', 'STRONG'),
('Denmark', 'Europe', 'STRONG'),
('Sweden', 'Europe', 'COMPETITIVE'),
('Poland', 'Europe', 'COMPETITIVE'),
('Austria', 'Europe', 'COMPETITIVE'),
('Czechia', 'Europe', 'COMPETITIVE'),
('Switzerland', 'Europe', 'COMPETITIVE'),
('Serbia', 'Europe', 'COMPETITIVE'),
('Norway', 'Europe', 'DEVELOPING'),
-- Africa (9)
('Egypt', 'Africa', 'COMPETITIVE'),
('Cameroon', 'Africa', 'COMPETITIVE'),
('Senegal', 'Africa', 'COMPETITIVE'),
('Ghana', 'Africa', 'DEVELOPING'),
('Nigeria', 'Africa', 'DEVELOPING'),
('Morocco', 'Africa', 'COMPETITIVE'),
('Ivory Coast', 'Africa', 'DEVELOPING'),
('Mali', 'Africa', 'DEVELOPING'),
('Tunisia', 'Africa', 'DEVELOPING'),
-- Asia (8)
('Japan', 'Asia', 'COMPETITIVE'),
('South Korea', 'Asia', 'COMPETITIVE'),
('Saudi Arabia', 'Asia', 'DEVELOPING'),
('Iran', 'Asia', 'DEVELOPING'),
('Iraq', 'Asia', 'DEVELOPING'),
('Australia', 'Asia', 'DEVELOPING'),
('Uzbekistan', 'Asia', 'DEVELOPING'),
('Qatar', 'Asia', 'DEVELOPING')
ON CONFLICT DO NOTHING;
