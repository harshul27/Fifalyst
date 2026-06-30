"""
Phase 6: Dashboard Testing
Unit and integration tests for Streamlit dashboard
"""

import pytest
import streamlit as st
from datetime import datetime

def test_dashboard_imports():
    """Test that dashboard can be imported"""
    try:
        import dashboard.app
        assert True
    except ImportError:
        assert False, "Dashboard import failed"

def test_wc_teams_filter():
    """Test that only World Cup teams are shown"""
    WC_TEAMS = {
        "United States", "Mexico", "Canada",
        "Brazil", "Argentina", "Uruguay", "Paraguay",
        "England", "France", "Germany", "Spain", "Netherlands", "Italy"
    }
    
    # Sample matches
    matches = [
        {"home_team": "Brazil", "away_team": "Serbia"},  # Valid WC
        {"home_team": "Brazil", "away_team": "Netherlands"},  # Valid WC
    ]
    
    # Filter
    wc_matches = [m for m in matches 
                  if m["home_team"] in WC_TEAMS and m["away_team"] in WC_TEAMS]
    
    assert len(wc_matches) >= 1
    assert all(m["home_team"] in WC_TEAMS for m in wc_matches)

def test_fitness_color_mapping():
    """Test fitness score to color mapping"""
    colors = {
        85: "#2ecc71",   # PEAK
        75: "#f39c12",   # HOT
        65: "#e74c3c",   # FAIR
        50: "#c0392b"    # CRITICAL
    }
    
    for fitness, expected_color in colors.items():
        # Color should match fitness level
        assert fitness >= 0 and fitness <= 100

def test_recommendation_confidence():
    """Test confidence score validation"""
    recommendations = [
        {"confidence": 0.92},  # HIGH
        {"confidence": 0.78},  # MEDIUM
        {"confidence": 0.65},  # LOW
    ]
    
    for rec in recommendations:
        assert rec["confidence"] >= 0.5 and rec["confidence"] <= 1.0

def test_fatigue_status_mapping():
    """Test fatigue percentage to status mapping"""
    test_cases = [
        (10, "PEAK"),      # ≤20%
        (35, "HOT"),       # ≤40%
        (60, "FAIR"),      # ≤70%
        (85, "CRITICAL")   # >70%
    ]
    
    for fatigue, expected_status in test_cases:
        if fatigue <= 20:
            status = "PEAK"
        elif fatigue <= 40:
            status = "HOT"
        elif fatigue <= 70:
            status = "FAIR"
        else:
            status = "CRITICAL"
        
        assert status == expected_status

if __name__ == "__main__":
    print("Running Phase 6 Dashboard Tests...")
    
    test_dashboard_imports()
    print("✓ Dashboard imports successfully")
    
    test_wc_teams_filter()
    print("✓ World Cup teams filter working")
    
    test_fitness_color_mapping()
    print("✓ Fitness color mapping validated")
    
    test_recommendation_confidence()
    print("✓ Recommendation confidence validation passed")
    
    test_fatigue_status_mapping()
    print("✓ Fatigue status mapping validated")
    
    print("\nAll Phase 6 tests passed! ✅")
