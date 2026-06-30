"""Match state tracker"""
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
import json
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class MatchState:
    match_id: str
    home_team: str
    away_team: str
    state: str
    minute: int
    home_score: int
    away_score: int
    home_lineup: list
    away_lineup: list
    substitutions_used: dict
    last_updated: str

class MatchStateTracker:
    def __init__(self, state_file=".cache/match_states.json"):
        self.state_file = Path(state_file)
        self.states = {}

    def update_match_state(self, match_id, home_team, away_team, minute, home_score, away_score, home_lineup, away_lineup):
        if minute == 0: state = 'SCHEDULED'
        elif 0 < minute < 45: state = 'LIVE_1ST'
        elif minute == 45: state = 'HALFTIME'
        elif 45 < minute < 90: state = 'LIVE_2ND'
        else: state = 'FINISHED'
        
        subs_used = self.states.get(match_id, {}).get('subs', {'home': 0, 'away': 0}) if isinstance(self.states.get(match_id), dict) else {'home': 0, 'away': 0}
        
        match_state = MatchState(match_id=match_id, home_team=home_team, away_team=away_team, state=state, minute=minute, home_score=home_score, away_score=away_score, home_lineup=home_lineup, away_lineup=away_lineup, substitutions_used=subs_used, last_updated=datetime.now().isoformat())
        self.states[match_id] = match_state
        logger.debug(f"Updated {match_id}: {state} (min {minute})")
        return match_state

    def get_available_subs(self, match_id, team):
        state = self.states.get(match_id)
        if not state: return 5
        used = state.substitutions_used.get(team, 0)
        return max(0, 5 - used)

async def main():
    tracker = MatchStateTracker()
    state = tracker.update_match_state('wc_2026_001', 'Brazil', 'Serbia', 45, 1, 0, [{'player_id': f'p{i}', 'name': f'Player {i}', 'status': 'active' if i < 11 else 'bench'} for i in range(16)], [{'player_id': f'p{i}', 'name': f'Player {i}', 'status': 'active' if i < 11 else 'bench'} for i in range(16, 32)])
    print(f"State: {state.state}, Subs available: {tracker.get_available_subs(state.match_id, 'home')}")

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
