"""
Data Collection Agent - Fetches live match data from ESPN and Sofascore
Simplified for reliability over LLM reasoning
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DataCollectionAgent(BaseAgent):
    """Fetch live match data from ESPN API and Sofascore"""

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        espn_base_url: str = "https://site.api.espn.com/apis/site/v2",
        sofascore_base_url: str = "https://api.sofascore.com/api/v1",
    ):
        super().__init__(
            agent_name="DATA_COLLECTION_AGENT",
            temperature=0.1,
            redis_host=redis_host,
            redis_port=redis_port,
            cache_ttl=300,
        )

        # HTTP session with retries
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.espn_base_url = espn_base_url
        self.sofascore_base_url = sofascore_base_url

    async def _fetch_espn_matches(self) -> List[Dict[str, Any]]:
        """Fetch World Cup matches from ESPN"""
        try:
            url = f"{self.espn_base_url}/sports/soccer/fifa.world/scoreboard"
            response = await asyncio.to_thread(self.session.get, url, timeout=10)
            response.raise_for_status()

            data = response.json()
            events = data.get("events", [])

            matches = []
            for event in events:
                match = {
                    "match_id": event.get("id"),
                    "home_team": event.get("competitions", [{}])[0].get("competitors", [{}])[0].get("team", {}).get("displayName", "Unknown"),
                    "away_team": event.get("competitions", [{}])[0].get("competitors", [{}])[1].get("team", {}).get("displayName", "Unknown") if len(event.get("competitions", [{}])[0].get("competitors", [])) > 1 else "Unknown",
                    "home_score": int(event.get("competitions", [{}])[0].get("competitors", [{}])[0].get("score", 0)),
                    "away_score": int(event.get("competitions", [{}])[0].get("competitors", [{}])[1].get("score", 0)) if len(event.get("competitions", [{}])[0].get("competitors", [])) > 1 else 0,
                    "status": event.get("status", {}).get("type", "UNKNOWN"),
                    "minute": 0,
                    "league": "fifa.world",
                    "timestamp": datetime.utcnow().isoformat(),
                }
                matches.append(match)

            logger.info(f"Fetched {len(matches)} matches from ESPN")
            return matches

        except Exception as e:
            logger.error(f"ESPN fetch error: {e}")
            return []

    async def _store_matches_to_redis(self, matches: List[Dict[str, Any]]) -> int:
        """Store matches to Redis"""
        if not self.redis_client:
            return 0

        stored = 0
        for match in matches:
            try:
                key = f"fifa:match:{match['match_id']}:data"
                self.redis_client.setex(key, 300, json.dumps(match))
                stored += 1
            except Exception as e:
                logger.error(f"Redis store error for {match.get('match_id')}: {e}")

        return stored

    async def run(self) -> Dict[str, Any]:
        """Main data collection cycle"""
        self.start_cycle()

        try:
            logger.info("DataCollectionAgent: Starting data collection")

            # Fetch matches
            matches = await self._fetch_espn_matches()

            if not matches:
                logger.warning("No matches found")
                self.end_cycle("WARNING", "No matches")
                return {
                    "status": "NO_MATCHES",
                    "matches_processed": 0,
                    "matches": [],
                }

            # Store to Redis
            stored = await self._store_matches_to_redis(matches)

            self.end_cycle("SUCCESS")
            logger.info(f"DataCollectionAgent: Complete ({stored}/{len(matches)} stored)")

            return {
                "status": "SUCCESS",
                "matches_processed": len(matches),
                "matches_stored": stored,
                "matches": matches,
            }

        except Exception as e:
            logger.error(f"DataCollectionAgent error: {e}")
            self.end_cycle("ERROR", str(e))
            return {
                "status": "ERROR",
                "error": str(e),
                "matches": [],
            }
