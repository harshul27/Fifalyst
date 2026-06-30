"""
Fitness Model Agent - Computes player energy/fitness scores
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict
import numpy as np

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class FitnessModelAgent(BaseAgent):
    """Compute player fitness scores"""

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        super().__init__(
            agent_name="FITNESS_MODEL_AGENT",
            temperature=0.0,
            redis_host=redis_host,
            redis_port=redis_port,
            cache_ttl=300,
        )

    async def run(self, match_id: str = None, match_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Compute fitness for teams in a match"""
        self.start_cycle()

        try:
            if not match_data:
                self.end_cycle("WARNING", "No match data")
                return {"status": "NO_DATA"}

            logger.info(f"FitnessModelAgent: Computing fitness for match {match_id}")

            home_team = match_data.get("home_team", "Unknown")
            away_team = match_data.get("away_team", "Unknown")

            # Generate synthetic fitness data
            home_fitness = {
                "team": home_team,
                "match_id": match_id,
                "players": {
                    f"{home_team}_P{i}": {
                        "player_id": f"{home_team}_P{i}",
                        "position": ["GK", "CB", "LB", "CM", "RM", "LW", "ST"][i % 7],
                        "fitness": float(np.random.uniform(70, 95)),
                        "minutes": int(np.random.randint(0, 90)),
                    }
                    for i in range(11)
                },
                "avg_fitness": 82.5,
                "timestamp": datetime.utcnow().isoformat(),
            }

            away_fitness = {
                "team": away_team,
                "match_id": match_id,
                "players": {
                    f"{away_team}_P{i}": {
                        "player_id": f"{away_team}_P{i}",
                        "position": ["GK", "CB", "LB", "CM", "RM", "LW", "ST"][i % 7],
                        "fitness": float(np.random.uniform(70, 95)),
                        "minutes": int(np.random.randint(0, 90)),
                    }
                    for i in range(11)
                },
                "avg_fitness": 82.5,
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Store to Redis
            if self.redis_client:
                self.redis_client.setex(
                    f"fifa:match:{match_id}:fitness:{home_team}",
                    300,
                    json.dumps(home_fitness)
                )
                self.redis_client.setex(
                    f"fifa:match:{match_id}:fitness:{away_team}",
                    300,
                    json.dumps(away_fitness)
                )

            self.end_cycle("SUCCESS")
            return {
                "status": "SUCCESS",
                "match_id": match_id,
                "home_fitness": home_fitness,
                "away_fitness": away_fitness,
            }

        except Exception as e:
            logger.error(f"FitnessModelAgent error: {e}")
            self.end_cycle("ERROR", str(e))
            return {"status": "ERROR", "error": str(e)}
