"""
FIFA World Cup 2026 - Live Match Analytics & Substitution Recommendations
Streamlit Dashboard exclusively for 48 World Cup teams
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
import time
from pathlib import Path
from datetime import datetime

st.set_page_config(
    page_title="FIFA World Cup 2026 - Live Match Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== DATA LOADING ====================

WC_TEAMS = [
    # North America
    "United States", "Mexico", "Canada",
    # South America
    "Argentina", "Brazil", "Colombia", "Ecuador", "Paraguay", "Uruguay",
    # Europe
    "England", "France", "Germany", "Spain", "Portugal", "Italy",
    "Netherlands", "Belgium", "Denmark", "Sweden", "Poland", "Austria",
    "Czechia", "Switzerland", "Serbia", "Norway",
    # Africa
    "Egypt", "Cameroon", "Senegal", "Ghana", "Nigeria", "Morocco",
    "Ivory Coast", "Mali", "Tunisia",
    # Asia
    "Japan", "South Korea", "Saudi Arabia", "Iran", "Iraq", "Australia",
    "Uzbekistan", "Qatar",
]

@st.cache_data(ttl=300)
def load_team_pes() -> pd.DataFrame:
    """Load trained World Cup team PES data"""
    try:
        return pd.read_parquet("data/world_cup_2026/world_cup_2026_teams_trained.parquet")
    except FileNotFoundError:
        st.warning("World Cup team data not found. Run world_cup_trainer.py first.")
        return create_mock_world_cup_pes()

@st.cache_data(ttl=300)
def load_player_pes() -> pd.DataFrame:
    """Load trained World Cup player PES data"""
    try:
        return pd.read_parquet("data/world_cup_2026/world_cup_2026_players_trained.parquet")
    except FileNotFoundError:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_squad_profiles() -> dict:
    """Load World Cup squad profiles"""
    try:
        with open("data/world_cup_2026/world_cup_2026_squads.json", 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def create_mock_world_cup_pes() -> pd.DataFrame:
    """Create mock PES data for demonstration"""
    import random

    data = []
    for team in WC_TEAMS:
        pes = random.uniform(60, 92)
        data.append({
            'team': team,
            'current_pes': round(pes, 1),
            'status': 'ELITE' if pes > 82 else 'STRONG' if pes > 75 else 'COMPETITIVE'
        })

    return pd.DataFrame(data).sort_values('current_pes', ascending=False)

# ==================== SIDEBAR ====================

st.sidebar.title("FIFA World Cup 2026")
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/2/2e/2026_FIFA_World_Cup_logo.svg", width=200)

st.sidebar.info("""
**🏆 World Cup 2026**
- 48 Teams
- 80 Matches
- June 11 - July 19, 2026
""")

st.sidebar.divider()

# Load data
team_pes = load_team_pes()
player_pes = load_player_pes()
squad_profiles = load_squad_profiles()

st.sidebar.metric("Teams Trained", len(team_pes))
st.sidebar.metric("Players Loaded", len(player_pes) if not player_pes.empty else "—")

# Team selection
st.sidebar.subheader("Match Setup")
home_options = sorted(WC_TEAMS)
home_team = st.sidebar.selectbox("Home Team", home_options, key="home")

away_options = [t for t in sorted(WC_TEAMS) if t != home_team]
away_team = st.sidebar.selectbox("Away Team", away_options, key="away")

st.sidebar.divider()

# Control buttons
if st.sidebar.button("Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

auto_refresh = st.sidebar.toggle("Auto-refresh (30s)", value=False)

# ==================== MAIN DASHBOARD ====================

st.title("FIFA World Cup 2026 - Live Match Analytics")
st.caption("AI-powered substitution recommendations for all 48 World Cup teams")

# ==================== TOURNAMENT OVERVIEW ====================

col1, col2, col3 = st.columns(3)
col1.metric("Total Teams", len(WC_TEAMS))
col2.metric("Tournament Matches", "80")
col3.metric("Tournament Duration", "40 Days")

st.divider()

# ==================== TEAM RANKINGS ====================

st.header("World Cup 2026 Team Rankings")

# Categorize teams
elite = team_pes[team_pes['current_pes'] > 82]
strong = team_pes[(team_pes['current_pes'] > 75) & (team_pes['current_pes'] <= 82)]
competitive = team_pes[(team_pes['current_pes'] > 68) & (team_pes['current_pes'] <= 75)]
developing = team_pes[team_pes['current_pes'] <= 68]

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.subheader("Elite")
    for idx, (_, row) in enumerate(elite.iterrows(), 1):
        st.write(f"{idx}. **{row['team']}** ({row['current_pes']:.1f})")

with col2:
    st.subheader("Strong")
    for idx, (_, row) in enumerate(strong.iterrows(), 1):
        st.write(f"{idx}. **{row['team']}** ({row['current_pes']:.1f})")

with col3:
    st.subheader("Competitive")
    for idx, (_, row) in enumerate(competitive.head(5).iterrows(), 1):
        st.write(f"{idx}. **{row['team']}** ({row['current_pes']:.1f})")
    if len(competitive) > 5:
        st.caption(f"... and {len(competitive)-5} more")

with col4:
    st.subheader("Developing")
    for idx, (_, row) in enumerate(developing.head(5).iterrows(), 1):
        st.write(f"{idx}. **{row['team']}** ({row['current_pes']:.1f})")
    if len(developing) > 5:
        st.caption(f"... and {len(developing)-5} more")

st.divider()

# ==================== MATCH ANALYSIS ====================

st.header(f"Match Analysis: {home_team} vs {away_team}")

col1, col2 = st.columns(2)

with col1:
    home_pes = team_pes[team_pes['team'] == home_team]['current_pes'].values
    home_pes = home_pes[0] if len(home_pes) > 0 else 75
    st.metric(f"{home_team}", f"{home_pes:.1f} PES", "Home Advantage")

with col2:
    away_pes = team_pes[team_pes['team'] == away_team]['current_pes'].values
    away_pes = away_pes[0] if len(away_pes) > 0 else 75
    st.metric(f"{away_team}", f"{away_pes:.1f} PES", "Away")

st.divider()

# ==================== SQUAD DETAILS ====================

col1, col2 = st.columns(2)

with col1:
    st.subheader(f"{home_team} Squad")
    if home_team in squad_profiles:
        profile = squad_profiles[home_team]
        st.write(f"**Team PES**: {profile.get('team_pes', 'N/A')}")
        st.write(f"**Status**: {profile.get('status', 'N/A')}")
        st.write(f"**Squad Size**: {profile.get('squad_size', 'N/A')} players")

        # Show positions
        positions = profile.get('positions', {})
        if positions:
            st.write("**Key Players by Position**:")
            for pos, players in positions.items():
                if players and pos != 'BENCH':
                    st.write(f"  {pos}: {players[0]['name']} ({players[0]['pes']:.1f} PES)")
    else:
        st.info("Squad data not available")

with col2:
    st.subheader(f"{away_team} Squad")
    if away_team in squad_profiles:
        profile = squad_profiles[away_team]
        st.write(f"**Team PES**: {profile.get('team_pes', 'N/A')}")
        st.write(f"**Status**: {profile.get('status', 'N/A')}")
        st.write(f"**Squad Size**: {profile.get('squad_size', 'N/A')} players")

        # Show positions
        positions = profile.get('positions', {})
        if positions:
            st.write("**Key Players by Position**:")
            for pos, players in positions.items():
                if players and pos != 'BENCH':
                    st.write(f"  {pos}: {players[0]['name']} ({players[0]['pes']:.1f} PES)")
    else:
        st.info("Squad data not available")

st.divider()

# ==================== LIVE SUBSTITUTION RECOMMENDATIONS ====================

st.header("Live Substitution Recommendations")

try:
    from live_match_engine import LiveMatchEngine
    _HAS_ENGINE = True
except ImportError:
    _HAS_ENGINE = False

if _HAS_ENGINE:
    with st.expander("Show Live Match Simulator", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            minute = st.slider("Match Minute", 0, 90, 45, 5)

        with col2:
            home_score = st.number_input(f"{home_team} Goals", 0, 10, 0)

        with col3:
            away_score = st.number_input(f"{away_team} Goals", 0, 10, 0)

        if st.button("Get Substitution Recommendations", use_container_width=True):
            try:
                engine = LiveMatchEngine()

                # Create lineups from squad data
                home_lineup = [f"{home_team}_P{i}" for i in range(11)]
                away_lineup = [f"{away_team}_P{i}" for i in range(11)]

                # Start match
                match_id = engine.start_live_match(home_team, away_team, home_lineup, away_lineup)

                # Update match state
                update = engine.update_live_match(
                    match_id,
                    score={"home": int(home_score), "away": int(away_score)},
                    minute=int(minute)
                )

                fatigue = (minute / 90) * 100

                st.subheader(f"Minute {minute}' - {home_team} {int(home_score)} - {int(away_score)} {away_team}")
                st.write(f"**Player Fatigue Level**: ~{fatigue:.0f}%")

                if update['recommendations']:
                    for rec in update['recommendations']:
                        with st.container(border=True):
                            st.subheader(f"{rec['team'].upper()}")
                            st.write(f"**Reason**: {rec['reason']}")

                            rec_col1, rec_col2, rec_col3 = st.columns(3)

                            with rec_col1:
                                st.write("**REMOVE**")
                                st.metric(
                                    "Player",
                                    rec['off_player']['id'][-2:],
                                    f"PES: {rec['off_player']['current_pes']:.1f}"
                                )
                                st.write(f"Fatigue: {rec['off_player']['fatigue']:.0f}%")

                            with rec_col2:
                                st.write("**BRING ON**")
                                st.metric(
                                    "Replacement",
                                    rec['on_player']['id'][-2:],
                                    f"PES: {rec['on_player']['current_pes']:.1f}"
                                )
                                st.write("Fresh (0%)")

                            with rec_col3:
                                st.write("**IMPACT**")
                                impact = rec['impact_potential']
                                if impact > 0:
                                    st.success(f"+{impact:.1f} PES")
                                else:
                                    st.info(f"{impact:.1f} PES")

                else:
                    if fatigue < 70:
                        st.info(f"No substitution needed yet. Players are fresh ({fatigue:.0f}% fatigue)")
                    else:
                        st.warning("No high-impact substitution available at this time")

            except Exception as e:
                st.error(f"Error: {str(e)}")

else:
    st.info("Live match engine not available. Install dependencies for recommendations.")

st.divider()

# ==================== TOURNAMENT ANALYSIS ====================

st.header("Tournament Analysis")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Regional Strength")

    regions = {
        "North America": ["United States", "Mexico", "Canada"],
        "South America": ["Argentina", "Brazil", "Colombia", "Ecuador", "Paraguay", "Uruguay"],
        "Europe": ["England", "France", "Germany", "Spain", "Portugal", "Italy", "Netherlands", "Belgium", "Denmark", "Sweden", "Poland", "Austria", "Czechia", "Switzerland", "Serbia", "Norway"],
        "Africa": ["Egypt", "Cameroon", "Senegal", "Ghana", "Nigeria", "Morocco", "Ivory Coast", "Mali", "Tunisia"],
        "Asia": ["Japan", "South Korea", "Saudi Arabia", "Iran", "Iraq", "Australia", "Uzbekistan", "Qatar"],
    }

    region_stats = []
    for region, teams in regions.items():
        region_df = team_pes[team_pes['team'].isin(teams)]
        if not region_df.empty:
            avg_pes = region_df['current_pes'].mean()
            region_stats.append({
                'Region': region,
                'Avg PES': f"{avg_pes:.1f}",
                'Teams': len(region_df)
            })

    region_df_display = pd.DataFrame(region_stats)
    st.dataframe(region_df_display, use_container_width=True, hide_index=True)

with col2:
    st.subheader("Key Statistics")

    st.metric("Mean Team PES", f"{team_pes['current_pes'].mean():.2f}")
    st.metric("PES Range", f"{team_pes['current_pes'].min():.1f} - {team_pes['current_pes'].max():.1f}")
    st.metric("Std Deviation", f"{team_pes['current_pes'].std():.2f}")

st.divider()

# ==================== AUTO-REFRESH ====================

if auto_refresh:
    time.sleep(30)
    st.rerun()

# ==================== FOOTER ====================

st.caption("""
FIFA World Cup 2026 - Live Match Analytics System
- 48 Teams trained
- AI-powered substitution recommendations
- Real-time fatigue tracking
- Squad rotation planning

Data sources: Bustami/efi-fifa-data-wc-2026 | Kaggle FIFA Dataset | Machina.gg API
""")
