"""Live metrics fetcher - Real ESPN World Cup API integration"""
import asyncio
import logging
import requests
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class LiveMetricsFetcher:
    """Fetch real-time match data from ESPN World Cup API"""

    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"

    def __init__(self):
        self.session = requests.Session()
        logger.info("✓ LiveMetricsFetcher initialized (real ESPN API)")

    async def fetch_live_matches(self) -> List[Dict[str, Any]]:
        """Fetch live/scheduled World Cup matches from ESPN"""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self.session.get(f"{self.ESPN_BASE}/scoreboard", timeout=10)
            )
            data = response.json()

            matches = []
            for event in data.get('events', []):
                comp = event.get('competitions', [{}])[0]
                competitors = comp.get('competitors', [])

                if len(competitors) < 2:
                    continue

                # Parse status
                status_obj = event.get('status', {})
                status_type = status_obj.get('type', {})
                status_name = status_type.get('name', '').lower() if isinstance(status_type, dict) else ''
                status_state = status_type.get('state', '').lower() if isinstance(status_type, dict) else ''

                # Filter: only IN_PROGRESS or SCHEDULED matches
                if status_state == 'post':
                    continue

                is_live = status_state == 'in'
                is_scheduled = status_state == 'pre'

                if not (is_live or is_scheduled):
                    continue

                home = competitors[0]
                away = competitors[1]

                match = {
                    'match_id': event.get('id', ''),
                    'home_team': home.get('team', {}).get('displayName', ''),
                    'away_team': away.get('team', {}).get('displayName', ''),
                    'home_score': int(home.get('score', 0)) if is_live else 0,
                    'away_score': int(away.get('score', 0)) if is_live else 0,
                    'minute': self._parse_minute(status_obj.get('displayClock', '0:00')),
                    'status': 'LIVE' if is_live else 'SCHEDULED',
                    'lineups': {
                        'home': self._parse_lineup(comp.get('competitors', [{}])[0].get('lineup', [])),
                        'away': self._parse_lineup(comp.get('competitors', [{}])[1].get('lineup', []))
                    }
                }
                matches.append(match)

            logger.info(f"✓ Fetched {len(matches)} matches from ESPN")
            return matches
        except Exception as e:
            logger.error(f"✗ Failed to fetch ESPN: {e}")
            return []

    def _parse_minute(self, clock_str: str) -> int:
        """Parse minute from clock string like '67:30'"""
        try:
            return int(clock_str.split(':')[0].strip("'"))
        except (ValueError, IndexError):
            return 0

    def _parse_lineup(self, lineup: List[Dict]) -> List[Dict[str, Any]]:
        """Parse ESPN lineup format into player list"""
        return [
            {
                'player_id': entry.get('athlete', {}).get('id', ''),
                'name': entry.get('athlete', {}).get('displayName', ''),
                'position': entry.get('position', {}).get('abbreviation', 'MID'),
                'status': 'active' if i < 11 else 'bench'
            }
            for i, entry in enumerate(lineup[:20])
        ]

    async def close(self):
        self.session.close()
        logger.info("✓ LiveMetricsFetcher closed")


async def main():
    fetcher = LiveMetricsFetcher()
    matches = await fetcher.fetch_live_matches()
    print(f"Found {len(matches)} matches")
    for m in matches:
        print(f"  {m['home_team']} vs {m['away_team']} ({m['status']}, {m['minute']}')")
    await fetcher.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
