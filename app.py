"""FIFA Shadow Coach — Live Match Analytics Dashboard (Agent-Powered)"""
import streamlit as st
import pandas as pd
import numpy as np
import time
import json
import asyncio
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent orchestrator
try:
    from orchestrator import MasterOrchestrator
    _HAS_ORCHESTRATOR = True
except ImportError:
    _HAS_ORCHESTRATOR = False
    logger.warning("Orchestrator not available")

# Legacy model (fallback for simulation)
try:
    from model import simulate_match_state
    _HAS_MODEL = True
except ImportError:
    _HAS_MODEL = False

# Redis connection for agent data
try:
    import redis
    _redis = redis.Redis(host="localhost", port=6379, decode_responses=True, socket_connect_timeout=2)
    _redis.ping()
    _HAS_REDIS = True
except Exception as e:
    _HAS_REDIS = False
    _redis = None
    logger.warning(f"Redis unavailable: {e}")

st.set_page_config(
    page_title="FIFA Shadow Coach - Live Match Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== ORCHESTRATOR STARTUP ====================

_FALLBACK_TEAMS = ["Brazil", "France", "Argentina", "Germany", "England",
                   "Mexico", "South Korea", "United States", "Portugal", "Belgium"]

@st.cache_resource
def start_orchestrator():
    """Start orchestrator in background thread if Redis available."""
    if not _HAS_ORCHESTRATOR or not _HAS_REDIS:
        logger.info("Skipping orchestrator: dependencies not available")
        return None

    try:
        orchestrator = MasterOrchestrator(redis_host="localhost", redis_port=6379)

        def run_orchestrator():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                logger.info("Starting orchestrator loop")
                loop.run_until_complete(orchestrator.run())
            except Exception as e:
                logger.error(f"Orchestrator error: {e}")
            finally:
                loop.close()

        thread = threading.Thread(target=run_orchestrator, daemon=True)
        thread.start()
        logger.info("Orchestrator started in background thread")
        return orchestrator
    except Exception as e:
        logger.error(f"Failed to start orchestrator: {e}")
        return None

# Start orchestrator on app load
_orchestrator = start_orchestrator()

# ==================== REDIS DATA ACCESS ====================

def get_live_matches() -> List[Dict[str, Any]]:
    """Fetch live matches from Redis (populated by DataCollectionAgent)."""
    if not _HAS_REDIS or _redis is None:
        return []
    try:
        match_keys = _redis.keys("fifa:match:*:data")
        matches = []
        for key in match_keys:
            data = _redis.get(key)
            if data:
                try:
                    matches.append(json.loads(data))
                except json.JSONDecodeError:
                    pass
        return matches
    except Exception as e:
        logger.warning(f"Error fetching matches: {e}")
        return []

def get_team_fitness(team: str, match_id: str) -> Dict[str, Any]:
    """Get team fitness from Redis (populated by FitnessModelAgent)."""
    if not _HAS_REDIS or _redis is None:
        return {"team": team, "players": {}, "avg_fitness": 80.0}
    try:
        key = f"fifa:match:{match_id}:fitness:{team}"
        data = _redis.get(key)
        if data:
            return json.loads(data)
        return {"team": team, "players": {}, "avg_fitness": 80.0}
    except Exception:
        return {"team": team, "players": {}, "avg_fitness": 80.0}

def get_recommendations(match_id: str) -> Dict[str, Any]:
    """Get substitution recommendations from Redis (populated by RecommendationEngineAgent)."""
    if not _HAS_REDIS or _redis is None:
        return {"match_id": match_id, "home_recommendations": [], "away_recommendations": []}
    try:
        key = f"fifa:match:{match_id}:recommendations"
        data = _redis.get(key)
        if data:
            return json.loads(data)
        return {"match_id": match_id, "home_recommendations": [], "away_recommendations": []}
    except Exception:
        return {"match_id": match_id, "home_recommendations": [], "away_recommendations": []}

def get_match_state(match_id: str) -> Dict[str, Any]:
    """Get match state from Redis (populated by LiveMatchAgent)."""
    if not _HAS_REDIS or _redis is None:
        return {"match_id": match_id, "state": "UNKNOWN", "minute": 0}
    try:
        key = f"fifa:match:{match_id}:state"
        data = _redis.get(key)
        if data:
            return json.loads(data)
        return {"match_id": match_id, "state": "UNKNOWN", "minute": 0}
    except Exception:
        return {"match_id": match_id, "state": "UNKNOWN", "minute": 0}

@st.cache_data(ttl=30)
def load_live_matches_df() -> pd.DataFrame:
    """Load live matches from orchestrator (via Redis)."""
    matches = get_live_matches()
    if not matches:
        return pd.DataFrame()
    try:
        return pd.DataFrame(matches)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def load_all_teams() -> list:
    """Get all teams from live matches or fallback list."""
    matches = get_live_matches()
    if not matches:
        return _FALLBACK_TEAMS
    teams = set()
    for match in matches:
        if "home_team" in match:
            teams.add(match["home_team"])
        if "away_team" in match:
            teams.add(match["away_team"])
    return sorted(list(teams)) if teams else _FALLBACK_TEAMS

@st.cache_data(ttl=30)
def get_team_energy_from_agents(team: str, match_id: Optional[str] = None) -> dict:
    """Get team energy from orchestrator fitness model."""
    if match_id:
        fitness = get_team_fitness(team, match_id)
        players = fitness.get("players", {})
        if players:
            avg_fitness = np.mean([p.get("fitness", 80) if isinstance(p, dict) else 80
                                 for p in players.values()])
        else:
            avg_fitness = 80.0
        return {
            "energy": avg_fitness,
            "confidence": 0.95,
            "metric_source": "agent_fitness_model",
            "match_count": len(players),
            "players": players
        }
    return {"energy": 80.0, "confidence": 0.05, "metric_source": "default_baseline", "match_count": 0}

def _get_orchestrator_status() -> str:
    """Check orchestrator status via Redis."""
    if not _HAS_REDIS or _redis is None:
        return "No Redis"
    try:
        status = _redis.get("fifa:orchestrator:status")
        if status:
            data = json.loads(status)
            return f"Cycle {data.get('cycle_count', 0)}"
        return "Starting..."
    except Exception:
        return "Offline"

def _data_source_badge() -> str:
    """Return current data source."""
    if not _HAS_ORCHESTRATOR or not _HAS_REDIS:
        return "DEMO"
    status = _get_orchestrator_status()
    if status == "Offline" or status == "No Redis":
        return "DEMO"
    return "AGENT-POWERED"

# ==================== SIDEBAR ====================

st.sidebar.title("FIFA Shadow Coach")

source_badge = _data_source_badge()
if "AGENT" in source_badge:
    st.sidebar.success(f"Source: {source_badge}")
else:
    st.sidebar.warning(f"Source: {source_badge}")

orchestrator_status = _get_orchestrator_status()
st.sidebar.caption(f"Orchestrator: {orchestrator_status}")

# Show active matches
matches = get_live_matches()
if matches:
    st.sidebar.caption(f"{len(matches)} live match(es)")
else:
    st.sidebar.caption("No live matches")

st.sidebar.divider()

teams = load_all_teams()
home_team = st.sidebar.selectbox("Home Team", teams, index=0)
away_options = [t for t in teams if t != home_team]
away_team = st.sidebar.selectbox("Away Team", away_options, index=0 if away_options else 0)

if st.sidebar.button("Refresh Now"):
    st.cache_data.clear()
    st.rerun()

# ==================== MAIN CONTENT ====================

st.header("Live & Today's Matches")
st.caption("Source: Agent-powered real-time data collection from ESPN/Sofascore")

matches_df = load_live_matches_df()
if not matches_df.empty:
    STATUS_COLORS = {"LIVE": "🟢", "FINISHED": "⚪", "SCHEDULED": "🔵", "CANCELED": "🔴", "POSTPONED": "🟡"}

    cols_per_row = 3
    rows = [matches_df.iloc[i:i + cols_per_row] for i in range(0, len(matches_df), cols_per_row)]

    for row_batch in rows:
        cols = st.columns(cols_per_row)
        for idx, (_, match) in enumerate(row_batch.iterrows()):
            with cols[idx]:
                status = str(match.get("status", "SCHEDULED"))
                icon = STATUS_COLORS.get(status, "⚪")
                league_raw = str(match.get("league", ""))
                league_label = "World Cup" if "world" in league_raw else "Friendly"

                st.markdown(
                    f"**{icon} {match['home_team']} {int(match.get('home_score', 0))} — "
                    f"{int(match.get('away_score', 0))} {match['away_team']}**  \n"
                    f"_{league_label}_ · {status}"
                )
else:
    st.info("No matches found. Orchestrator is starting up or no live matches available.")

st.divider()

# ==================== SQUAD ENERGY & SIMULATION ====================

col_left, col_right = st.columns([1.2, 1])

with col_left:
    st.subheader(f"Squad Fitness — {home_team}")
    st.caption("Real-time fitness estimation from agent fitness model")

    home_fitness = get_team_energy_from_agents(home_team)
    players = home_fitness.get("players", {})

    if players and isinstance(players, dict):
        player_list = []
        for player_id, player_data in players.items():
            if isinstance(player_data, dict):
                player_list.append({
                    "Player": player_id,
                    "Fitness": player_data.get("fitness", 80),
                    "Position": player_data.get("position", "Unknown"),
                    "Minutes": player_data.get("minutes", 0),
                })

        if player_list:
            players_df = pd.DataFrame(player_list)
            players_df["Fatigue Risk"] = players_df["Fitness"].apply(
                lambda x: "HIGH" if x < 50 else ("MEDIUM" if x < 75 else "LOW")
            )

            color_fn = lambda v: f"background-color: {'#ff6b6b' if v < 50 else '#ffd43b' if v < 75 else '#51cf66'}"
            styled = players_df.style.applymap(color_fn, subset=["Fitness"]).format({"Fitness": "{:.0f}"})
            st.dataframe(styled, use_container_width=True, hide_index=True)
        else:
            st.info("No player fitness data available yet.")
    else:
        st.info("Waiting for agent to populate fitness data...")

with col_right:
    st.subheader("Match Simulation")

    home_energy = home_fitness.get("energy", 80.0)
    away_fitness = get_team_energy_from_agents(away_team)
    away_energy = away_fitness.get("energy", 80.0)

    pes_col1, pes_col2 = st.columns(2)
    pes_col1.metric(f"{home_team} Fitness", f"{home_energy:.0f}")
    pes_col2.metric(f"{away_team} Fitness", f"{away_energy:.0f}")

    home_conf = home_fitness.get("confidence", 0.0)
    away_conf = away_fitness.get("confidence", 0.0)
    conf_label = f"{home_conf:.0%} / {away_conf:.0%}"

    st.caption(f"Confidence: {conf_label} | Source: Agent Fitness Model")

    if _HAS_MODEL and st.button("Run Simulation (60' → 90')", use_container_width=True):
        h_pes, a_pes = home_energy, away_energy
        chart_data, chart_ph, status_ph = [], st.empty(), st.empty()

        for minute in range(60, 91, 5):
            outcome = simulate_match_state(h_pes, a_pes, minute, 5000)
            chart_data.append({
                "Min": minute,
                f"{home_team} Win": outcome["home_win"],
                "Draw": outcome["draw"],
                f"{away_team} Win": outcome["away_win"],
            })
            with chart_ph.container():
                st.line_chart(
                    pd.DataFrame(chart_data).set_index("Min"),
                    use_container_width=True,
                )
            status_ph.markdown(
                f"**Minute {minute}'** — "
                f"{home_team}: {outcome['home_win']:.0f}% · "
                f"Draw: {outcome['draw']:.0f}% · "
                f"{away_team}: {outcome['away_win']:.0f}%"
            )
            h_pes = max(50, h_pes - 0.5)
            a_pes = max(50, a_pes - 0.5)
            time.sleep(0.2)

        st.success("Simulation complete!")
    elif not _HAS_MODEL:
        st.warning("Simulation model not available")

# ==================== SUBSTITUTION RECOMMENDATIONS ====================

st.divider()
st.header("AI Substitution Recommendations")
st.caption("Powered by RecommendationEngineAgent")

# Find match ID for selected teams
match_id = None
for match in get_live_matches():
    if match.get("home_team") == home_team and match.get("away_team") == away_team:
        match_id = match.get("match_id")
        break

if match_id:
    recs = get_recommendations(match_id)
    home_recs = recs.get("home_recommendations", [])
    away_recs = recs.get("away_recommendations", [])

    if home_recs or away_recs:
        if home_recs:
            st.subheader(f"{home_team} Recommendations")
            for rec in home_recs:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write("**Remove:**")
                    st.metric("Player", rec.get("off_player_name", "Unknown"),
                             f"Fitness: {rec.get('off_fitness', 0):.0f}")
                with col2:
                    st.write("**Bring On:**")
                    st.metric("Replacement", rec.get("on_player_name", "Unknown"),
                             f"Fitness: {rec.get('on_fitness', 0):.0f}")
                with col3:
                    st.write("**Impact:**")
                    st.metric("Confidence", f"{rec.get('confidence', 0):.0%}")
                st.caption(f"Reasons: {', '.join(rec.get('reasons', []))}")

        if away_recs:
            st.subheader(f"{away_team} Recommendations")
            for rec in away_recs:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write("**Remove:**")
                    st.metric("Player", rec.get("off_player_name", "Unknown"),
                             f"Fitness: {rec.get('off_fitness', 0):.0f}")
                with col2:
                    st.write("**Bring On:**")
                    st.metric("Replacement", rec.get("on_player_name", "Unknown"),
                             f"Fitness: {rec.get('on_fitness', 0):.0f}")
                with col3:
                    st.write("**Impact:**")
                    st.metric("Confidence", f"{rec.get('confidence', 0):.0%}")
                st.caption(f"Reasons: {', '.join(rec.get('reasons', []))}")
    else:
        st.info("No substitution recommendations available yet. Agents are processing...")
else:
    st.warning("Select a live match to see recommendations")

# ==================== DEBUG INFO ====================

if st.checkbox("Show Debug Info"):
    st.subheader("Debug Information")

    with st.expander("Orchestrator Status"):
        if _HAS_ORCHESTRATOR:
            st.success("Orchestrator available")
            st.info(f"Status: {_get_orchestrator_status()}")
        else:
            st.error("Orchestrator not installed")

    with st.expander("Redis Connection"):
        if _HAS_REDIS:
            st.success("Redis available")
            try:
                info = _redis.info("server")
                st.json({"Redis Version": info.get("redis_version"), "Uptime": info.get("uptime_in_seconds")})
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.error("Redis not available")

    with st.expander("Live Matches in Redis"):
        matches = get_live_matches()
        st.json(matches)

st.markdown("---")
st.caption("FIFA Shadow Coach v3.1 — Agent-Powered Live Analytics | Powered by Claude")
