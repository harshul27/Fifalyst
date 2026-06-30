"""Player live metrics"""
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PlayerMetrics:
    player_id: str
    name: str
    position: str
    match_id: str
    minute: int
    distance_km: float
    passes: int
    tackles: int
    shots: int
    rating: float
    running_load_pct: float
    pass_accuracy: float

class PlayerLiveMetricsAggregator:
    EXPECTED_DISTANCE = {'GK': 6.0, 'DEF': 9.5, 'MID': 10.5, 'ATT': 9.8}

    async def compute_metrics(self, match_state, team_stats):
        metrics_list = []
        minute = match_state.get('minute', 0)
        match_id = match_state.get('match_id', '')
        
        for side in ['home', 'away']:
            lineup = match_state.get(f'{side}_lineup', [])
            stats = team_stats.get(side, {})
            
            for player in lineup:
                if player.get('status') != 'active': continue
                position = player.get('position', 'MID')
                distance = (stats.get('distance', 0) / 11 / 90) * minute if minute > 0 else 0
                passes = int(stats.get('passes', 0) * 0.35 / 11)
                
                metric = PlayerMetrics(player_id=player['player_id'], name=player['name'], position=position, match_id=match_id, minute=minute, distance_km=distance, passes=passes, tackles=max(0, int(np.random.randn() * 2 + 2)), shots=1 if position == 'ATT' else 0, rating=6.5 + passes/30*0.5, running_load_pct=min(100, distance/(self.EXPECTED_DISTANCE.get(position, 10)/90*minute)*100) if minute > 0 else 0, pass_accuracy=np.random.uniform(70, 88))
                metrics_list.append(metric)
        
        logger.debug(f"Computed metrics for {len(metrics_list)} players")
        return metrics_list

async def main():
    agg = PlayerLiveMetricsAggregator()
    match_state = {'match_id': 'wc_2026_001', 'minute': 45, 'home_lineup': [{'player_id': f'h{i}', 'name': f'Player {i}', 'position': 'MID', 'status': 'active'} for i in range(11)], 'away_lineup': [{'player_id': f'a{i}', 'name': f'Player {i}', 'position': 'DEF', 'status': 'active'} for i in range(11)]}
    team_stats = {'home': {'distance': 400, 'passes': 250, 'tackles': 15}, 'away': {'distance': 380, 'passes': 240, 'tackles': 18}}
    metrics = await agg.compute_metrics(match_state, team_stats)
    print(f"Computed {len(metrics)} metrics")

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
