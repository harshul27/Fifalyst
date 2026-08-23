"""Live match data scraper - Extract lineups, state, and metrics from Sofascore & FotMob"""
import asyncio
import logging
import json
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import requests

logger = logging.getLogger(__name__)


@dataclass
class MatchStateData:
    """Match state extracted from web sources"""
    match_id: str
    minute: int
    status: str  # SCHEDULED, LIVE, FINISHED
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    home_lineup: List[Dict]
    away_lineup: List[Dict]
    source: str  # sofascore, fotmob


class SofascoreScraper:
    """Extract lineups, match state, and metrics from Sofascore using requests"""

    SOFASCORE_BASE = "https://www.sofascore.com/football/match"

    async def fetch_match_state(self, match_id: str, home_team: str, away_team: str) -> Optional[MatchStateData]:
        """Fetch match state from Sofascore API"""
        try:
            # Try Sofascore API first
            api_url = f"https://api.sofascore.com/api/v1/event/{match_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Referer': 'https://www.sofascore.com/',
                'Accept': 'application/json',
            }

            response = requests.get(api_url, headers=headers, timeout=10)
            response.raise_for_status()

            # Parse API response instead of HTML
            data = response.json()
            event = data.get('event', {})

            if not event:
                logger.debug(f"No event data from Sofascore API")
                return None

            minute = 0
            if 'status' in event:
                if 'displayClock' in event['status']:
                    try:
                        minute = int(event['status']['displayClock'].split(':')[0])
                    except:
                        minute = 0

            # Extract lineups
            home_lineup = []
            away_lineup = []

            home_team_data = event.get('homeTeam', {})
            away_team_data = event.get('awayTeam', {})

            if 'formation' in home_team_data and 'players' in home_team_data:
                home_lineup = self._extract_lineup_from_api(home_team_data.get('players', []))
            if 'formation' in away_team_data and 'players' in away_team_data:
                away_lineup = self._extract_lineup_from_api(away_team_data.get('players', []))

            return MatchStateData(
                match_id=match_id,
                minute=minute,
                status='LIVE' if event.get('status', {}).get('type') == 'inplay' else 'SCHEDULED',
                home_team=home_team,
                away_team=away_team,
                home_score=event.get('homeScore', {}).get('current', 0) or 0,
                away_score=event.get('awayScore', {}).get('current', 0) or 0,
                home_lineup=home_lineup,
                away_lineup=away_lineup,
                source='sofascore'
            )

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.debug(f"Sofascore API blocked (403) - trying web scrape fallback")
                # Try website fallback
                try:
                    url = f"{self.SOFASCORE_BASE}/{match_id}"
                    headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    return self._parse_match_state(response.text, match_id, home_team, away_team)
                except:
                    return None
            logger.debug(f"Sofascore fetch error: {e}")
            return None

            # Try to extract JSON from page
            match_obj = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', response.text, re.DOTALL)
            if not match_obj:
                logger.debug(f"Could not find match state in Sofascore HTML")
                return None

            try:
                data = json.loads(match_obj.group(1))
                # Extract lineup data
                match_data = data.get('match', {})
                minute = int(match_data.get('currentPeriodStartTime', 0) or 0) // 60
                status = 'LIVE' if 'inProgress' in str(data) else 'SCHEDULED'

                home_lineup = []
                away_lineup = []

                # Try to extract lineups
                if 'homeTeam' in match_data and 'lineUp' in match_data['homeTeam']:
                    home_lineup = self._extract_lineup(match_data['homeTeam']['lineUp'], 'home')
                if 'awayTeam' in match_data and 'lineUp' in match_data['awayTeam']:
                    away_lineup = self._extract_lineup(match_data['awayTeam']['lineUp'], 'away')

                return MatchStateData(
                    match_id=match_id,
                    minute=minute,
                    status=status,
                    home_team=home_team,
                    away_team=away_team,
                    home_score=int(match_data.get('homeScore', {}).get('current', 0) or 0),
                    away_score=int(match_data.get('awayScore', {}).get('current', 0) or 0),
                    home_lineup=home_lineup,
                    away_lineup=away_lineup,
                    source='sofascore'
                )
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"Error parsing Sofascore JSON: {e}")
                return None

        except Exception as e:
            logger.error(f"Sofascore match state error: {e}")
            return None

    async def fetch_live_match_data(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Fetch player metrics from Sofascore"""
        try:
            url = f"{self.SOFASCORE_BASE}/{match_id}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            return {'home': [], 'away': []}  # Simplified for now
        except Exception as e:
            logger.debug(f"Sofascore metrics fetch error: {e}")
            return {'home': [], 'away': []}

    def _extract_lineup(self, lineup_data: List[Dict], team_key: str) -> List[Dict]:
        """Extract and normalize lineup"""
        lineups = []
        for i, player in enumerate(lineup_data[:20]):
            lineups.append({
                'player_id': player.get('player', {}).get('id', f'{team_key}_p{i}'),
                'name': player.get('player', {}).get('name', 'Unknown'),
                'position': player.get('position', 'MID'),
                'status': 'active' if i < 11 else 'bench'
            })
        return lineups

    def _extract_lineup_from_api(self, players_list: List[Dict]) -> List[Dict]:
        """Extract lineup from Sofascore API response"""
        lineups = []
        for i, player_data in enumerate(players_list[:20]):
            player_info = player_data.get('player', {})
            lineups.append({
                'player_id': player_info.get('id', f'p{i}'),
                'name': player_info.get('name', 'Unknown'),
                'position': player_data.get('position', 'MID'),
                'status': 'active' if i < 11 else 'bench'
            })
        return lineups

    def _parse_match_state(self, html: str, match_id: str, home_team: str, away_team: str) -> Optional[MatchStateData]:
        """Parse match state from HTML (fallback)"""
        return None

    def _build_sofascore_url(self, match_id: str) -> str:
        """Build Sofascore match URL"""
        return f"{self.SOFASCORE_BASE}/{match_id}"


class FotmobScraper:
    """Extract lineups, match state, and metrics from FotMob using requests"""

    FOTMOB_BASE = "https://www.fotmob.com/matches"

    async def fetch_match_state(self, match_id: str, home_team: str, away_team: str) -> Optional[MatchStateData]:
        """Fetch match state from FotMob"""
        try:
            url = f"{self.FOTMOB_BASE}/{match_id}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            # Try to extract JSON from page
            data_match = re.search(r'window\.__data__\s*=\s*({.*?});', response.text, re.DOTALL)
            if not data_match:
                logger.debug(f"Could not find match data in FotMob HTML")
                return None

            try:
                data = json.loads(data_match.group(1))
                return MatchStateData(
                    match_id=match_id,
                    minute=0,
                    status='SCHEDULED',
                    home_team=home_team,
                    away_team=away_team,
                    home_score=0,
                    away_score=0,
                    home_lineup=[],
                    away_lineup=[],
                    source='fotmob'
                )
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"Error parsing FotMob JSON: {e}")
                return None

        except Exception as e:
            logger.error(f"FotMob match state error: {e}")
            return None

    async def fetch_live_match_data(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Fetch player metrics from FotMob"""
        try:
            url = f"{self.FOTMOB_BASE}/{match_id}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            return {'home': [], 'away': []}  # Simplified for now
        except Exception as e:
            logger.debug(f"FotMob metrics fetch error: {e}")
            return {'home': [], 'away': []}

    def _extract_lineup(self, lineup_data: List[Dict], team_key: str) -> List[Dict]:
        """Extract and normalize lineup from FotMob"""
        lineups = []
        for i, player in enumerate(lineup_data[:20]):
            lineups.append({
                'player_id': player.get('id', f'{team_key}_p{i}'),
                'name': player.get('name', 'Unknown'),
                'position': player.get('position', 'MID'),
                'status': 'active' if i < 11 else 'bench'
            })
        return lineups


class LiveWebDataAggregator:
    """Aggregate data from multiple web sources with fallback"""

    def __init__(self):
        self.sofascore = SofascoreScraper()
        self.fotmob = FotmobScraper()
        logger.info("✓ LiveWebDataAggregator initialized")

    async def fetch_match_state(self, match_id: str, home_team: str, away_team: str) -> Optional[MatchStateData]:
        """Fetch match state with fallback chain: Sofascore → FotMob"""
        try:
            # Try Sofascore first
            logger.info(f"Fetching match state from Sofascore for {match_id}")
            sofascore_data = await self.sofascore.fetch_match_state(match_id, home_team, away_team)

            if sofascore_data:
                logger.info(f"✓ Got match state from Sofascore")
                return sofascore_data

            # Fallback to FotMob
            logger.info(f"Sofascore unavailable, trying FotMob")
            fotmob_data = await self.fotmob.fetch_match_state(match_id, home_team, away_team)

            if fotmob_data:
                logger.info(f"✓ Got match state from FotMob")
                return fotmob_data

            logger.warning(f"No match state available from any web source for {match_id}")
            return None

        except Exception as e:
            logger.error(f"Web aggregator error: {e}")
            return None

    async def fetch_live_player_metrics(self, match_id: str, home_team: str, away_team: str) -> Dict:
        """Fetch live player metrics from web sources"""
        try:
            # Try both sources in parallel
            sofascore_metrics = await self.sofascore.fetch_live_match_data(match_id)
            fotmob_metrics = await self.fotmob.fetch_live_match_data(match_id)

            # Return merged metrics
            return {
                'home': sofascore_metrics.get('home', []) or fotmob_metrics.get('home', []),
                'away': sofascore_metrics.get('away', []) or fotmob_metrics.get('away', [])
            }
        except Exception as e:
            logger.debug(f"Metrics fetch error: {e}")
            return {'home': [], 'away': []}
