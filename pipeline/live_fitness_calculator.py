"""Live fitness calculator"""
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PlayerFitness:
    player_id: str
    name: str
    position: str
    baseline_fitness: float
    current_fitness: float
    fatigue_pct: float
    running_load: float
    fatigue_status: str
    substitution_risk: float
    recommendation_ready: bool

class LiveFitnessCalculator:
    def __init__(self, fitness_predictor=None):
        self.predictor = fitness_predictor

    async def calculate_fitness(self, players_baseline, live_metrics, minute):
        fitness_list = []
        
        for player in players_baseline:
            baseline = player.get('baseline_fitness', 75)
            position = player.get('position', 'MID')
            live = next((m for m in live_metrics if m.get('player_id') == player['player_id']), None)
            
            if not live:
                fitness_list.append(PlayerFitness(player_id=player['player_id'], name=player.get('name', ''), position=position, baseline_fitness=baseline, current_fitness=baseline, fatigue_pct=0, running_load=0, fatigue_status='PEAK', substitution_risk=0.05, recommendation_ready=False))
                continue
            
            base_fatigue = (minute / 90) * 100
            running_fatigue = 5 if live.get('running_load_pct', 0) > 110 else 0
            total_fatigue = base_fatigue + running_fatigue
            
            position_multiplier = {'GK': 0.8, 'DEF': 0.95, 'MID': 1.0, 'ATT': 1.1}.get(position, 1.0)
            adjusted_fatigue = total_fatigue * position_multiplier
            current = np.clip(baseline - adjusted_fatigue, 0, 100)
            fatigue_pct = np.clip((adjusted_fatigue / baseline * 100) if baseline > 0 else 0, 0, 100)
            
            if current >= 85: status = 'PEAK'
            elif current >= 75: status = 'HOT'
            elif current >= 65: status = 'FAIR'
            else: status = 'CRITICAL'
            
            risk_map = {'PEAK': 0.05, 'HOT': 0.2, 'FAIR': 0.6, 'CRITICAL': 0.9}
            rec_ready = minute >= 30 and fatigue_pct > 70
            
            fitness_list.append(PlayerFitness(player_id=player['player_id'], name=player.get('name', ''), position=position, baseline_fitness=baseline, current_fitness=current, fatigue_pct=fatigue_pct, running_load=live.get('running_load_pct', 0), fatigue_status=status, substitution_risk=risk_map.get(status, 0.5), recommendation_ready=rec_ready))
        
        logger.debug(f"Calculated fitness for {len(fitness_list)} players")
        return fitness_list

async def main():
    calc = LiveFitnessCalculator()
    players = [{'player_id': 'p1', 'name': 'Player 1', 'position': 'MID', 'baseline_fitness': 85}]
    metrics = [{'player_id': 'p1', 'running_load_pct': 105}]
    fitness = await calc.calculate_fitness(players, metrics, 67)
    print(f"Fitness: {fitness[0].current_fitness:.0f} ({fitness[0].fatigue_status})")

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
