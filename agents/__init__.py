"""
FIFA World Cup 2026 Multi-Agent System - Agents Package

This package contains all specialized agents for the distributed system:
- DataCollectionAgent: Fetches live data from ESPN, Sofascore, TransferMarkt
- FitnessModelAgent: Computes player fitness scores using trained models
- LiveMatchAgent: Tracks match state, lineups, substitutions
- RecommendationEngineAgent: Generates substitution recommendations
- FeedbackAgent: Tracks recommendation accuracy and learns from outcomes
"""

from .base_agent import BaseAgent, AgentMetrics
from .data_collection_agent import DataCollectionAgent
from .fitness_model_agent import FitnessModelAgent
from .live_match_agent import LiveMatchAgent
from .recommendation_engine_agent import RecommendationEngineAgent
from .feedback_agent import FeedbackAgent

__all__ = [
    "BaseAgent",
    "AgentMetrics",
    "DataCollectionAgent",
    "FitnessModelAgent",
    "LiveMatchAgent",
    "RecommendationEngineAgent",
    "FeedbackAgent",
]
