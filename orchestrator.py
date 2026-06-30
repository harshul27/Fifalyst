"""
Master Orchestrator for FIFA World Cup Multi-Agent System

Responsibilities:
- Coordinate all 5 specialized agents
- Manage 5-minute processing cycle
- Emit events to Redis Pub/Sub
- Track agent health and metrics
- Execute agents in parallel for 8 concurrent matches
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import redis

from agents.data_collection_agent import DataCollectionAgent
from agents.fitness_model_agent import FitnessModelAgent
from agents.live_match_agent import LiveMatchAgent
from agents.recommendation_engine_agent import RecommendationEngineAgent
from agents.feedback_agent import FeedbackAgent

logger = logging.getLogger(__name__)


class MasterOrchestrator:
    """
    Master Orchestrator - Coordinates all agents and manages the processing pipeline
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        cycle_interval: int = 300,  # 5 minutes
        max_concurrent_matches: int = 8,
    ):
        """
        Initialize orchestrator

        Args:
            redis_host: Redis connection host
            redis_port: Redis connection port
            cycle_interval: Seconds between processing cycles
            max_concurrent_matches: Max matches to process in parallel
        """
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
        )

        self.cycle_interval = cycle_interval
        self.max_concurrent_matches = max_concurrent_matches

        # Initialize agents
        self.data_collection = DataCollectionAgent(redis_host, redis_port)
        self.fitness_model = FitnessModelAgent(redis_host, redis_port)
        self.live_match = LiveMatchAgent(redis_host, redis_port)
        self.recommendation_engine = RecommendationEngineAgent(redis_host, redis_port)
        self.feedback = FeedbackAgent(redis_host, redis_port)

        # Subscriptions for event listening
        self.pubsub = self.redis_client.pubsub()
        self.is_running = False
        self.cycle_count = 0
        self.start_time = None

        logger.info("Initialized MasterOrchestrator with 5 agents")

    async def run(self) -> None:
        """Main orchestrator loop - runs continuously"""
        self.is_running = True
        self.start_time = datetime.utcnow()

        try:
            logger.info("Orchestrator started")

            while self.is_running:
                cycle_start = datetime.utcnow()
                self.cycle_count += 1

                try:
                    await self._process_cycle()

                except Exception as e:
                    logger.error(f"Cycle error: {e}")

                # Wait until next cycle
                elapsed = (datetime.utcnow() - cycle_start).total_seconds()
                wait_time = max(0, self.cycle_interval - elapsed)

                if wait_time > 0:
                    logger.debug(f"Waiting {wait_time:.1f}s until next cycle")
                    await asyncio.sleep(wait_time)

        except KeyboardInterrupt:
            logger.info("Orchestrator interrupted")
        finally:
            await self.shutdown()

    async def _process_cycle(self) -> None:
        """
        Execute one complete processing cycle

        Sequence:
        1. Data Collection Agent fetches ESPN/Sofascore/Transfermarkt data
        2. Live Match Agent updates match state
        3. Fitness Model Agent computes player fitness
        4. Recommendation Engine Agent generates substitution recommendations
        5. Feedback Agent tracks outcomes
        """
        logger.info(f"=== Cycle {self.cycle_count} started ===")

        try:
            # Step 1: Data Collection
            logger.debug("Step 1: Data Collection")
            collection_result = await self.data_collection.run()
            matches_collected = collection_result.get("matches_processed", 0)

            if matches_collected == 0:
                logger.info("No live matches, waiting for next cycle")
                return

            # Get match data from collection result
            matches_data = collection_result.get("matches", [])

            # Step 2: Fitness Model (for each match in parallel)
            logger.debug("Step 2: Fitness Model Computation")
            fitness_tasks = [
                self.fitness_model.run(
                    match.get("match_id"),
                    match,
                )
                for match in matches_data[:self.max_concurrent_matches]
            ]
            fitness_results = await asyncio.gather(*fitness_tasks, return_exceptions=True)

            # Step 3: Live Match Agent (for each match in parallel)
            logger.debug("Step 3: Live Match State Tracking")
            live_match_tasks = [
                self.live_match.run(
                    match.get("match_id"),
                    match,
                )
                for match in matches_data[:self.max_concurrent_matches]
            ]
            live_match_results = await asyncio.gather(*live_match_tasks, return_exceptions=True)

            # Step 4: Recommendation Engine Agent (for each match in parallel)
            logger.debug("Step 4: Substitution Recommendations")
            recommendation_tasks = [
                self.recommendation_engine.run(
                    match.get("match_id"),
                    match,
                )
                for match in matches_data[:self.max_concurrent_matches]
            ]
            recommendation_results = await asyncio.gather(*recommendation_tasks, return_exceptions=True)

            # Step 5: Feedback Agent (post-match analysis, periodic)
            logger.debug("Step 5: Feedback & Learning")
            feedback_result = await self.feedback.run()

            # Emit cycle complete event
            await self._emit_cycle_complete(
                self.cycle_count,
                matches_collected,
                fitness_results,
                live_match_results,
                recommendation_results,
            )

            logger.info(f"=== Cycle {self.cycle_count} complete ===")

        except Exception as e:
            logger.error(f"Cycle {self.cycle_count} error: {e}")

    async def _emit_cycle_complete(
        self,
        cycle_num: int,
        matches_processed: int,
        fitness_results: List[Any],
        live_match_results: List[Any],
        recommendation_results: List[Any],
    ) -> None:
        """Emit event when cycle completes"""
        try:
            payload = {
                "cycle": cycle_num,
                "timestamp": datetime.utcnow().isoformat(),
                "matches_processed": matches_processed,
                "agents_complete": {
                    "data_collection": matches_processed,
                    "fitness_model": len([r for r in fitness_results if not isinstance(r, Exception)]),
                    "live_match": len([r for r in live_match_results if not isinstance(r, Exception)]),
                    "recommendation_engine": len([r for r in recommendation_results if not isinstance(r, Exception)]),
                    "feedback": "pending",
                },
                "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
            }

            channel = "fifa:orchestrator:cycle_complete"
            message = json.dumps(payload)
            self.redis_client.publish(channel, message)

            logger.debug(f"Emitted cycle complete event")

        except Exception as e:
            logger.error(f"Cycle event emission error: {e}")

    async def shutdown(self) -> None:
        """Graceful shutdown"""
        logger.info("Orchestrator shutting down...")
        self.is_running = False

        # Close subscriptions
        if self.pubsub:
            self.pubsub.close()

        # Close Redis connection
        if self.redis_client:
            self.redis_client.close()

        logger.info(f"Orchestrator shut down. Completed {self.cycle_count} cycles.")

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status"""
        return {
            "is_running": self.is_running,
            "cycle_count": self.cycle_count,
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds()
            if self.start_time else 0,
            "agents": {
                "data_collection": "active",
                "fitness_model": "active",
                "live_match": "active",
                "recommendation_engine": "active",
                "feedback": "active",
            },
        }


async def main():
    """Main entry point"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    orchestrator = MasterOrchestrator()

    try:
        await orchestrator.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
