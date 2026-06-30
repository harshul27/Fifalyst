"""
Recommendation Engine Agent - Generates substitution recommendations
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict
import numpy as np

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class RecommendationEngineAgent(BaseAgent):
    """Generate substitution recommendations based on fitness"""

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        super().__init__(
            agent_name="RECOMMENDATION_ENGINE_AGENT",
            temperature=0.3,
            redis_host=redis_host,
            redis_port=redis_port,
            cache_ttl=300,
        )

    async def run(self, match_id: str = None, match_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Generate substitution recommendations"""
        self.start_cycle()

        try:
            if not match_data:
                self.end_cycle("WARNING", "No match data")
                return {"status": "NO_DATA"}

            minute = match_data.get("minute", 0)

            # Only generate recommendations after 30 minutes
            if minute < 30:
                logger.debug(f"Too early for recommendations (minute {minute} < 30)")
                return {
                    "status": "TOO_EARLY",
                    "match_id": match_id,
                    "minute": minute,
                    "recommendations": [],
                }

            logger.info(f"RecommendationEngineAgent: Generating recommendations for match {match_id}")

            home_team = match_data.get("home_team", "Unknown")
            away_team = match_data.get("away_team", "Unknown")

            # Generate synthetic recommendations
            recommendations = {
                "match_id": match_id,
                "minute": minute,
                "home_recommendations": [
                    {
                        "off_player_id": f"{home_team}_P5",
                        "off_player_name": "Tired Player",
                        "off_position": "CM",
                        "off_fitness": 45.0,
                        "off_fatigue_pct": 85.0,
                        "on_player_id": f"{home_team}_S1",
                        "on_player_name": "Fresh Player",
                        "on_fitness": 95.0,
                        "impact_score": 5.2,
                        "confidence": 0.82,
                        "reasons": ["High fatigue", "Defensive pressure"],
                        "subs_remaining": 2,
                    }
                ],
                "away_recommendations": [],
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Store to Redis
            if self.redis_client:
                self.redis_client.setex(
                    f"fifa:match:{match_id}:recommendations",
                    300,
                    json.dumps(recommendations)
                )

            self.end_cycle("SUCCESS")
            return {
                "status": "SUCCESS",
                "match_id": match_id,
                "recommendations": recommendations,
            }

        except Exception as e:
            logger.error(f"RecommendationEngineAgent error: {e}")
            self.end_cycle("ERROR", str(e))
            return {"status": "ERROR", "error": str(e)}
