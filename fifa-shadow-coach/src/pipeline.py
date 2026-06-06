"""
FIFA Shadow Coach - Automated Data Pipeline
ETL → Feature Engineering → Self-Correcting Feedback Loop
"""

import os
import sys
import json
import duckdb
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Import the model module (assumes it's in the same src/ directory)
try:
    from model import calculate_player_energy, BASE_PLAYER_ENERGY, MIN_PHYSIOLOGICAL_ENERGY
except ImportError:
    # Fallback if running from outputs directory
    print("⚠ Warning: Could not import model module. Using stubs.")
    BASE_PLAYER_ENERGY = 100.0
    MIN_PHYSIOLOGICAL_ENERGY = 15.0
    def calculate_player_energy(logs):
        return BASE_PLAYER_ENERGY


# ==================== LOGGING & SETUP ====================

class PipelineLogger:
    """Lightweight logger for pipeline status."""
    def __init__(self):
        self.timestamp = datetime.utcnow().isoformat()

    def log(self, message: str, level: str = "INFO"):
        """Log with timestamp and level."""
        prefix = f"[{datetime.utcnow().isoformat()}] [{level}]"
        print(f"{prefix} {message}")

    def success(self, message: str):
        self.log(f"✓ {message}", "SUCCESS")

    def error(self, message: str):
        self.log(f"✗ {message}", "ERROR")

    def info(self, message: str):
        self.log(message, "INFO")


logger = PipelineLogger()
DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "database.duckdb"
CONFIG_PATH = DATA_DIR / "model_config.json"
PARQUET_PATH = DATA_DIR / "latest_squad_state.parquet"


def setup_directories():
    """Ensure data directory exists."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        logger.success(f"Data directory ready: {DATA_DIR}")
    except Exception as e:
        logger.error(f"Failed to create data directory: {e}")
        raise


def initialize_duckdb() -> duckdb.DuckDBPyConnection:
    """Initialize or connect to DuckDB instance."""
    try:
        conn = duckdb.connect(str(DB_PATH))
        logger.success(f"DuckDB connected: {DB_PATH}")
        return conn
    except Exception as e:
        logger.error(f"DuckDB connection failed: {e}")
        raise


# ==================== ETL PROCESS ====================

def create_mock_player_data() -> pd.DataFrame:
    """
    Generate mock play-by-play player data simulating scraped match data.

    Returns:
        DataFrame with columns: Player, minutes, days_ago, intensity
    """
    np.random.seed(42)
    players = ['Mbappé', 'Neymar', 'Vinicius', 'Rodrygo', 'Paquetá',
               'Neymar_backup', 'Vinicius_backup', 'Ney_sub', 'Messi']

    records = []
    for player in players:
        # Each player has 1-4 recent match records
        n_matches = np.random.randint(1, 5)
        for match_idx in range(n_matches):
            records.append({
                'player': player,
                'minutes_played': np.clip(np.random.normal(75, 15), 0, 90),
                'days_ago': np.random.exponential(scale=3),
                'match_intensity': np.clip(np.random.normal(0.7, 0.15), 0.2, 1.0)
            })

    df = pd.DataFrame(records)
    return df


def insert_mock_data_to_duckdb(conn: duckdb.DuckDBPyConnection, df: pd.DataFrame):
    """Insert mock DataFrame into DuckDB table."""
    try:
        conn.execute("DROP TABLE IF EXISTS player_match_logs")
        conn.execute("""
            CREATE TABLE player_match_logs AS
            SELECT
                player,
                minutes_played,
                days_ago,
                match_intensity
            FROM df
        """)
        row_count = conn.execute("SELECT COUNT(*) FROM player_match_logs").fetchall()[0][0]
        logger.success(f"Inserted {row_count} player match records into DuckDB")
    except Exception as e:
        logger.error(f"ETL insert failed: {e}")
        raise


# ==================== FEATURE ENGINEERING ====================

def extract_and_engineer_features(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    Query player match logs and compute Player Energy Scores (PES).

    Returns:
        DataFrame with columns: player, pes, n_matches, avg_intensity
    """
    try:
        # Query: group by player, aggregate match history
        query = """
            SELECT
                player,
                COUNT(*) as n_matches,
                AVG(match_intensity) as avg_intensity,
                MAX(days_ago) as days_since_last_match
            FROM player_match_logs
            GROUP BY player
            ORDER BY player
        """
        grouped_df = conn.execute(query).fetch_df()
        logger.info(f"Extracted features for {len(grouped_df)} players")

        # Apply calculate_player_energy to each player's match history
        results = []
        for _, row in grouped_df.iterrows():
            player_name = row['player']

            # Fetch match logs for this specific player
            player_logs = conn.execute(
                f"""
                SELECT minutes_played, days_ago, match_intensity
                FROM player_match_logs
                WHERE player = ?
                ORDER BY days_ago ASC
                """,
                [player_name]
            ).fetch_df()

            # Convert to list of dicts for calculate_player_energy
            match_logs = [
                {
                    'minutes_played': float(m),
                    'days_ago': float(d),
                    'match_intensity': float(i)
                }
                for m, d, i in zip(
                    player_logs['minutes_played'],
                    player_logs['days_ago'],
                    player_logs['match_intensity']
                )
            ]

            # Compute PES
            pes = calculate_player_energy(match_logs)

            results.append({
                'player': player_name,
                'pes': pes,
                'n_matches': int(row['n_matches']),
                'avg_intensity': float(row['avg_intensity']),
                'days_since_last_match': float(row['days_since_last_match'])
            })

        feature_df = pd.DataFrame(results)
        logger.success(f"Computed PES for {len(feature_df)} players")
        return feature_df

    except Exception as e:
        logger.error(f"Feature engineering failed: {e}")
        raise


def write_features_to_parquet(df: pd.DataFrame):
    """Write engineered features to compressed Parquet."""
    try:
        df.to_parquet(PARQUET_PATH, compression='snappy', index=False)
        file_size_kb = PARQUET_PATH.stat().st_size / 1024
        logger.success(f"Wrote squad state to {PARQUET_PATH} ({file_size_kb:.1f} KB)")
    except Exception as e:
        logger.error(f"Parquet write failed: {e}")
        raise


# ==================== SELF-CORRECTING FEEDBACK LOOP ====================

def load_or_init_config() -> Dict:
    """Load model config or initialize with defaults."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded config from {CONFIG_PATH}")
            return config
        except Exception as e:
            logger.error(f"Config load failed: {e}, using defaults")

    # Initialize defaults
    config = {
        'alpha_fatigue_weight': 1.0,
        'loss_history': [],
        'backprop_iterations': 0,
        'last_updated': datetime.utcnow().isoformat()
    }
    logger.info("Initialized new config with defaults")
    return config


def simulate_backpropagation(config: Dict, squad_pes: pd.DataFrame) -> Dict:
    """
    Simulate post-match backpropagation: adjust alpha_fatigue_weight,
    compute mock loss, and track optimization history.
    """
    try:
        logger.info("Starting backpropagation simulation...")

        # Mock loss: based on variance in squad PES (ideal squad has high coherence)
        current_loss = float(squad_pes['pes'].std())  # Loss = PES variance

        # Gradient descent: if loss > threshold, reduce alpha (more aggressive fatigue)
        loss_threshold = 20.0
        learning_rate = 0.01

        if current_loss > loss_threshold:
            config['alpha_fatigue_weight'] -= learning_rate
            config['alpha_fatigue_weight'] = max(0.5, config['alpha_fatigue_weight'])
            logger.info(f"Loss {current_loss:.2f} > {loss_threshold}, reduced alpha to {config['alpha_fatigue_weight']:.4f}")
        else:
            logger.info(f"Loss {current_loss:.2f} ≤ {loss_threshold}, no adjustment needed")

        # Track loss history (rolling window of last 10)
        config['loss_history'].append(float(current_loss))
        config['loss_history'] = config['loss_history'][-10:]

        config['backprop_iterations'] += 1
        config['last_updated'] = datetime.utcnow().isoformat()

        logger.success(f"Backprop iteration {config['backprop_iterations']} complete. Loss: {current_loss:.2f}")
        return config

    except Exception as e:
        logger.error(f"Backpropagation failed: {e}")
        return config


def save_config(config: Dict):
    """Persist config to JSON."""
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        logger.success(f"Config saved to {CONFIG_PATH}")
    except Exception as e:
        logger.error(f"Config save failed: {e}")


# ==================== MAIN ORCHESTRATION ====================

def run_pipeline():
    """Execute full production pipeline."""
    conn = None
    try:
        logger.info("=" * 70)
        logger.info("FIFA SHADOW COACH - DATA PIPELINE STARTED")
        logger.info("=" * 70)

        # Step 1: Setup
        logger.info("\n[STEP 1/6] Directory & Database Setup")
        setup_directories()
        conn = initialize_duckdb()

        # Step 2: ETL
        logger.info("\n[STEP 2/6] Mock Data ETL")
        mock_df = create_mock_player_data()
        logger.info(f"Generated {len(mock_df)} mock match records")
        insert_mock_data_to_duckdb(conn, mock_df)

        # Step 3: Feature Engineering
        logger.info("\n[STEP 3/6] Feature Engineering & PES Calculation")
        squad_pes = extract_and_engineer_features(conn)
        logger.info(f"Squad PES distribution: min={squad_pes['pes'].min():.1f}, "
                    f"max={squad_pes['pes'].max():.1f}, mean={squad_pes['pes'].mean():.1f}")

        # Step 4: Persist Features
        logger.info("\n[STEP 4/6] Persist to Parquet")
        write_features_to_parquet(squad_pes)

        # Step 5: Config & Backprop
        logger.info("\n[STEP 5/6] Self-Correcting Feedback Loop")
        config = load_or_init_config()
        config = simulate_backpropagation(config, squad_pes)
        save_config(config)

        # Step 6: Cleanup
        logger.info("\n[STEP 6/6] Cleanup & Close Connections")
        if conn:
            conn.close()
            logger.success("DuckDB connection closed safely")

        logger.info("\n" + "=" * 70)
        logger.success("PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)

        return 0

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return 1

    finally:
        # Ensure DB connection is closed
        if conn:
            try:
                conn.close()
            except:
                pass


if __name__ == "__main__":
    exit_code = run_pipeline()
    sys.exit(exit_code)
