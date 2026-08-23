"""Track substitutions made and dynamically update recommendations"""
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SubstitutionEvent:
    """Record of a substitution made during match"""
    match_id: str
    team: str
    minute: int
    player_off: str
    player_on: str
    player_off_id: str
    player_on_id: str
    reason: str  # WHY this sub was made (fatigue, injury, tactical, etc)
    timestamp: str  # ISO timestamp


@dataclass
class SubstitutionTracker:
    """Track all substitutions per match and update recommendations"""
    match_id: str
    home_team: str
    away_team: str
    subs_made: List[SubstitutionEvent] = field(default_factory=list)
    subs_used: Dict[str, int] = field(default_factory=lambda: {'home': 0, 'away': 0})
    players_on_field: Dict[str, set] = field(default_factory=lambda: {'home': set(), 'away': set()})
    players_off_field: Dict[str, set] = field(default_factory=lambda: {'home': set(), 'away': set()})

    def __post_init__(self):
        logger.info(f"✓ SubstitutionTracker initialized for {self.home_team} vs {self.away_team}")

    def record_substitution(self, team: str, minute: int, player_off_id: str,
                           player_off_name: str, player_on_id: str,
                           player_on_name: str, reason: str = "UNKNOWN"):
        """Record a substitution made during the match"""
        if self.subs_used[team] >= 5:
            logger.warning(f"⚠️  {team} has already used all 5 substitutions!")
            return False

        sub = SubstitutionEvent(
            match_id=self.match_id,
            team=team,
            minute=minute,
            player_off=player_off_name,
            player_off_id=player_off_id,
            player_on=player_on_name,
            player_on_id=player_on_id,
            reason=reason,
            timestamp=datetime.now().isoformat()
        )

        self.subs_made.append(sub)
        self.subs_used[team] += 1

        # Update on-field tracking
        self.players_on_field[team].add(player_on_id)
        self.players_off_field[team].add(player_off_id)

        logger.info(
            f"✓ SUB ({minute}'): {self.home_team if team == 'home' else self.away_team} | "
            f"{player_off_name} OFF → {player_on_name} ON | "
            f"Subs used: {self.subs_used[team]}/5 | Reason: {reason}"
        )

        return True

    def get_available_subs(self, team: str) -> int:
        """Get remaining substitutions for a team"""
        return 5 - self.subs_used[team]

    def is_substituted_off(self, team: str, player_id: str) -> bool:
        """Check if a player has been substituted off"""
        return player_id in self.players_off_field[team]

    def is_on_field(self, team: str, player_id: str) -> bool:
        """Check if player is currently on field"""
        return player_id in self.players_on_field[team]

    def get_subs_history(self, team: Optional[str] = None) -> List[Dict]:
        """Get substitution history as dict list"""
        if team:
            subs = [s for s in self.subs_made if s.team == team]
        else:
            subs = self.subs_made

        return [
            {
                'minute': s.minute,
                'team': s.team,
                'off': s.player_off,
                'on': s.player_on,
                'reason': s.reason
            }
            for s in subs
        ]

    def update_recommendation_validity(self, rec: Dict, team: str) -> tuple[bool, str]:
        """
        Check if a recommendation is still valid after substitutions

        Returns: (is_valid: bool, reason: str)
        """
        off_player_id = rec.get('off_player_id', '')
        on_player_id = rec.get('on_player_id', '')

        # If target player already substituted off, recommendation invalid
        if self.is_substituted_off(team, off_player_id):
            return False, f"{rec.get('off')} already substituted off"

        # If replacement already used in substitution, recommendation invalid
        if self.is_substituted_off(team, on_player_id):
            return False, f"{rec.get('on')} already used in substitution"

        # If no subs remaining, recommendation invalid
        if self.get_available_subs(team) <= 0:
            return False, "No substitutions remaining"

        return True, "Valid"

    def filter_recommendations(self, recommendations: List[Dict], team: str) -> List[Dict]:
        """
        Filter and rerank recommendations based on substitutions already made

        Returns: valid recommendations only
        """
        valid_recs = []

        for rec in recommendations:
            is_valid, reason = self.update_recommendation_validity(rec, team)
            if is_valid:
                valid_recs.append(rec)
            else:
                logger.debug(f"Filtered recommendation: {reason}")

        return valid_recs

    def get_impact_of_subs(self) -> Dict[str, Any]:
        """
        Analyze impact of substitutions made so far

        Returns: {
            'home_subs_impact': [list of sub impacts],
            'away_subs_impact': [list of sub impacts],
            'total_freshness_gained': float
        }
        """
        home_impact = []
        away_impact = []

        for sub in self.subs_made:
            impact = {
                'minute': sub.minute,
                'off': sub.player_off,
                'on': sub.player_on,
                'reason': sub.reason
            }

            if sub.team == 'home':
                home_impact.append(impact)
            else:
                away_impact.append(impact)

        return {
            'home_subs_impact': home_impact,
            'away_subs_impact': away_impact,
            'home_subs_remaining': self.get_available_subs('home'),
            'away_subs_remaining': self.get_available_subs('away')
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current substitution status"""
        return {
            'match_id': self.match_id,
            'subs_made': [
                {
                    'minute': s.minute,
                    'team': s.team,
                    'off': s.player_off,
                    'on': s.player_on,
                    'reason': s.reason
                }
                for s in self.subs_made
            ],
            'subs_used': self.subs_used.copy(),
            'subs_remaining': {
                'home': self.get_available_subs('home'),
                'away': self.get_available_subs('away')
            }
        }

    def reset(self):
        """Reset tracker for next match"""
        self.subs_made.clear()
        self.subs_used = {'home': 0, 'away': 0}
        self.players_on_field.clear()
        self.players_off_field.clear()
        logger.info(f"✓ SubstitutionTracker reset for {self.home_team} vs {self.away_team}")
