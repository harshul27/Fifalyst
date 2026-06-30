#!/usr/bin/env python3
"""
Verify agent system setup and connectivity.
Checks dependencies, Redis, and agent instantiation without running.
"""

import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check_dependencies():
    """Verify all required dependencies are installed."""
    logger.info("Checking Python dependencies...")

    dependencies = {
        "redis": "Redis client",
        "requests": "HTTP library for ESPN/Sofascore APIs",
        "langchain": "LangChain framework for agents",
        "langchain_anthropic": "Claude API integration",
        "pandas": "Data manipulation",
        "numpy": "Numerical computing",
        "duckdb": "Database",
        "pydantic": "Data validation",
    }

    missing = []
    for module, description in dependencies.items():
        try:
            __import__(module)
            logger.info(f"✓ {module:20} - {description}")
        except ImportError:
            logger.error(f"✗ {module:20} - {description}")
            missing.append(module)

    if missing:
        logger.error(f"\nMissing {len(missing)} dependencies. Install with:")
        logger.error(f"  pip install {' '.join(missing)}")
        return False

    logger.info("✓ All dependencies installed")
    return True


def check_redis():
    """Verify Redis connectivity."""
    logger.info("\nChecking Redis connection...")

    try:
        import redis
        client = redis.Redis(host="localhost", port=6379, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        info = client.info("server")
        logger.info(f"✓ Redis connected")
        logger.info(f"  Version: {info.get('redis_version')}")
        logger.info(f"  Uptime: {info.get('uptime_in_seconds')} seconds")
        client.close()
        return True
    except Exception as e:
        logger.error(f"✗ Redis connection failed: {e}")
        logger.error("  Make sure Redis is running: redis-server")
        return False


def check_orchestrator_imports():
    """Verify orchestrator and agent imports work."""
    logger.info("\nChecking orchestrator/agent imports...")

    try:
        from orchestrator import MasterOrchestrator
        logger.info("✓ MasterOrchestrator imported")
    except ImportError as e:
        logger.error(f"✗ Failed to import MasterOrchestrator: {e}")
        return False

    try:
        from agents.base_agent import BaseAgent
        from agents.data_collection_agent import DataCollectionAgent
        from agents.fitness_model_agent import FitnessModelAgent
        from agents.live_match_agent import LiveMatchAgent
        from agents.recommendation_engine_agent import RecommendationEngineAgent
        from agents.feedback_agent import FeedbackAgent

        logger.info("✓ DataCollectionAgent imported")
        logger.info("✓ FitnessModelAgent imported")
        logger.info("✓ LiveMatchAgent imported")
        logger.info("✓ RecommendationEngineAgent imported")
        logger.info("✓ FeedbackAgent imported")
        return True
    except ImportError as e:
        logger.error(f"✗ Failed to import agents: {e}")
        return False


def check_agent_instantiation():
    """Try to instantiate agents (without running)."""
    logger.info("\nChecking agent instantiation...")

    try:
        from orchestrator import MasterOrchestrator
        orchestrator = MasterOrchestrator(
            redis_host="localhost",
            redis_port=6379,
            cycle_interval=300,
            max_concurrent_matches=8,
        )
        logger.info("✓ MasterOrchestrator instantiated")
        logger.info(f"  Agents: data_collection, fitness_model, live_match, recommendation_engine, feedback")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to instantiate orchestrator: {e}")
        return False


def check_espn_connectivity():
    """Verify ESPN API is reachable."""
    logger.info("\nChecking ESPN API connectivity...")

    try:
        import requests
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            logger.info("✓ ESPN API reachable")
            return True
        else:
            logger.error(f"✗ ESPN API returned {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"✗ ESPN API connection failed: {e}")
        return False


def check_sofascore_connectivity():
    """Verify Sofascore API is reachable."""
    logger.info("\nChecking Sofascore API connectivity...")

    try:
        import requests
        url = "https://api.sofascore.com/api/v1/unique-tournaments/17/seasons"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            logger.info("✓ Sofascore API reachable")
            return True
        else:
            logger.error(f"✗ Sofascore API returned {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"✗ Sofascore API connection failed: {e}")
        return False


def main():
    """Run all checks."""
    logger.info("=" * 60)
    logger.info("FIFA Shadow Coach - Agent System Verification")
    logger.info("=" * 60)

    checks = [
        ("Dependencies", check_dependencies),
        ("Redis", check_redis),
        ("Orchestrator Imports", check_orchestrator_imports),
        ("Agent Instantiation", check_agent_instantiation),
        ("ESPN API", check_espn_connectivity),
        ("Sofascore API", check_sofascore_connectivity),
    ]

    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            logger.error(f"✗ {name} check failed: {e}")
            results[name] = False

    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "✓" if result else "✗"
        logger.info(f"{status} {name}")

    logger.info(f"\nPassed: {passed}/{total}")

    if passed == total:
        logger.info("\n✓ All checks passed! Agent system is ready.")
        logger.info("\nTo start the system:")
        logger.info("  1. python pipeline.py orchestrator  # Start orchestrator in terminal 1")
        logger.info("  2. streamlit run app.py              # Start app in terminal 2")
        return 0
    else:
        logger.error(f"\n✗ {total - passed} check(s) failed. Fix the issues above and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
