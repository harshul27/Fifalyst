"""
Live Match Agent - Tracks live match state and lineups
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class LiveMatchAgent(BaseAgent):
    """Track live match state and lineups"""

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        super().__init__(
            agent_name="LIVE_MATCH_AGENT",
            temperature=0.0,
            redis_host=redis_host,
            redis_port=redis_port,
            cache_ttl=60,
        )

    async def run(self, match_id: str = None, match_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Track live match state"""
        self.start_cycle()

        try:
            if not match_data:
                self.end_cycle("WARNING", "No match data")
                return {"status": "NO_DATA"}

            logger.info(f"LiveMatchAgent: Tracking match {match_id}")

            match_state = {
                "match_id": match_id,
                "status": match_data.get("status", "UNKNOWN"),
                "minute": match_data.get("minute", 0),
                "home_team": match_data.get("home_team"),
                "away_team": match_data.get("away_team"),
                "home_score": match_data.get("home_score", 0),
                "away_score": match_data.get("away_score", 0),
                "home_lineup": [],
                "away_lineup": [],
                "substitutions": [],
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Store to Redis
            if self.redis_client:
                self.redis_client.setex(
                    f"fifa:match:{match_id}:state",
                    60,
                    json.dumps(match_state)
                )

            self.end_cycle("SUCCESS")
            return {
                "status": "SUCCESS",
                "match_id": match_id,
                "match_state": match_state,
            }

        except Exception as e:
            logger.error(f"LiveMatchAgent error: {e}")
            self.end_cycle("ERROR", str(e))
            return {"status": "ERROR", "error": str(e)}
