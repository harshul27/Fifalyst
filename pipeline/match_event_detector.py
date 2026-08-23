"""Detect match state transitions and trigger real-time updates"""
import logging
from typing import Dict, Any, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class MatchEventType(Enum):
    """Types of match events that trigger actions"""
    MATCH_START = "MATCH_START"           # Minute changes from 0 → 1
    FIRST_HALF_30MIN = "FIRST_HALF_30MIN" # Minute 30 reached (recommendations ready)
    HALFTIME = "HALFTIME"                  # Minute 45
    SECOND_HALF_START = "SECOND_HALF_START" # Minute 46
    FINAL_WHISTLE = "FINAL_WHISTLE"       # Minute 90+
    GOAL_SCORED = "GOAL_SCORED"           # Score change
    SUBSTITUTION = "SUBSTITUTION"          # Player swap
    INJURY_ALERT = "INJURY_ALERT"         # Possible injury detected


class MatchEventDetector:
    """Detect significant match events and trigger appropriate handlers"""

    def __init__(self, match_id: str, home_team: str, away_team: str):
        self.match_id = match_id
        self.home_team = home_team
        self.away_team = away_team

        # Tracking state for change detection
        self.previous_state = {
            'minute': 0,
            'score': {'home': 0, 'away': 0},
            'lineups': {'home': [], 'away': []},
            'status': 'SCHEDULED'
        }

        self.current_state = self.previous_state.copy()

        # Event handlers
        self.event_handlers: Dict[MatchEventType, list[Callable]] = {
            event_type: [] for event_type in MatchEventType
        }

        # Flags
        self.match_started = False
        self.recommendations_ready = False
        self.match_finished = False

        logger.info(f"✓ MatchEventDetector initialized for {home_team} vs {away_team}")

    def register_handler(self, event_type: MatchEventType, handler: Callable):
        """Register a handler function for an event type"""
        self.event_handlers[event_type].append(handler)
        logger.debug(f"Registered handler for {event_type.value}: {handler.__name__}")

    def detect_events(self, match_data: Dict[str, Any]) -> list[tuple[MatchEventType, Dict]]:
        """
        Detect all events by comparing current vs previous state

        Returns: list of (event_type, event_data) tuples
        """
        events = []

        # Store current state
        self.previous_state = self.current_state.copy()
        self.current_state = {
            'minute': match_data.get('minute', 0),
            'score': {
                'home': match_data.get('home_score', 0),
                'away': match_data.get('away_score', 0)
            },
            'lineups': {
                'home': match_data.get('home_lineup', []),
                'away': match_data.get('away_lineup', [])
            },
            'status': match_data.get('status', 'SCHEDULED')
        }

        # Detect MATCH_START (minute 0 → 1+)
        if self.previous_state['minute'] == 0 and self.current_state['minute'] > 0:
            events.append((MatchEventType.MATCH_START, {
                'match_id': self.match_id,
                'minute': self.current_state['minute'],
                'home_team': self.home_team,
                'away_team': self.away_team
            }))
            self.match_started = True
            logger.info(f"🔔 MATCH START: {self.home_team} vs {self.away_team}")

        # Detect FIRST_HALF_30MIN (min 0-29 → 30+)
        if (self.previous_state['minute'] < 30 and self.current_state['minute'] >= 30
                and not self.recommendations_ready):
            events.append((MatchEventType.FIRST_HALF_30MIN, {
                'match_id': self.match_id,
                'minute': self.current_state['minute'],
                'status': 'RECOMMENDATIONS_READY'
            }))
            self.recommendations_ready = True
            logger.info(f"🔔 30' MARK REACHED: Substitution recommendations now active")

        # Detect HALFTIME (min < 45 → 45)
        if self.previous_state['minute'] < 45 and self.current_state['minute'] == 45:
            events.append((MatchEventType.HALFTIME, {
                'match_id': self.match_id,
                'minute': 45,
                'score': f"{self.current_state['score']['home']}-{self.current_state['score']['away']}"
            }))
            logger.info(f"🔔 HALFTIME")

        # Detect SECOND_HALF_START (min 45 → 46+)
        if self.previous_state['minute'] == 45 and self.current_state['minute'] > 45:
            events.append((MatchEventType.SECOND_HALF_START, {
                'match_id': self.match_id,
                'minute': self.current_state['minute']
            }))
            logger.info(f"🔔 SECOND HALF STARTS")

        # Detect FINAL_WHISTLE (min < 90 → 90+)
        if (self.previous_state['minute'] < 90 and self.current_state['minute'] >= 90
                and not self.match_finished):
            events.append((MatchEventType.FINAL_WHISTLE, {
                'match_id': self.match_id,
                'minute': self.current_state['minute'],
                'final_score': f"{self.current_state['score']['home']}-{self.current_state['score']['away']}"
            }))
            self.match_finished = True
            logger.info(f"🔔 FINAL WHISTLE")

        # Detect GOAL_SCORED (score change)
        if self.current_state['score'] != self.previous_state['score']:
            events.append((MatchEventType.GOAL_SCORED, {
                'match_id': self.match_id,
                'minute': self.current_state['minute'],
                'home_score': self.current_state['score']['home'],
                'away_score': self.current_state['score']['away'],
                'score_change': {
                    'home': self.current_state['score']['home'] - self.previous_state['score']['home'],
                    'away': self.current_state['score']['away'] - self.previous_state['score']['away']
                }
            }))
            logger.info(
                f"🔔 GOAL! Score: "
                f"{self.current_state['score']['home']}-{self.current_state['score']['away']}"
            )

        # Detect SUBSTITUTION (lineup changes)
        subs = self._detect_lineup_changes()
        for sub in subs:
            events.append((MatchEventType.SUBSTITUTION, sub))
            logger.info(
                f"🔔 SUB ({sub['minute']}'): {sub['team']} | "
                f"{sub['player_off']} OFF → {sub['player_on']} ON"
            )

        return events

    def _detect_lineup_changes(self) -> list[Dict]:
        """Detect substitutions by comparing lineups"""
        subs = []

        for team_key in ['home', 'away']:
            prev_lineup = {p.get('player_id'): p for p in self.previous_state['lineups'][team_key]}
            curr_lineup = {p.get('player_id'): p for p in self.current_state['lineups'][team_key]}

            # Find players that were on field and are now gone (sub off)
            for player_id, player_data in prev_lineup.items():
                if player_id not in curr_lineup and player_data.get('status') == 'active':
                    # Find who replaced this player
                    for new_id, new_data in curr_lineup.items():
                        if new_id not in prev_lineup and new_data.get('status') == 'active':
                            subs.append({
                                'match_id': self.match_id,
                                'team': 'home' if team_key == 'home' else 'away',
                                'minute': self.current_state['minute'],
                                'player_off_id': player_id,
                                'player_off': player_data.get('name', 'Unknown'),
                                'player_on_id': new_id,
                                'player_on': new_data.get('name', 'Unknown')
                            })
                            break

        return subs

    def emit_event(self, event_type: MatchEventType, event_data: Dict):
        """Emit an event and call all registered handlers"""
        handlers = self.event_handlers.get(event_type, [])

        for handler in handlers:
            try:
                handler(event_data)
            except Exception as e:
                logger.error(f"Error in {event_type.value} handler: {e}")

    def process_match_update(self, match_data: Dict[str, Any]):
        """
        Main entry point: process match data and emit appropriate events

        Call this every time match data updates
        """
        events = self.detect_events(match_data)

        for event_type, event_data in events:
            self.emit_event(event_type, event_data)

    def should_refresh_immediately(self) -> bool:
        """
        Determine if dashboard should refresh immediately or wait 5 min

        Refresh immediately if: match just started, 30' reached, goal scored, sub made
        """
        if not self.match_started:
            return False  # Wait for match to start

        if self.match_finished:
            return False  # No refresh after final whistle

        # Refresh immediately in first 5 minutes (lots of action)
        if self.current_state['minute'] <= 5:
            return True

        # Refresh immediately around 30' (recommendations becoming active)
        if 28 <= self.current_state['minute'] <= 32:
            return True

        # Refresh immediately around halftime
        if 43 <= self.current_state['minute'] <= 47:
            return True

        # Refresh immediately at goal or substitution
        # (last event would be recent, check timestamps if available)

        return False

    def get_poll_interval(self) -> int:
        """
        Get recommended polling interval in seconds

        SCHEDULED: 60 seconds
        LIVE: 30 seconds (around key moments) or 300 seconds (normal play)
        FINISHED: no polling needed
        """
        if not self.match_started:
            return 60  # Not started, poll every minute

        if self.match_finished:
            return 999999  # Match over, don't poll

        if self.should_refresh_immediately():
            return 30  # Key moments, poll every 30s

        return 300  # Normal play, poll every 5 minutes

    def get_status(self) -> Dict[str, Any]:
        """Get current event detection status"""
        return {
            'match_id': self.match_id,
            'home_team': self.home_team,
            'away_team': self.away_team,
            'match_started': self.match_started,
            'recommendations_ready': self.recommendations_ready,
            'match_finished': self.match_finished,
            'current_minute': self.current_state['minute'],
            'current_score': self.current_state['score'],
            'poll_interval': self.get_poll_interval()
        }
