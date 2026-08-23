"""Online model training - Learn from live match data during first 30 minutes"""
import logging
from typing import Dict, List, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LiveObservation:
    """Observation from live match during first 30 minutes"""
    player_id: str
    minute: int
    distance_km: float
    passes: int
    tackles: int
    pass_accuracy: float
    running_load_pct: float
    expected_fatigue_model: float  # What baseline model predicted
    actual_performance: float  # Observed real value


class OnlineModelTrainer:
    """Train fitness model on live data during first 30 minutes"""

    def __init__(self):
        self.observations: List[LiveObservation] = []
        self.weight_adjustments = {
            'distance_multiplier': 1.0,      # Adjust how distance affects fatigue
            'intensity_factor': 1.0,          # Adjust for match intensity
            'position_variance': {            # Per-position adjustments
                'GK': 1.0,
                'DEF': 1.0,
                'MID': 1.0,
                'ATT': 1.0
            }
        }
        logger.info("✓ OnlineModelTrainer initialized (learning disabled until min 0+)")

    def record_observation(self, observation: LiveObservation):
        """Record a live player observation during first 30 minutes"""
        if len(self.observations) >= 10000:  # Prevent memory bloat
            self.observations = self.observations[-5000:]  # Keep last 5000

        self.observations.append(observation)
        logger.debug(f"Recorded observation: {observation.player_id} @ {observation.minute}'")

    def calculate_error(self, predicted_fatigue: float, actual_performance: float) -> float:
        """
        Calculate error: how wrong was the predicted fatigue vs actual performance?

        Higher actual_performance with high predicted_fatigue = model underpredicted
        Lower actual_performance with low predicted_fatigue = model overpredicted
        """
        # Normalize: performance is [0-100], fatigue is [0-100]
        expected_performance = 100 - predicted_fatigue
        error = abs(expected_performance - actual_performance)
        return error

    def get_match_intensity(self, observations: List[LiveObservation]) -> float:
        """
        Estimate match intensity from observations

        Higher intensity = more distance covered, more passes, more tackles
        Returns factor [0.7, 1.3] to apply to baseline fatigue model
        """
        if not observations:
            return 1.0

        avg_distance = sum(o.distance_km for o in observations) / len(observations)
        avg_passes = sum(o.passes for o in observations) / len(observations)

        # Typical match: ~9km distance, ~40 passes per player
        distance_factor = avg_distance / 9.0
        pass_factor = avg_passes / 40.0

        intensity = (distance_factor * 0.6 + pass_factor * 0.4)
        # Cap between 0.7 and 1.3
        return max(0.7, min(1.3, intensity))

    def update_weights(self):
        """
        Update model weights based on observed data (minute 1-30)

        Called every 5 minutes during first 30 minutes
        """
        if len(self.observations) < 50:
            logger.debug(f"Not enough observations yet ({len(self.observations)}/50)")
            return

        # Group observations by minute for batch analysis
        by_minute = {}
        for obs in self.observations:
            if obs.minute not in by_minute:
                by_minute[obs.minute] = []
            by_minute[obs.minute].append(obs)

        # Calculate average error per minute
        total_error = 0.0
        error_count = 0

        for minute, obs_list in by_minute.items():
            for obs in obs_list:
                error = self.calculate_error(obs.expected_fatigue_model, obs.actual_performance)
                total_error += error
                error_count += 1

        avg_error = total_error / error_count if error_count > 0 else 0

        # Adjust distance multiplier based on error
        # If error is high, real matches are more intense than model predicts
        if avg_error > 15:
            self.weight_adjustments['distance_multiplier'] *= 1.05  # Model underestimated
            logger.info(f"↑ Distance multiplier increased to {self.weight_adjustments['distance_multiplier']:.2f}")
        elif avg_error < 5:
            self.weight_adjustments['distance_multiplier'] *= 0.95  # Model overestimated
            logger.info(f"↓ Distance multiplier decreased to {self.weight_adjustments['distance_multiplier']:.2f}")

        # Estimate match intensity and adjust
        intensity = self.get_match_intensity(self.observations)
        self.weight_adjustments['intensity_factor'] = intensity
        logger.info(f"Match intensity factor: {intensity:.2f}x (error: {avg_error:.1f} pts)")

        # Adjust per-position variances
        self._adjust_position_weights()

    def _adjust_position_weights(self):
        """Adjust weights per position based on observed fatigue patterns"""
        if not self.observations:
            return

        by_position = {}
        for obs in self.observations:
            # Position not directly in observation, would need to map player_id → position
            # For now, skip position-specific adjustment
            pass

    def get_adjusted_fatigue(self, base_fatigue: float, position: str, distance_km: float) -> float:
        """
        Apply learned adjustments to predicted fatigue

        base_fatigue: fatigue from minute-based model
        position: player position (GK, DEF, MID, ATT)
        distance_km: observed running distance

        Returns: adjusted fatigue [0, 100]
        """
        # Apply distance multiplier
        distance_penalty = (distance_km / 12.0) * 30  # 12km typical = 30% fatigue
        distance_penalty *= self.weight_adjustments['distance_multiplier']

        # Apply intensity factor
        adjusted = base_fatigue * self.weight_adjustments['intensity_factor']
        adjusted += distance_penalty

        # Apply position variance
        position_factor = self.weight_adjustments['position_variance'].get(position, 1.0)
        adjusted *= position_factor

        return min(adjusted, 100)  # Cap at 100%

    def get_model_confidence(self) -> float:
        """
        Return confidence in learned adjustments [0, 1]

        0.0 = no training yet (use baseline)
        1.0 = fully trained (min 30 reached)
        """
        # At minute 30, we've had ~6 observations per player
        # Confidence = 0.0 to 0.95 based on number of observations
        if len(self.observations) < 50:
            return 0.0
        if len(self.observations) > 500:
            return 0.95  # Cap at 0.95 (always some uncertainty)

        return min(0.95, len(self.observations) / 1000)

    def reset_for_next_match(self):
        """Clear observations after match ends (or minute 30+ reached)"""
        self.observations.clear()
        self.weight_adjustments = {
            'distance_multiplier': 1.0,
            'intensity_factor': 1.0,
            'position_variance': {
                'GK': 1.0,
                'DEF': 1.0,
                'MID': 1.0,
                'ATT': 1.0
            }
        }
        logger.info("✓ OnlineModelTrainer reset for next match")

    def get_status(self) -> Dict[str, Any]:
        """Return current training status"""
        return {
            'observations_collected': len(self.observations),
            'confidence': self.get_model_confidence(),
            'distance_multiplier': self.weight_adjustments['distance_multiplier'],
            'intensity_factor': self.weight_adjustments['intensity_factor'],
            'position_variance': self.weight_adjustments['position_variance']
        }
