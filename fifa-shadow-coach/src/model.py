"""
FIFA Shadow Coach - Analytical Model Module
Vectorized player energy calculation and Monte Carlo match simulation.
"""

import numpy as np
from typing import List, Dict, Tuple


# Constants
EXPONENTIAL_DECAY_LAMBDA = np.log(2) / 10.0  # ~0.0693: 10-day half-life
BASE_PLAYER_ENERGY = 100.0
MIN_PHYSIOLOGICAL_ENERGY = 15.0
BASE_GOAL_INTENSITY_LAMBDA = 2.5  # Expected goals per team per 90 min


def calculate_player_energy(match_logs: List[Dict]) -> float:
    """
    Compute Player Energy Score (PES) using exponential decay fatigue model.

    Args:
        match_logs: List of dicts with keys:
            - 'minutes_played' (float): Minutes in that match
            - 'days_ago' (float): Days since that match (>=0)
            - 'match_intensity' (float): Intensity scalar [0, 1]

    Returns:
        float: PES bounded [15.0, 100.0]

    Formula:
        PES = max(15.0, 100 - sum(strain_i * exp(-lambda * days_ago_i)))
        where strain_i = minutes_played_i * match_intensity_i / 90
    """
    if not match_logs:
        return BASE_PLAYER_ENERGY

    try:
        # Vectorize match logs
        minutes = np.array([log.get('minutes_played', 0.0) for log in match_logs])
        days_ago = np.array([log.get('days_ago', 0.0) for log in match_logs])
        intensity = np.array([log.get('match_intensity', 0.5) for log in match_logs])

        # Clamp intensity to [0, 1] and compute strain per match
        intensity = np.clip(intensity, 0.0, 1.0)
        strain = (minutes * intensity) / 90.0  # Normalize to 90-min match

        # Apply exponential decay: strain decays as time passes
        decay_factors = np.exp(-EXPONENTIAL_DECAY_LAMBDA * days_ago)
        cumulative_strain = np.sum(strain * decay_factors)

        # Compute PES with floor
        pes = BASE_PLAYER_ENERGY - cumulative_strain
        pes = np.clip(pes, MIN_PHYSIOLOGICAL_ENERGY, BASE_PLAYER_ENERGY)

        return float(pes)

    except (KeyError, TypeError, ValueError) as e:
        # Fallback: return baseline if malformed input
        return BASE_PLAYER_ENERGY


def simulate_match_state(
    home_pes: float,
    away_pes: float,
    current_minute: int,
    remaining_simulations: int = 1000
) -> Dict[str, float]:
    """
    Monte Carlo simulator: forecast match outcomes from current minute.

    Args:
        home_pes (float): Home team's average Player Energy Score [15, 100]
        away_pes (float): Away team's average Player Energy Score [15, 100]
        current_minute (int): Current match minute [0, 90]
        remaining_simulations (int): Number of Monte Carlo trials (default 1000)

    Returns:
        dict: {
            'home_win': float (0-100),
            'draw': float (0-100),
            'away_win': float (0-100)
        }

    Logic:
        - Remaining time = 90 - current_minute
        - Scale goal intensity lambda by avg(team_pes) / 100 (energy multiplier)
        - Draw Poisson samples for home and away goals over remaining time
        - Tally outcomes across trials
        - Return outcome percentages
    """
    if remaining_simulations < 1:
        remaining_simulations = 1000

    try:
        # Validate and clamp inputs
        home_pes = np.clip(float(home_pes), MIN_PHYSIOLOGICAL_ENERGY, BASE_PLAYER_ENERGY)
        away_pes = np.clip(float(away_pes), MIN_PHYSIOLOGICAL_ENERGY, BASE_PLAYER_ENERGY)
        current_minute = max(0, min(90, int(current_minute)))
        remaining_minutes = 90 - current_minute

        # If match is over, return deterministic outcome
        if remaining_minutes <= 0:
            return {
                'home_win': 33.33,
                'draw': 33.33,
                'away_win': 33.33
            }

        # Scale goal intensities by team energy (PES affects goal-scoring ability)
        home_energy_factor = home_pes / BASE_PLAYER_ENERGY
        away_energy_factor = away_pes / BASE_PLAYER_ENERGY

        # Adjust lambda: base intensity scaled by energy and remaining time fraction
        time_fraction = remaining_minutes / 90.0
        home_lambda = BASE_GOAL_INTENSITY_LAMBDA * time_fraction * home_energy_factor
        away_lambda = BASE_GOAL_INTENSITY_LAMBDA * time_fraction * away_energy_factor

        # Run Monte Carlo: draw goals from Poisson
        home_goals = np.random.poisson(home_lambda, size=remaining_simulations)
        away_goals = np.random.poisson(away_lambda, size=remaining_simulations)

        # Tally outcomes
        home_wins = np.sum(home_goals > away_goals)
        draws = np.sum(home_goals == away_goals)
        away_wins = np.sum(away_goals > home_goals)

        # Convert to percentages
        total = remaining_simulations
        home_win_pct = (home_wins / total) * 100.0
        draw_pct = (draws / total) * 100.0
        away_win_pct = (away_wins / total) * 100.0

        return {
            'home_win': round(home_win_pct, 2),
            'draw': round(draw_pct, 2),
            'away_win': round(away_win_pct, 2)
        }

    except (TypeError, ValueError) as e:
        # Fallback: balanced outcome
        return {
            'home_win': 33.33,
            'draw': 33.34,
            'away_win': 33.33
        }


if __name__ == "__main__":
    """Unit tests for player energy and match simulation."""

    print("=" * 70)
    print("FIFA Shadow Coach Model - Unit Tests")
    print("=" * 70)

    # Test 1: calculate_player_energy with fresh player
    print("\nTest 1: Fresh player (no match history)")
    pes_fresh = calculate_player_energy([])
    assert pes_fresh == 100.0, f"Expected 100.0, got {pes_fresh}"
    print(f"✓ PES (fresh): {pes_fresh}")

    # Test 2: calculate_player_energy with single recent match
    print("\nTest 2: Player after recent intense match")
    match_logs = [
        {'minutes_played': 90.0, 'days_ago': 1.0, 'match_intensity': 0.9}
    ]
    pes_fatigued = calculate_player_energy(match_logs)
    assert 15.0 <= pes_fatigued < 100.0, f"PES out of bounds: {pes_fatigued}"
    print(f"✓ PES (fatigued): {pes_fatigued:.2f}")

    # Test 3: calculate_player_energy with multiple matches
    print("\nTest 3: Player with 3-match history")
    match_logs = [
        {'minutes_played': 90.0, 'days_ago': 0.5, 'match_intensity': 0.8},
        {'minutes_played': 75.0, 'days_ago': 5.0, 'match_intensity': 0.7},
        {'minutes_played': 45.0, 'days_ago': 10.0, 'match_intensity': 0.6},
    ]
    pes_recovery = calculate_player_energy(match_logs)
    assert 15.0 <= pes_recovery <= 100.0, f"PES out of bounds: {pes_recovery}"
    print(f"✓ PES (recovering): {pes_recovery:.2f}")

    # Test 4: Energy floor (minimum physiological)
    print("\nTest 4: Energy floor validation")
    extreme_logs = [
        {'minutes_played': 90.0, 'days_ago': 0.0, 'match_intensity': 1.0},
        {'minutes_played': 90.0, 'days_ago': 0.1, 'match_intensity': 1.0},
        {'minutes_played': 90.0, 'days_ago': 0.2, 'match_intensity': 1.0},
    ]
    pes_floor = calculate_player_energy(extreme_logs)
    assert pes_floor >= MIN_PHYSIOLOGICAL_ENERGY, f"Below floor: {pes_floor}"
    print(f"✓ PES (bounded): {pes_floor:.2f} >= {MIN_PHYSIOLOGICAL_ENERGY}")

    # Test 5: simulate_match_state - early match
    print("\nTest 5: Monte Carlo - Early match (minute 30)")
    outcome_early = simulate_match_state(
        home_pes=85.0,
        away_pes=75.0,
        current_minute=30,
        remaining_simulations=1000
    )
    total_prob = outcome_early['home_win'] + outcome_early['draw'] + outcome_early['away_win']
    assert abs(total_prob - 100.0) < 0.1, f"Probabilities don't sum to 100: {total_prob}"
    assert outcome_early['home_win'] > outcome_early['away_win'], "Home advantage not reflected"
    print(f"✓ Outcome (30'): Home {outcome_early['home_win']}%, Draw {outcome_early['draw']}%, Away {outcome_early['away_win']}%")

    # Test 6: simulate_match_state - late match
    print("\nTest 6: Monte Carlo - Late match (minute 85)")
    outcome_late = simulate_match_state(
        home_pes=80.0,
        away_pes=80.0,
        current_minute=85,
        remaining_simulations=1000
    )
    total_prob_late = outcome_late['home_win'] + outcome_late['draw'] + outcome_late['away_win']
    assert abs(total_prob_late - 100.0) < 0.1, f"Probabilities don't sum to 100: {total_prob_late}"
    print(f"✓ Outcome (85'): Home {outcome_late['home_win']}%, Draw {outcome_late['draw']}%, Away {outcome_late['away_win']}%")

    # Test 7: simulate_match_state - match over
    print("\nTest 7: Monte Carlo - Match over (minute 90+)")
    outcome_over = simulate_match_state(
        home_pes=80.0,
        away_pes=80.0,
        current_minute=91,
        remaining_simulations=1000
    )
    # Fallback should return balanced probabilities
    assert abs(outcome_over['home_win'] - 33.33) < 1.0, "Match-over fallback failed"
    print(f"✓ Outcome (90+): Home {outcome_over['home_win']}%, Draw {outcome_over['draw']}%, Away {outcome_over['away_win']}%")

    # Test 8: Energy factor effect on goal simulation
    print("\nTest 8: Energy differential effect on outcomes")
    high_energy = simulate_match_state(95.0, 50.0, 45, 1000)
    low_energy = simulate_match_state(50.0, 95.0, 45, 1000)
    assert high_energy['home_win'] > low_energy['home_win'], "High energy should improve home win %"
    print(f"✓ High energy home: {high_energy['home_win']}% | Low energy home: {low_energy['home_win']}%")

    print("\n" + "=" * 70)
    print("All tests passed ✓")
    print("=" * 70)
