"""FIFA World Cup 2026 - Live Match Analytics Dashboard"""
import streamlit as st
import asyncio
import json
from datetime import datetime
from orchestrator import get_orchestrator

st.set_page_config(
    page_title="FIFA World Cup 2026 - Live Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== SIDEBAR ====================
st.sidebar.title("🏆 FIFA World Cup 2026")
st.sidebar.info("""
**Tournament Info:**
- 48 Teams
- 80 Matches
- June 11 - July 19, 2026
- Real-time ESPN data
""")

col1, col2, col3 = st.sidebar.columns(3)
if col1.button("🔄 Refresh", use_container_width=True):
    st.rerun()

if col2.button("⚙️ Cache Clear", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

auto_refresh = st.sidebar.toggle("Auto-refresh (5min)", value=False)

st.sidebar.divider()
st.sidebar.caption("Powered by ESPN API + AI Fitness Models")

# ==================== MAIN CONTENT ====================
st.title("🎯 FIFA World Cup 2026 Live Analytics")
st.caption("Real-time match tracking, player fitness, and substitution recommendations")

# Fetch live matches
@st.cache_data(ttl=300)
def get_live_data():
    """Fetch live matches from orchestrator (5-min cache)"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    orch = get_orchestrator()
    result = loop.run_until_complete(orch.run_cycle())
    loop.close()
    return result

try:
    live_data = get_live_data()
    matches = live_data.get('matches', [])
except Exception as e:
    st.error(f"Failed to fetch matches: {e}")
    matches = []

# ==================== LIVE MATCHES ====================
st.header("📺 Live & Upcoming Matches")

if not matches:
    st.info("No live World Cup matches at this time. Check back soon!")
else:
    st.metric("Total Matches", len(matches))

    for match in matches:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([2, 1, 2, 1])

            with col1:
                st.write(f"**{match['home_team']}**")

            with col2:
                score = match['score']
                status = match['status']
                minute = match.get('minute', 0)
                if minute > 0:
                    st.write(f"**{score}** ({minute}')")
                else:
                    st.write(f"**{score}**")

            with col3:
                st.write(f"**{match['away_team']}**")

            with col4:
                status_col = "🟢" if status == "LIVE" else "🔵"
                st.write(f"{status_col} {status}")

            # Fitness heatmap (if available during LIVE matches)
            if match.get('home_fitness') or match.get('away_fitness'):
                st.subheader("⚡ Player Fitness")

                fitness_home = match.get('home_fitness', [])
                fitness_away = match.get('away_fitness', [])

                if fitness_home:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**{match['home_team']} Fitness:**")
                        for p in fitness_home[:6]:  # top 6
                            fitness = p.get('fitness', 100)
                            color = "🟢" if fitness > 75 else "🟡" if fitness > 50 else "🔴"
                            st.write(f"{color} {p.get('name', 'Unknown')}: {fitness:.0f}%")

                if fitness_away:
                    with col2:
                        st.write(f"**{match['away_team']} Fitness:**")
                        for p in fitness_away[:6]:  # top 6
                            fitness = p.get('fitness', 100)
                            color = "🟢" if fitness > 75 else "🟡" if fitness > 50 else "🔴"
                            st.write(f"{color} {p.get('name', 'Unknown')}: {fitness:.0f}%")

            # Substitution recommendations (if available)
            if match.get('recommendations'):
                st.subheader("💡 Substitution Recommendations")
                for i, rec in enumerate(match.get('recommendations', [])[:3], 1):
                    confidence = rec.get('confidence', 0)
                    conf_bar = "█" * int(confidence * 10) + "░" * (10 - int(confidence * 10))
                    st.write(f"""
**#{i}** ({confidence*100:.0f}% Confidence) {conf_bar}
- Off: {rec.get('off', '?')} ({rec.get('off_fitness', 0):.0f}% fitness)
- On: {rec.get('on', '?')} ({rec.get('on_fitness', 0):.0f}% fitness)
- Team: {rec.get('team', '?').upper()}
- Reason: {rec.get('reason', '?')}
                    """)

# ==================== SYSTEM STATUS ====================
st.divider()
st.subheader("✅ System Status")

col1, col2, col3, col4 = st.columns(4)
col1.metric("ESPN API", "🟢 Connected")
col2.metric("Fitness Model", "🟢 Ready")
col3.metric("Last Update", live_data.get('timestamp', 'Never')[:19])
col4.metric("Matches Tracked", len(matches))

if auto_refresh:
    import time
    st.write("Auto-refreshing in 5 minutes...")
    time.sleep(300)
    st.rerun()
