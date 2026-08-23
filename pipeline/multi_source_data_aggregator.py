"""Multi-source data aggregator - Merge ESPN and web scraper data with intelligent fallback"""
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from pipeline.live_metrics_fetcher import LiveMetricsFetcher
from pipeline.live_web_scraper import LiveWebDataAggregator, MatchStateData

logger = logging.getLogger(__name__)


@dataclass
class AggregatedMatchData:
    """Complete match data merged from multiple sources"""
    match_id: str
    home_team: str
    away_team: str
    minute: int
    status: str  # SCHEDULED, LIVE, FINISHED
    home_score: int
    away_score: int
    home_lineup: list
    away_lineup: list
    sources: Dict[str, str]  # {'state': 'espn', 'lineups': 'sofascore', 'metrics': 'fotmob'}
    data_quality: Dict[str, float]  # Confidence scores per data source


class MultiSourceDataAggregator:
    """Intelligently merge data from ESPN, Sofascore, and FotMob"""

    def __init__(self):
        self.espn_fetcher = LiveMetricsFetcher()
        self.web_scraper = LiveWebDataAggregator()
        logger.info("✓ MultiSourceDataAggregator initialized")

    async def fetch_complete_match_data(self, match_id: str, home_team: str, away_team: str) -> Optional[AggregatedMatchData]:
        """
        Fetch complete match data from multiple sources with intelligent merging

        Strategy:
        1. Try ESPN first (most reliable for general data)
        2. Try web scrapers for detailed lineups if ESPN fails
        3. Merge metrics from all available sources
        4. Track data quality and source attribution

        Returns: AggregatedMatchData with merged information
        """
        try:
            # Parallel fetch from all sources
            espn_task = self._fetch_espn_match(match_id)
            web_task = self.web_scraper.fetch_match_state(match_id, home_team, away_team)
            metrics_task = self.web_scraper.fetch_live_player_metrics(match_id, home_team, away_team)

            import asyncio
            espn_data, web_state, web_metrics = await asyncio.gather(
                espn_task,
                web_task,
                metrics_task,
                return_exceptions=True
            )

            # Handle exceptions
            if isinstance(espn_data, Exception):
                espn_data = None
                logger.warning(f"ESPN fetch failed: {espn_data}")
            if isinstance(web_state, Exception):
                web_state = None
                logger.warning(f"Web state fetch failed: {web_state}")
            if isinstance(web_metrics, Exception):
                web_metrics = None
                logger.warning(f"Web metrics fetch failed: {web_metrics}")

            # Merge data with intelligent fallback
            return self._merge_match_data(
                espn_data=espn_data,
                web_state=web_state,
                web_metrics=web_metrics,
                match_id=match_id,
                home_team=home_team,
                away_team=away_team
            )

        except Exception as e:
            logger.error(f"Failed to fetch complete match data: {e}")
            return None

    async def _fetch_espn_match(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Fetch single match data from ESPN"""
        try:
            # Get all matches and find this one
            all_matches = await self.espn_fetcher.fetch_live_matches()
            for match in all_matches:
                if match.get('match_id') == match_id:
                    return match
            logger.debug(f"Match {match_id} not found in ESPN data")
            return None
        except Exception as e:
            logger.error(f"ESPN fetch error: {e}")
            return None

    def _merge_match_data(
        self,
        espn_data: Optional[Dict],
        web_state: Optional[MatchStateData],
        web_metrics: Optional[Dict],
        match_id: str,
        home_team: str,
        away_team: str
    ) -> Optional[AggregatedMatchData]:
        """Intelligently merge data from multiple sources"""

        sources = {}
        data_quality = {}

        # Priority: Use ESPN for state if available, otherwise web sources
        if espn_data:
            minute = espn_data.get('minute', 0)
            status = espn_data.get('status', 'SCHEDULED')
            home_score = espn_data.get('home_score', 0)
            away_score = espn_data.get('away_score', 0)
            home_lineup = espn_data.get('lineups', {}).get('home', [])
            away_lineup = espn_data.get('lineups', {}).get('away', [])

            sources['state'] = 'espn'
            sources['score'] = 'espn'
            sources['minute'] = 'espn'
            data_quality['espn'] = 0.95  # High confidence in ESPN

            logger.info(f"✓ Using ESPN data: {home_team} {home_score}-{away_score} {away_team} ({minute}')")

            # Use web scrapers as backup for lineups if ESPN lineups incomplete
            if not home_lineup or not away_lineup:
                logger.info(f"ESPN lineups incomplete, checking web sources...")
                if web_state:
                    if not home_lineup:
                        home_lineup = web_state.home_lineup
                        sources['home_lineup'] = web_state.source
                    if not away_lineup:
                        away_lineup = web_state.away_lineup
                        sources['away_lineup'] = web_state.source

                    logger.info(f"✓ Got missing lineups from {web_state.source}")
            else:
                sources['lineups'] = 'espn'

        elif web_state:
            # Fallback: Use web scraper data if ESPN unavailable
            minute = web_state.minute
            status = web_state.status
            home_score = web_state.home_score
            away_score = web_state.away_score
            home_lineup = web_state.home_lineup
            away_lineup = web_state.away_lineup

            sources['state'] = web_state.source
            sources['score'] = web_state.source
            sources['minute'] = web_state.source
            sources['lineups'] = web_state.source
            data_quality[web_state.source] = 0.85  # Slightly lower confidence in web scrapers

            logger.warning(
                f"⚠️  Using {web_state.source} (ESPN unavailable): "
                f"{home_team} {home_score}-{away_score} {away_team} ({minute}')"
            )

        else:
            logger.error(f"No data available from any source for {match_id}")
            return None

        # Always supplement with web metrics if available
        if web_metrics and (web_metrics.get('home') or web_metrics.get('away')):
            sources['metrics'] = 'web_aggregated'
            data_quality['web_metrics'] = 0.75

        aggregated = AggregatedMatchData(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            minute=minute,
            status=status,
            home_score=home_score,
            away_score=away_score,
            home_lineup=home_lineup,
            away_lineup=away_lineup,
            sources=sources,
            data_quality=data_quality
        )

        return aggregated

    def get_data_source_report(self, agg_data: AggregatedMatchData) -> str:
        """Generate a human-readable report of data sources"""
        report = f"""
╔═══════════════════════════════════════════════════════════╗
║           MULTI-SOURCE DATA REPORT                        ║
╠═══════════════════════════════════════════════════════════╣
║ Match: {agg_data.home_team} vs {agg_data.away_team}
║ Status: {agg_data.status} | Score: {agg_data.home_score}-{agg_data.away_score} ({agg_data.minute}')
╠═══════════════════════════════════════════════════════════╣
║ DATA SOURCES:
║ • State (minute, score, status): {agg_data.sources.get('state', 'UNKNOWN').upper()}
║ • Lineups (11 players): {agg_data.sources.get('lineups', 'UNKNOWN').upper()}
║ • Metrics (distance, passes): {agg_data.sources.get('metrics', 'NONE').upper()}
╠═══════════════════════════════════════════════════════════╣
║ DATA QUALITY:
"""
        for source, confidence in agg_data.data_quality.items():
            report += f"║ • {source.upper()}: {confidence*100:.0f}%\n"

        report += """╚═══════════════════════════════════════════════════════════╝"""
        return report
