"""
FIFA World Cup 2026 - Simplified Live Match Orchestrator
Coordinates data fetching, fitness calculation, and recommendations
No agents needed - direct pipeline coordination
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd

from pipeline.live_metrics_fetcher import LiveMetricsFetcher
from pipeline.match_state_tracker import MatchStateTracker
from pipeline.live_fitness_calculator import LiveFitnessCalculator

logger = logging.getLogger(__name__)


class LiveMatchOrchestrator:
    """Lightweight orchestrator for live World Cup match tracking"""

    WC_TEAMS = {
        "United States", "Mexico", "Canada", "Brazil", "Argentina", "Uruguay", "Paraguay",
        "England", "France", "Germany", "Spain", "Netherlands", "Italy", "Portugal", "Belgium",
        "Japan", "South Korea", "Australia", "Saudi Arabia", "Iran", "United Arab Emirates",
        "Senegal", "Nigeria", "Morocco", "Cameroon", "Egypt", "Ivory Coast", "Tunisia",
        "Costa Rica", "Panama", "New Zealand", "Indonesia", "Malaysia",
        "Colombia", "Ecuador", "Denmark", "Sweden", "Poland", "Austria", "Czechia",
        "Switzerland", "Serbia", "Norway", "Ghana", "Mali"
    }

    def __init__(self):
        self.fetcher = LiveMetricsFetcher()
        self.state_tracker = MatchStateTracker()
        self.fitness_calc = LiveFitnessCalculator()
        self.live_matches = {}
        self.last_update = None

    async def fetch_live_matches(self) -> List[Dict[str, Any]]:
        """Fetch live World Cup matches from ESPN"""
        try:
            matches = await self.fetcher.fetch_live_matches()
            # Filter to WC teams only
            wc_matches = [
                m for m in matches
                if m.get('home_team') in self.WC_TEAMS and m.get('away_team') in self.WC_TEAMS
            ]
            logger.info(f"✓ Fetched {len(wc_matches)} WC matches from ESPN")
            return wc_matches
        except Exception as e:
            logger.error(f"✗ Failed to fetch matches: {e}")
            return []

    async def process_match(self, match: Dict[str, Any]) -> Dict[str, Any]:
        """Process single match: update state, calculate fitness, generate recommendations"""
        try:
            match_id = match.get('match_id', f"{match.get('home_team')}_{match.get('away_team')}")
            minute = match.get('minute', 0)

            # Update match state
            home_team = match.get('home_team')
            away_team = match.get('away_team')
            home_score = match.get('home_score', 0)
            away_score = match.get('away_score', 0)
            lineups = match.get('lineups', {})

            state = self.state_tracker.update_match_state(
                match_id, home_team, away_team, minute,
                home_score, away_score,
                lineups.get('home', []), lineups.get('away', [])
            )

            # Calculate live fitness for all players
            home_players = [
                {
                    'player_id': p.get('player_id', p.get('name', 'unknown')),
                    'name': p.get('name', ''),
                    'position': p.get('position', 'MID'),
                    'baseline_fitness': 80 + (hash(str(p.get('player_id'))) % 20 - 10)
                }
                for p in (state.home_lineup if hasattr(state, 'home_lineup') else state.get('home_lineup', []))
            ]
            away_players = [
                {
                    'player_id': p.get('player_id', p.get('name', 'unknown')),
                    'name': p.get('name', ''),
                    'position': p.get('position', 'MID'),
                    'baseline_fitness': 80 + (hash(str(p.get('player_id'))) % 20 - 10)
                }
                for p in (state.away_lineup if hasattr(state, 'away_lineup') else state.get('away_lineup', []))
            ]

            # Mock live metrics (in production, fetch from Sofascore/ESPN)
            live_metrics = [
                {
                    'player_id': p['player_id'],
                    'running_load_pct': 80 + (hash(str(p['player_id'])) % 30 - 15)
                }
                for p in home_players + away_players
            ]

            # Calculate fitness for both teams
            home_fitness_list = await self.fitness_calc.calculate_fitness(home_players, live_metrics, minute)
            away_fitness_list = await self.fitness_calc.calculate_fitness(away_players, live_metrics, minute)

            fitness_scores = {
                'home': [
                    {
                        'name': p.name,
                        'player_id': p.player_id,
                        'fitness': p.current_fitness,
                        'fatigue_pct': p.fatigue_pct,
                        'minutes_on': minute,
                        'status': p.fatigue_status
                    }
                    for p in home_fitness_list
                ],
                'away': [
                    {
                        'name': p.name,
                        'player_id': p.player_id,
                        'fitness': p.current_fitness,
                        'fatigue_pct': p.fatigue_pct,
                        'minutes_on': minute,
                        'status': p.fatigue_status
                    }
                    for p in away_fitness_list
                ]
            }

            # Generate substitution recommendations
            recommendations = self._generate_recommendations(
                state, fitness_scores, match.get('home_score', 0), match.get('away_score', 0)
            )

            result = {
                'match_id': match_id,
                'status': state.state if hasattr(state, 'state') else state.get('status', 'LIVE'),
                'minute': minute,
                'score': f"{home_score}-{away_score}",
                'home_team': home_team,
                'away_team': away_team,
                'home_fitness': fitness_scores.get('home', []),
                'away_fitness': fitness_scores.get('away', []),
                'recommendations': recommendations,
                'timestamp': datetime.now().isoformat()
            }

            self.live_matches[match_id] = result
            return result
        except Exception as e:
            logger.error(f"✗ Failed to process match: {e}")
            return {}

    def _generate_recommendations(
        self, state: Dict, fitness_scores: Dict, home_score: int, away_score: int
    ) -> List[Dict]:
        """Generate substitution recommendations based on fatigue and team status"""
        recommendations = []

        # Only recommend after 30 minutes
        minute = state.minute if hasattr(state, 'minute') else state.get('minute', 0)
        if minute < 30:
            return recommendations

        for team_key in ['home', 'away']:
            subs_remaining = self.state_tracker.get_available_subs(
                state.match_id if hasattr(state, 'match_id') else state.get('match_id', ''),
                team_key
            )
            if subs_remaining <= 0:
                continue

            players = fitness_scores.get(team_key, [])
            if not players:
                continue

            # Find tired starters (fitness < 50%, played > 30 min)
            tired = [p for p in players if p.get('fitness', 100) < 50 and p.get('minutes_on', 0) > 30]
            # Find fresh bench players (fitness > 80%, not used yet)
            bench = [p for p in players if p.get('fitness', 100) > 80 and p.get('minutes_on', 0) == 0]

            if tired and bench:
                tired = sorted(tired, key=lambda x: x.get('fitness', 100))
                bench = sorted(bench, key=lambda x: x.get('fitness', 100), reverse=True)

                tired_player = tired[0]
                fresh_player = bench[0]

                # Confidence: higher fatigue % = higher confidence
                fatigue_component = min(tired_player.get('fatigue_pct', 0) / 100, 1.0)
                confidence = 0.60 + (fatigue_component * 0.35)  # 0.60-0.95 range

                recommendations.append({
                    'off': tired_player.get('name', 'Unknown'),
                    'off_fitness': round(tired_player.get('fitness', 100), 1),
                    'on': fresh_player.get('name', 'Unknown'),
                    'on_fitness': round(fresh_player.get('fitness', 100), 1),
                    'confidence': round(confidence, 3),
                    'reason': 'HIGH_FATIGUE',
                    'team': team_key,
                    'subs_remaining': subs_remaining - 1
                })

        return sorted(recommendations, key=lambda x: x.get('confidence', 0), reverse=True)[:3]

    async def run_cycle(self) -> Dict[str, Any]:
        """Run one 5-minute processing cycle"""
        try:
            logger.info(f"\n{'='*70}")
            logger.info(f"LIVE MATCH CYCLE - {datetime.now().strftime('%H:%M:%S')}")
            logger.info(f"{'='*70}")

            # Fetch live matches
            matches = await self.fetch_live_matches()

            if not matches:
                logger.info("ℹ️  No live WC matches at this time")
                return {'matches': [], 'timestamp': datetime.now().isoformat()}

            # Process each match in parallel
            tasks = [self.process_match(m) for m in matches]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            processed = [r for r in results if isinstance(r, dict) and r]
            self.last_update = datetime.now().isoformat()

            logger.info(f"✓ Processed {len(processed)} matches")

            return {
                'matches': processed,
                'count': len(processed),
                'timestamp': self.last_update
            }
        except Exception as e:
            logger.error(f"✗ Cycle failed: {e}")
            return {'matches': [], 'error': str(e), 'timestamp': datetime.now().isoformat()}

    async def continuous_loop(self, interval_seconds: int = 300):
        """Run continuous 5-minute refresh loop"""
        logger.info(f"Starting live match monitoring loop (refresh every {interval_seconds}s)")

        try:
            while True:
                await self.run_cycle()
                await asyncio.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("Live monitoring stopped")


# Singleton instance for Streamlit caching
_orchestrator = None

def get_orchestrator() -> LiveMatchOrchestrator:
    """Get or create singleton orchestrator"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = LiveMatchOrchestrator()
    return _orchestrator


async def main():
    """Test orchestrator"""
    logging.basicConfig(level=logging.INFO)
    orch = LiveMatchOrchestrator()
    result = await orch.run_cycle()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
