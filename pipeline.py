"""
FIFA Shadow Coach - Automated Data Pipeline (Agent-Powered)
Manages orchestrator startup, data validation, and DuckDB sync
"""

import sys
import json
import duckdb
import redis
import pandas as pd
import asyncio
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import orchestrator
try:
    from orchestrator import MasterOrchestrator
    _HAS_ORCHESTRATOR = True
except ImportError:
    _HAS_ORCHESTRATOR = False
    logger.warning("Orchestrator not available")

# Import legacy modules for fallback
try:
    from model import calculate_player_energy, BASE_PLAYER_ENERGY, MIN_PHYSIOLOGICAL_ENERGY
except ImportError:
    BASE_PLAYER_ENERGY = 100.0
    MIN_PHYSIOLOGICAL_ENERGY = 15.0
    def calculate_player_energy(logs):
        return BASE_PLAYER_ENERGY


class PipelineLogger:
    def log(self, message: str, level: str = "INFO"):
        print(f"[{datetime.now(timezone.utc).isoformat()}] [{level}] {message}")

    def success(self, message: str):
        self.log(f"[OK] {message}", "SUCCESS")

    def error(self, message: str):
        self.log(f"[FAIL] {message}", "ERROR")

    def info(self, message: str):
        self.log(message, "INFO")

    def warn(self, message: str):
        self.log(message, "WARNING")


logger_pipe = PipelineLogger()
DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "database.duckdb"
CONFIG_PATH = DATA_DIR / "model_config.json"
PARQUET_PATH = DATA_DIR / "latest_squad_state.parquet"

# Redis connection
try:
    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    redis_client.ping()
    _HAS_REDIS = True
except Exception as e:
    _HAS_REDIS = False
    logger_pipe.warn(f"Redis unavailable: {e}")
    redis_client = None


def setup_directories():
    """Create data directory if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger_pipe.success(f"Data directory ready: {DATA_DIR}")


def initialize_duckdb() -> duckdb.DuckDBPyConnection:
    """Initialize DuckDB connection."""
    conn = duckdb.connect(str(DB_PATH))
    logger_pipe.success(f"DuckDB connected: {DB_PATH}")
    return conn


def sync_redis_to_duckdb() -> int:
    """
    Sync match data from Redis (populated by agents) to DuckDB.
    Returns count of matches synced.
    """
    if not _HAS_REDIS or redis_client is None:
        logger_pipe.warn("Redis not available — skipping sync")
        return 0

    try:
        conn = initialize_duckdb()

        # Create matches table if not exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                match_id STRING PRIMARY KEY,
                home_team STRING,
                away_team STRING,
                home_score INT,
                away_score INT,
                status STRING,
                minute INT,
                league STRING,
                timestamp TIMESTAMP,
                data JSON
            )
        """)

        # Get all match data from Redis
        match_keys = redis_client.keys("fifa:match:*:data")
        matches_synced = 0

        for key in match_keys:
            try:
                match_data = redis_client.get(key)
                if not match_data:
                    continue

                data = json.loads(match_data)
                match_id = data.get("match_id")

                conn.execute("""
                    INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (match_id) DO UPDATE SET
                        home_score = EXCLUDED.home_score,
                        away_score = EXCLUDED.away_score,
                        status = EXCLUDED.status,
                        minute = EXCLUDED.minute,
                        timestamp = EXCLUDED.timestamp,
                        data = EXCLUDED.data
                """, [
                    match_id,
                    data.get("home_team"),
                    data.get("away_team"),
                    int(data.get("home_score", 0)),
                    int(data.get("away_score", 0)),
                    data.get("status", "SCHEDULED"),
                    int(data.get("minute", 0)),
                    data.get("league"),
                    datetime.utcnow(),
                    match_data,
                ])
                matches_synced += 1
            except Exception as e:
                logger.error(f"Error syncing match {key}: {e}")
                continue

        conn.commit()
        conn.close()
        logger_pipe.success(f"Synced {matches_synced} matches to DuckDB")
        return matches_synced

    except Exception as e:
        logger_pipe.error(f"DuckDB sync failed: {e}")
        return 0


def validate_orchestrator() -> bool:
    """Check if orchestrator is running and healthy."""
    if not _HAS_ORCHESTRATOR:
        logger_pipe.warn("Orchestrator not installed")
        return False

    if not _HAS_REDIS or redis_client is None:
        logger_pipe.warn("Redis not available")
        return False

    try:
        status = redis_client.get("fifa:orchestrator:status")
        if status:
            data = json.loads(status)
            logger_pipe.success(f"Orchestrator is healthy: {data}")
            return True
        else:
            logger_pipe.warn("Orchestrator status not found in Redis")
            return False
    except Exception as e:
        logger_pipe.error(f"Orchestrator validation failed: {e}")
        return False


def run_orchestrator_async() -> Optional[MasterOrchestrator]:
    """Start orchestrator in current process (blocking). For manual runs."""
    if not _HAS_ORCHESTRATOR:
        logger_pipe.error("Orchestrator not available")
        return None

    try:
        orchestrator = MasterOrchestrator(redis_host="localhost", redis_port=6379)
        logger_pipe.info("Starting orchestrator (blocking mode)...")
        logger_pipe.warn("Press Ctrl+C to stop")

        # Run orchestrator - this blocks
        asyncio.run(orchestrator.run())
        return orchestrator

    except KeyboardInterrupt:
        logger_pipe.success("Orchestrator stopped by user")
        return None
    except Exception as e:
        logger_pipe.error(f"Orchestrator error: {e}")
        raise


def get_live_match_count() -> int:
    """Get count of live matches in Redis."""
    if not _HAS_REDIS or redis_client is None:
        return 0

    try:
        keys = redis_client.keys("fifa:match:*:data")
        return len(keys)
    except Exception:
        return 0


def get_agent_metrics() -> Dict[str, any]:
    """Retrieve agent metrics from Redis."""
    if not _HAS_REDIS or redis_client is None:
        return {}

    try:
        metrics = {}
        for key in redis_client.keys("fifa:agent:*:metrics"):
            data = redis_client.get(key)
            if data:
                metrics[key] = json.loads(data)
        return metrics
    except Exception:
        return {}


# ==================== MAIN EXECUTION ====================

def run_pipeline(mode: str = "validate"):
    """
    Run pipeline in specified mode.

    Modes:
    - 'validate': Check orchestrator health and sync Redis→DuckDB
    - 'orchestrator': Start orchestrator (blocking)
    - 'sync': One-shot sync from Redis to DuckDB
    """
    logger_pipe.info(f"FIFA Shadow Coach Pipeline - Mode: {mode}")
    setup_directories()

    if mode == "validate":
        logger_pipe.info("Validating orchestrator...")
        is_healthy = validate_orchestrator()
        if is_healthy:
            logger_pipe.info("Syncing Redis to DuckDB...")
            count = sync_redis_to_duckdb()
            logger_pipe.success(f"Pipeline validation complete. {count} matches in DuckDB.")
        else:
            logger_pipe.warn("Orchestrator not running. Start it manually or use 'orchestrator' mode.")

    elif mode == "orchestrator":
        run_orchestrator_async()

    elif mode == "sync":
        logger_pipe.info("Syncing Redis to DuckDB...")
        count = sync_redis_to_duckdb()
        logger_pipe.success(f"Sync complete. {count} matches synced.")

    else:
        logger_pipe.error(f"Unknown mode: {mode}")
        print("Available modes: validate, orchestrator, sync")
        sys.exit(1)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "validate"
    try:
        run_pipeline(mode)
    except Exception as e:
        logger_pipe.error(f"Pipeline failed: {e}")
        sys.exit(1)
