"""Phase 5 orchestrator"""
import asyncio
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class LiveMatchOrchestrator:
    def __init__(self):
        self.fetcher = None
        self.state_tracker = None
        self.metrics_agg = None
        self.fitness_calc = None

    async def initialize(self, fetcher, state_tracker, metrics_agg, fitness_calc):
        self.fetcher = fetcher
        self.state_tracker = state_tracker
        self.metrics_agg = metrics_agg
        self.fitness_calc = fitness_calc
        logger.info("Orchestrator initialized")

    async def process_cycle(self):
        cycle_start = time.time()
        logger.info("\n" + "=" * 70)
        logger.info(f"LIVE MATCH CYCLE - {datetime.now().strftime('%H:%M:%S')}")
        logger.info("=" * 70)

        results = {'timestamp': datetime.now().isoformat(), 'matches': {}, 'total_time_ms': 0}

        try:
            # Step 1: Fetch matches
            step_start = time.time()
            matches = await self.fetcher.fetch_live_matches()
            step_time = (time.time() - step_start) * 1000
            logger.info(f"\n[T+0ms] Data Collection: Found {len(matches)} live matches ({step_time:.0f}ms)")

            # Step 2: Process each match
            for match in matches:
                match_id = match['match_id']
                details = await self.fetcher.fetch_match_details(match_id)
                state = self.state_tracker.update_match_state(match_id, match['home_team'], match['away_team'], match.get('minute', 0), match.get('home_score', 0), match.get('away_score', 0), details.get('lineups', {}).get('home', []), details.get('lineups', {}).get('away', []))
                
                all_players = state.home_lineup + state.away_lineup
                baseline_players = [{'player_id': p['player_id'], 'name': p['name'], 'position': p.get('position', 'MID'), 'baseline_fitness': 75 + (hash(p['player_id']) % 20 - 10)} for p in all_players]
                
                live_metrics = await self.metrics_agg.compute_metrics({'match_id': match_id, 'minute': state.minute, 'home_lineup': state.home_lineup, 'away_lineup': state.away_lineup}, details.get('live_stats', {}))
                metrics_dicts = [{'player_id': m.player_id, 'name': m.name, 'position': m.position, 'running_load_pct': m.running_load_pct, 'tackles': m.tackles, 'passes': m.passes, 'pass_accuracy': m.pass_accuracy} for m in live_metrics]
                fitness_scores = await self.fitness_calc.calculate_fitness(baseline_players, metrics_dicts, state.minute)
                
                tired = sorted([f for f in fitness_scores if f.fatigue_pct > 70], key=lambda x: x.fatigue_pct, reverse=True)[:3]
                recommendations = [{'off_player': p.name, 'position': p.position, 'fitness': p.current_fitness, 'fatigue': p.fatigue_pct, 'status': p.fatigue_status, 'substitution_risk': p.substitution_risk, 'confidence': 0.75 if p.substitution_risk > 0.7 else 0.5} for p in tired]
                
                results['matches'][match_id] = {'state': {'home': f"{state.home_team} {state.home_score}", 'away': f"{state.away_score} {state.away_team}", 'minute': state.minute, 'status': state.state}, 'recommendations': recommendations[:3]}
        
        except Exception as e:
            logger.error(f"Cycle failed: {e}")
            results['error'] = str(e)

        total_time = (time.time() - cycle_start) * 1000
        results['total_time_ms'] = total_time
        status_check = "PASS" if total_time < 500 else "SLOW"
        logger.info(f"\n{'=' * 70}\nCycle Complete: {total_time:.0f}ms total\nTarget: <500ms {status_check}\n{'=' * 70}")
        return results

async def main():
    from live_metrics_fetcher import LiveMetricsFetcher
    from match_state_tracker import MatchStateTracker
    from player_live_metrics import PlayerLiveMetricsAggregator
    from live_fitness_calculator import LiveFitnessCalculator

    fetcher = LiveMetricsFetcher()
    state_tracker = MatchStateTracker()
    metrics_agg = PlayerLiveMetricsAggregator()
    fitness_calc = LiveFitnessCalculator()

    orchestrator = LiveMatchOrchestrator()
    await orchestrator.initialize(fetcher, state_tracker, metrics_agg, fitness_calc)
    results = await orchestrator.process_cycle()
    print(f"\nCycle Complete! Total Time: {results['total_time_ms']:.0f}ms")
    await fetcher.close()

if __name__ == "__main__":
    asyncio.run(main())
