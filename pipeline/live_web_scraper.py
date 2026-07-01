"""Live match data scraper - Extract real-time data from Sofascore & FotMob"""
import asyncio
import logging
import json
import re
from typing import Dict, List, Any, Optional
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

logger = logging.getLogger(__name__)


class SofascoreScraper:
    """Extract live match data from Sofascore"""

    SOFASCORE_BASE = "https://www.sofascore.com/football/match"

    async def fetch_live_match_data(self, match_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch live match data from Sofascore
        match_id format: "sofascore_{match_id}" or "{home_team}_vs_{away_team}"
        """
        try:
            # Sofascore uses numeric match IDs
            # For now, construct URL from team names if available
            url = self._build_sofascore_url(match_id)

            config = CrawlerRunConfig(
                wait_for="div[class*='event']",  # Wait for event data
                timeout=10,
                headless=True,
                javascript_enabled=True
            )

            async with AsyncWebCrawler(config=config) as crawler:
                result = await crawler.arun(url)

                if not result.success:
                    logger.warning(f"Sofascore crawl failed for {match_id}")
                    return None

                return self._parse_sofascore_html(result.html)

        except Exception as e:
            logger.error(f"Sofascore scrape error: {e}")
            return None

    def _build_sofascore_url(self, match_id: str) -> str:
        """Build Sofascore URL from match identifier"""
        # Example: https://www.sofascore.com/brazil-serbia/1q0X1q0Z
        # For development, use a known match pattern
        return f"{self.SOFASCORE_BASE}/brazil-serbia/1q0X1q0Z"

    def _parse_sofascore_html(self, html: str) -> Dict[str, Any]:
        """Parse live match data from Sofascore HTML"""
        try:
            # Extract live statistics from JavaScript data
            # Sofascore embeds data in window.__INITIAL_STATE__
            match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html)

            if match:
                data = json.loads(match.group(1))
                return self._extract_live_stats(data)

            return {
                'status': 'parse_error',
                'events': [],
                'statistics': {}
            }
        except Exception as e:
            logger.error(f"Sofascore parse error: {e}")
            return {}

    def _extract_live_stats(self, data: Dict) -> Dict[str, Any]:
        """Extract relevant live statistics from parsed data"""
        return {
            'events': data.get('events', []),
            'statistics': {
                'home': data.get('match', {}).get('homeTeam', {}).get('statistics', {}),
                'away': data.get('match', {}).get('awayTeam', {}).get('statistics', {})
            },
            'lineups': {
                'home': data.get('match', {}).get('homeTeam', {}).get('lineup', []),
                'away': data.get('match', {}).get('awayTeam', {}).get('lineup', [])
            }
        }


class FotmobScraper:
    """Extract live match data from FotMob"""

    FOTMOB_BASE = "https://www.fotmob.com/matches"

    async def fetch_live_match_data(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Fetch live match data from FotMob"""
        try:
            url = f"{self.FOTMOB_BASE}/{match_id}"

            config = CrawlerRunConfig(
                wait_for="div[class*='match']",
                timeout=10,
                headless=True,
                javascript_enabled=True
            )

            async with AsyncWebCrawler(config=config) as crawler:
                result = await crawler.arun(url)

                if not result.success:
                    logger.warning(f"FotMob crawl failed for {match_id}")
                    return None

                return self._parse_fotmob_html(result.html)

        except Exception as e:
            logger.error(f"FotMob scrape error: {e}")
            return None

    def _parse_fotmob_html(self, html: str) -> Dict[str, Any]:
        """Parse live match data from FotMob HTML"""
        try:
            # FotMob embeds data in window.__data__
            match = re.search(r'window\.__data__\s*=\s*({.*?});', html)

            if match:
                data = json.loads(match.group(1))
                return self._extract_match_data(data)

            return {
                'status': 'parse_error',
                'stats': [],
                'lineup': {}
            }
        except Exception as e:
            logger.error(f"FotMob parse error: {e}")
            return {}

    def _extract_match_data(self, data: Dict) -> Dict[str, Any]:
        """Extract relevant live statistics from FotMob data"""
        return {
            'stats': data.get('matchStats', []),
            'lineup': {
                'home': data.get('homeTeam', {}).get('lineup', []),
                'away': data.get('awayTeam', {}).get('lineup', [])
            },
            'events': data.get('events', []),
            'minute': data.get('minute', 0)
        }


class LiveWebDataAggregator:
    """Aggregate live data from multiple sources"""

    def __init__(self):
        self.sofascore = SofascoreScraper()
        self.fotmob = FotmobScraper()

    async def fetch_live_player_metrics(
        self, match_id: str, home_team: str, away_team: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch live player metrics from web sources
        Returns: {
            'home': [{'player_id': '...', 'distance_km': 9.2, 'passes': 45, ...}, ...],
            'away': [...]
        }
        """
        try:
            # Try Sofascore first (most detailed)
            sofascore_data = await self.sofascore.fetch_live_match_data(match_id)

            if sofascore_data:
                return self._normalize_player_metrics(sofascore_data, 'sofascore')

            # Fallback to FotMob
            fotmob_data = await self.fotmob.fetch_live_match_data(match_id)

            if fotmob_data:
                return self._normalize_player_metrics(fotmob_data, 'fotmob')

            logger.warning(f"No live data available for {match_id}")
            return {'home': [], 'away': []}

        except Exception as e:
            logger.error(f"Failed to fetch live metrics: {e}")
            return {'home': [], 'away': []}

    def _normalize_player_metrics(self, data: Dict, source: str) -> Dict[str, List[Dict]]:
        """Normalize metrics from different sources to standard format"""
        if source == 'sofascore':
            return self._normalize_sofascore(data)
        elif source == 'fotmob':
            return self._normalize_fotmob(data)
        return {'home': [], 'away': []}

    def _normalize_sofascore(self, data: Dict) -> Dict[str, List[Dict]]:
        """Convert Sofascore data to standard format"""
        metrics = {'home': [], 'away': []}

        for team in ['home', 'away']:
            team_key = 'home' if team == 'home' else 'away'
            stats = data.get('statistics', {}).get(team_key, {})

            for player in stats.get('players', []):
                metrics[team_key].append({
                    'player_id': player.get('id', ''),
                    'name': player.get('name', ''),
                    'position': player.get('position', 'MID'),
                    'distance_km': player.get('distance', 0),
                    'passes': player.get('passes', 0),
                    'pass_accuracy': player.get('passAccuracy', 0),
                    'tackles': player.get('tackles', 0),
                    'clearances': player.get('clearances', 0),
                    'shots': player.get('shots', 0),
                    'rating': player.get('rating', 0)
                })

        return metrics

    def _normalize_fotmob(self, data: Dict) -> Dict[str, List[Dict]]:
        """Convert FotMob data to standard format"""
        metrics = {'home': [], 'away': []}

        for team in ['home', 'away']:
            team_key = 'home' if team == 'home' else 'away'
            stats = data.get('stats', [])

            for player_stat in stats:
                if player_stat.get('team') != team:
                    continue

                metrics[team_key].append({
                    'player_id': player_stat.get('playerId', ''),
                    'name': player_stat.get('playerName', ''),
                    'position': player_stat.get('position', 'MID'),
                    'distance_km': player_stat.get('distanceCovered', 0),
                    'passes': player_stat.get('passes', 0),
                    'pass_accuracy': player_stat.get('passAccuracy', 0),
                    'tackles': player_stat.get('tackles', 0),
                    'clearances': player_stat.get('clearances', 0),
                    'shots': player_stat.get('shots', 0),
                    'rating': player_stat.get('rating', 0)
                })

        return metrics


async def main():
    """Test live data scrapers"""
    logging.basicConfig(level=logging.INFO)

    agg = LiveWebDataAggregator()
    metrics = await agg.fetch_live_player_metrics('sofascore_brazil_serbia', 'Brazil', 'Serbia')

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
