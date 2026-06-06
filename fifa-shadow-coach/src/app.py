"""FIFA Shadow Coach - Interactive Sports Analytics Dashboard"""
import streamlit as st
import pandas as pd
import time
from pathlib import Path
from model import simulate_match_state

st.set_page_config(page_title="FIFA Shadow Coach", layout="wide")

@st.cache_data
def load_squad_state():
    try:
        df = pd.read_parquet(Path("data/latest_squad_state.parquet"))
        return df if not df.empty else None
    except:
        return None

st.sidebar.title("Match Configuration")
countries = ["Brazil", "France", "Argentina", "Germany", "England"]
home_country = st.sidebar.selectbox("Home Team", countries)
away_country = st.sidebar.selectbox("Away Team", [c for c in countries if c != home_country])

col_left, col_right = st.columns([1.2, 1])

with col_left:
    st.subheader("Squad State & Fatigue")
    squad_df = load_squad_state()
    if squad_df is not None:
        squad_df = squad_df.copy()
        squad_df['risk'] = squad_df['pes'].apply(
            lambda x: 'HIGH' if x < 50 else ('MEDIUM' if x < 75 else 'LOW'))
        display_df = squad_df[['player', 'pes', 'risk', 'n_matches']].copy()
        display_df.columns = ['Player', 'Energy', 'Risk', 'Matches']
        color_fn = lambda v: f"background-color: {'#ff6b6b' if v < 50 else '#ffd43b' if v < 75 else '#51cf66'}"
        styled = display_df.style.applymap(color_fn, subset=['Energy']).format({'Energy': '{:.0f}'})
        st.dataframe(styled, use_container_width=True)
    else:
        st.error("No squad data. Run pipeline first.")

with col_right:
    st.subheader("Live Match Simulation")
    if st.button("Stream Live (60 to 90 minutes)", use_container_width=True):
        home_pes, away_pes = 80.0, 75.0
        chart_data, chart_ph, status_ph = [], st.empty(), st.empty()
        for minute in range(60, 91, 5):
            outcome = simulate_match_state(home_pes, away_pes, minute, 500)
            chart_data.append({'Min': minute, 'Home': outcome['home_win'],
                              'Draw': outcome['draw'], 'Away': outcome['away_win']})
            with chart_ph.container():
                st.line_chart(pd.DataFrame(chart_data).set_index('Min'), use_container_width=True)
            status_ph.markdown(f"Minute {minute} | Home: {outcome['home_win']:.0f}% | "
                             f"Draw: {outcome['draw']:.0f}% | Away: {outcome['away_win']:.0f}%")
            home_pes, away_pes = max(50, home_pes - 0.5), max(50, away_pes - 0.5)
            time.sleep(0.3)
        st.success("Simulation complete!")
