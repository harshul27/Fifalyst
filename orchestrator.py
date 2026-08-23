"""
Premier League 2026/27 - Season Stats Orchestrator

Coordinates recording of every gameweek (1-38): per-player gameplay stats,
a pluggable physical-stats slot, and per-team attacking / midfield / defensive
profiles with derived tactical indicators.

Replaces the retired World Cup live-match path (ESPN + Sofascore/FotMob
scrapers, which were blocked/stubbed and fell back to mock numbers).
Data now comes from the FPL API, with optional FBref tactical enrichment.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from pipeline.fbref_client import FBrefClient
from pipeline.fpl_client import FPLClient
from pipeline.physical_adapter import PhysicalStatsAdapter
from pipeline.season_store import SeasonStore
from pipeline.sub_recommender import MatchState, PlayerState, SubRecommender
from pipeline.team_stats import aggregate_teams

logger = logging.getLogger(__name__)


class SeasonOrchestrator:
    """Record and serve PL 2026/27 gameweek data."""

    def __init__(self, use_fbref: bool = False, store: Optional[SeasonStore] = None):
        self.fpl = FPLClient()
        self.fbref = FBrefClient()
        self.physical = PhysicalStatsAdapter()
        self.store = store or SeasonStore()
        # ponytail: FBref scrapes and can take minutes on a cold cache, so deep
        # tactical enrichment is opt-in. FPL-derived team buckets always apply.
        self.use_fbref = use_fbref
        self._coach = None

    # ---- recording ----
    async def record_gameweek(self, gw: int, final: bool = False) -> Dict[str, Any]:
        """Fetch, assemble and persist one gameweek."""
        rows = await self.fpl.get_gw_player_stats_async(gw)
        if not rows:
            logger.info(f"GW{gw}: no player data yet - nothing recorded")
            return {"gw": gw, "players": 0, "teams": 0, "recorded": False}

        players = pd.DataFrame(rows)
        players = self.physical.enrich(players)  # adds physical cols (NaN by default)

        teams = aggregate_teams(players)
        if self.use_fbref:
            teams = await asyncio.get_event_loop().run_in_executor(
                None, self.fbref.enrich_teams, teams
            )

        self.store.write_gameweek(gw, players, teams, final=final)
        return {"gw": gw, "players": len(players), "teams": len(teams),
                "final": final, "recorded": True}

    async def run_season_update(self, force: bool = False) -> Dict[str, Any]:
        """Record every played gameweek that isn't already final.

        Backfills gameweeks played so far and appends each new one as it is
        played. A gameweek already stored as final is skipped unless forced.
        """
        recordable = self.fpl.recordable_gameweeks()
        done = self.store.recorded_gameweeks()

        todo = [r for r in recordable
                if force or not done.get(r["gw"], {}).get("final", False)]
        skipped = [r["gw"] for r in recordable if r not in todo]

        results = []
        for r in todo:  # sequential: FPL is rate-limited and 38 GWs is cheap
            results.append(await self.record_gameweek(r["gw"], final=r["final"]))

        logger.info(f"✓ season update: recorded {[x['gw'] for x in results]}, skipped {skipped}")
        return {
            "recorded": results,
            "skipped": skipped,
            "total_gameweeks": len(self.fpl.events()),
            "timestamp": datetime.now().isoformat(),
        }

    # ---- live substitution coach ----
    @property
    def coach(self) -> SubRecommender:
        """Lazy: loading the trained model costs ~100ms, so only on demand."""
        if self._coach is None:
            self._coach = SubRecommender()
        return self._coach

    def recommend_subs(self, players, match, bench=None, tracker=None,
                       team_key: str = "home", top_k: int = 3):
        """Rank substitution candidates for a live match state.

        players/bench: list[PlayerState]; match: MatchState.
        tracker: optional SubstitutionTracker enforcing the 5-sub limit and
        excluding players already withdrawn.
        """
        return self.coach.recommend(players, match, bench=bench, tracker=tracker,
                                    team_key=team_key, top_k=top_k)

    def tactical_advice(self, match):
        return self.coach.tactical_advice(match)

    # ---- reading (used by the dashboard) ----
    def gameweek_view(self, gw: int):
        return self.store.read_gameweek(gw)

    def season_view(self, kind: str = "players") -> pd.DataFrame:
        return self.store.read_season(kind)

    def status(self) -> Dict[str, Any]:
        recorded = self.store.recorded_gameweeks()
        return {
            "recorded_gameweeks": sorted(recorded),
            "final_gameweeks": sorted(g for g, m in recorded.items() if m.get("final")),
            "meta": self.store.meta(),
        }


# Singleton (Streamlit re-runs the script on every interaction)
_orchestrator: Optional[SeasonOrchestrator] = None


def get_orchestrator(use_fbref: bool = False) -> SeasonOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SeasonOrchestrator(use_fbref=use_fbref)
    return _orchestrator


async def main():
    logging.basicConfig(level=logging.INFO)
    result = await SeasonOrchestrator().run_season_update()
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
