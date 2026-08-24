"""Premier League 2026/27 - Season Stats Dashboard.

Browse recorded gameweek data: per-player stats by category and per-team
attacking / midfield / defensive profiles with tactical indicators.
Data is recorded by `python record.py`.
"""
import pandas as pd
import streamlit as st

from orchestrator import get_orchestrator
from pipeline.physical_adapter import PHYSICAL_COLS

st.set_page_config(page_title="Premier League 2026/27 - Season Stats",
                   layout="wide", initial_sidebar_state="expanded")

# Player stat categories -> columns (only those present are shown).
PLAYER_CATEGORIES = {
    "Attacking": ["goals_scored", "assists", "expected_goals",
                  "expected_goal_involvements", "threat"],
    "Playmaking": ["assists", "expected_assists", "creativity", "influence"],
    "Defending": ["tackles", "clearances_blocks_interceptions", "recoveries",
                  "defensive_contribution", "clean_sheets", "goals_conceded",
                  "expected_goals_conceded", "saves", "penalties_saved"],
    "Discipline": ["yellow_cards", "red_cards", "own_goals", "penalties_missed"],
    "Physical": PHYSICAL_COLS,
    "Overall": ["minutes", "starts", "total_points", "bonus", "bps", "ict_index"],
}
ID_COLS = ["web_name", "team_short", "position"]

TEAM_BUCKETS = {
    "Attacking": ["goals_scored", "assists", "expected_goals",
                  "expected_goal_involvements", "threat", "finishing_edge"],
    "Midfield": ["expected_assists", "creativity", "influence", "recoveries",
                 "ict_index", "possession_pct", "pass_completion_pct",
                 "progressive_passes"],
    "Defensive": ["goals_conceded", "expected_goals_conceded", "clean_sheet",
                  "tackles", "clearances_blocks_interceptions", "saves",
                  "defensive_actions"],
}

orch = get_orchestrator()
status = orch.status()
recorded = status["recorded_gameweeks"]

# ==================== SIDEBAR ====================
st.sidebar.title("Premier League 2026/27")
st.sidebar.caption("Season stats recorder - Gameweeks 1-38")

if not recorded:
    st.sidebar.error("No gameweeks recorded yet.")
    st.title("Premier League 2026/27 - Season Stats")
    st.warning("No data recorded yet. Run `python record.py` to record played gameweeks.")
    st.stop()

view = st.sidebar.radio("View", ["Single gameweek", "Season to date"])
gw = None
if view == "Single gameweek":
    gw = st.sidebar.selectbox("Gameweek", recorded, index=len(recorded) - 1,
                              format_func=lambda g: f"GW{g}")

st.sidebar.divider()
st.sidebar.metric("Gameweeks recorded", f"{len(recorded)} / 38")
final = set(status["final_gameweeks"])
st.sidebar.caption(
    "**Status per GW:**\n\n" +
    "\n".join(f"- GW{g}: {'final' if g in final else 'in progress'}" for g in recorded)
)
if st.sidebar.button("Reload data", width="stretch"):
    st.cache_data.clear()
    st.rerun()


# ==================== LOAD ====================
@st.cache_data(ttl=300)
def load(view: str, gw):
    if view == "Single gameweek":
        return orch.gameweek_view(gw)
    return orch.season_view("players"), orch.season_view("teams")


players, teams = load(view, gw)
if players is None or players.empty:
    st.error("No data for this selection.")
    st.stop()


def aggregate_season(df: pd.DataFrame, keys: list) -> pd.DataFrame:
    """Sum numeric stats across gameweeks for a season-to-date view."""
    num = df.select_dtypes("number").columns.difference(["gw", "team_id", "player_id"])
    out = df.groupby(keys, as_index=False)[list(num)].sum()
    out["GWs"] = df.groupby(keys).size().values
    return out


title_suffix = f"Gameweek {gw}" if gw else f"Season to date ({len(recorded)} GW)"
st.title("Premier League 2026/27")
st.caption(f"**{title_suffix}** - player and team statistics")

if view == "Season to date":
    players_view = aggregate_season(players, ["web_name", "team_short", "position"])
    teams_view = aggregate_season(teams, ["team", "team_short"])
else:
    players_view, teams_view = players, teams

c1, c2, c3, c4 = st.columns(4)
c1.metric("Players", len(players_view))
c2.metric("Teams", len(teams_view))
c3.metric("Goals", int(players_view["goals_scored"].sum()))
c4.metric("xG", f"{players_view['expected_goals'].sum():.1f}")

tab_players, tab_teams, tab_coach, tab_live = st.tabs(
    ["Players", "Teams & Tactics", "Match Coach", "Live Tracking"])

# ==================== PLAYERS ====================
with tab_players:
    teams_list = sorted(players_view["team_short"].unique())
    fcol1, fcol2 = st.columns([2, 1])
    picked = fcol1.multiselect("Filter by team", teams_list, default=[])
    positions = fcol2.multiselect("Position", ["GKP", "DEF", "MID", "FWD"], default=[])

    pv = players_view
    if picked:
        pv = pv[pv["team_short"].isin(picked)]
    if positions:
        pv = pv[pv["position"].isin(positions)]

    cat_tabs = st.tabs(list(PLAYER_CATEGORIES))
    for tab, (cat, cols) in zip(cat_tabs, PLAYER_CATEGORIES.items()):
        with tab:
            present = [c for c in cols if c in pv.columns]
            if cat == "Physical" and (not present or pv[present].isna().all().all()):
                st.info(
                    "**Physical statistics are not yet connected.**\n\n"
                    "Distance covered, sprints, high-speed running and top speed come "
                    "from tracking providers with no free public feed, so these columns "
                    "are intentionally empty rather than filled with estimates.\n\n"
                    "To populate them, subclass `PhysicalStatsAdapter` in "
                    "`pipeline/physical_adapter.py` with a real data source."
                )
                continue
            show = [c for c in ID_COLS if c in pv.columns] + present
            sort_by = present[0] if present else show[0]
            st.dataframe(pv[show].sort_values(sort_by, ascending=False),
                         width="stretch", hide_index=True, height=520)

# ==================== TEAMS ====================
with tab_teams:
    if teams_view.empty:
        st.info("No team data for this selection.")
    else:
        sort_col = "expected_goals" if "expected_goals" in teams_view.columns else "goals_scored"
        tv = teams_view.sort_values(sort_col, ascending=False)

        st.subheader("League overview")
        overview = [c for c in ["team_short", "goals_scored", "expected_goals",
                                "goals_conceded", "expected_goals_conceded",
                                "clean_sheet", "finishing_edge", "tactical_label"]
                    if c in tv.columns]
        st.dataframe(tv[overview], width="stretch", hide_index=True)

        st.divider()
        st.subheader("Team tactical profiles")
        name_col = "team" if "team" in tv.columns else "team_short"
        for _, row in tv.iterrows():
            label = row.get("tactical_label", "")
            header = f"**{row[name_col]}**"
            if isinstance(label, str) and label:
                header += f" - _{label}_"
            with st.container(border=True):
                st.markdown(header)
                bcols = st.columns(3)
                for bcol, (bucket, cols) in zip(bcols, TEAM_BUCKETS.items()):
                    with bcol:
                        st.caption(bucket)
                        for c in cols:
                            if c in tv.columns and pd.notna(row[c]):
                                v = row[c]
                                pretty = c.replace("_", " ")
                                st.write(f"{pretty}: **{v:.2f}**" if isinstance(v, float)
                                         else f"{pretty}: **{v}**")

st.divider()
st.caption("Source: FPL API (per-gameweek), FBref tactical enrichment optional. "
           f"Last updated {status['meta'].get('updated_at', 'never')}")


# ==================== MATCH COACH ====================
with tab_coach:
    import json
    from pathlib import Path
    from pipeline.sub_recommender import MatchState, PlayerState

    report_path = Path("models/sub_timing_model_report.json")
    if report_path.exists():
        rep = json.loads(report_path.read_text())
        h = rep["holdout"]
        st.subheader("Model report card")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Holdout PR-AUC", f"{h['pr_auc']:.3f}",
                  help=f"base rate {h['base_rate']:.3f} - PR-AUC is the honest metric here")
        m2.metric("Holdout ROC-AUC", f"{h['roc_auc']:.3f}")
        m3.metric("Top-1 hit rate", f"{h['precision_at_1']:.1%}",
                  help="the actually-substituted player ranked first")
        m4.metric("Top-3 hit rate", f"{h['precision_at_3']:.1%}")
        st.caption(
            f"Held out: **{h['competition']}** ({h['n_matches']} matches, "
            f"{h['n_rows']:,} decision rows) - never seen in training. "
            f"Trained on {rep['n_train_matches']:,} matches. "
            f"Best heuristic baseline PR-AUC: "
            f"{max(v for k, v in rep['baselines_on_holdout'].items() if k != 'random'):.3f}"
        )
    else:
        st.warning("No trained model yet. Run `python train_sub_model.py`.")

    st.divider()
    st.subheader("Live match state")

    c1, c2, c3 = st.columns(3)
    minute = c1.slider("Minute", 30, 90, 70, 5)
    goal_diff = c2.slider("Goal difference", -3, 3, -1)
    subs_used = c3.slider("Subs already used", 0, 5, 1)
    c4, c5, c6 = st.columns(3)
    team_xg = c4.slider("Our xG (last 10')", 0.0, 2.0, 0.2, 0.05)
    opp_xg = c5.slider("Opponent xG (last 10')", 0.0, 2.0, 0.7, 0.05)
    possession = c6.slider("Possession share (last 10')", 0.0, 1.0, 0.38, 0.02)
    c7, c8 = st.columns(2)
    tilt = c7.slider("Final-third action share", 0.0, 1.0, 0.18, 0.02)
    opp_shots = c8.slider("Opponent shots (last 10')", 0, 10, 4)

    match = MatchState(minute=minute, goal_diff=goal_diff, subs_used=subs_used,
                       team_xg_w=team_xg, opp_xg_w=opp_xg, possession_w=possession,
                       field_tilt_w=tilt, shots_w=0, opp_shots_w=opp_shots)

    st.subheader("Players on the pitch")
    st.caption("Edit the table - minutes played, recent involvement and card status drive the model.")
    default = pd.DataFrame([
        {"name": "Winger", "position": "FWD", "minutes_played": 70, "actions_total": 55,
         "actions_recent": 3, "passes": 35, "passes_completed": 24, "passes_recent": 6,
         "passes_completed_recent": 3, "has_card": True, "xg_total": 0.02},
        {"name": "Midfielder", "position": "MID", "minutes_played": 70, "actions_total": 72,
         "actions_recent": 17, "passes": 55, "passes_completed": 49, "passes_recent": 14,
         "passes_completed_recent": 13, "has_card": False, "xg_total": 0.10},
        {"name": "Full-back", "position": "DEF", "minutes_played": 70, "actions_total": 48,
         "actions_recent": 6, "passes": 38, "passes_completed": 30, "passes_recent": 8,
         "passes_completed_recent": 5, "has_card": False, "xg_total": 0.0},
    ])
    edited = st.data_editor(default, num_rows="dynamic", width="stretch", hide_index=True)

    bench_default = pd.DataFrame([
        {"name": "Fresh Forward", "position": "FWD"},
        {"name": "Fresh Midfielder", "position": "MID"},
    ])
    bench_edit = st.data_editor(bench_default, num_rows="dynamic", width="stretch",
                                hide_index=True, key="bench")

    def to_players(df, on_pitch=True):
        out = []
        for i, r in df.iterrows():
            out.append(PlayerState(
                player_id=f"{'p' if on_pitch else 'b'}{i}", name=str(r.get("name", "")),
                position=str(r.get("position", "MID")),
                minutes_played=int(r.get("minutes_played", 0) or 0),
                is_starter=on_pitch,
                has_card=bool(r.get("has_card", False)),
                actions_total=int(r.get("actions_total", 0) or 0),
                actions_recent=int(r.get("actions_recent", 0) or 0),
                passes=int(r.get("passes", 0) or 0),
                passes_completed=int(r.get("passes_completed", 0) or 0),
                passes_recent=int(r.get("passes_recent", 0) or 0),
                passes_completed_recent=int(r.get("passes_completed_recent", 0) or 0),
                xg_total=float(r.get("xg_total", 0.0) or 0.0),
            ))
        return out

    if st.button("Get recommendations", type="primary"):
        recs = orch.recommend_subs(to_players(edited), match,
                                   bench=to_players(bench_edit, on_pitch=False), top_k=3)
        st.subheader("Substitution recommendations")
        if not recs:
            st.info("No candidates.")
        for i, r in enumerate(recs, 1):
            with st.container(border=True):
                on = f" -> **{r['on']}**" if r.get("on") else ""
                st.markdown(f"**#{i} {r['off']}** ({r['position']}, {r['minutes_played']}'){on}")
                st.progress(min(1.0, r["sub_probability"]),
                            text=f"substitution likelihood {r['sub_probability']:.1%}")
                st.caption(" - ".join(r["reasons"]))

        st.subheader("Tactical adjustments")
        for a in orch.tactical_advice(match):
            st.markdown(f"- **{a['change']}** — {a['why']}")

    st.caption(
        "The timing model learns from real coach decisions in StatsBomb data. "
        "It ranks who is most likely to come off given fatigue, booking risk, fading "
        "involvement, game state and momentum — it does not claim those decisions "
        "were optimal. The impact layer re-ranks using measured post-substitution "
        "momentum swings, which are observational and confounded."
    )


# ==================== LIVE TRACKING ====================
with tab_live:
    from pipeline.live_store import LiveStore
    from pipeline.live_poller import LivePoller
    from pipeline.sub_recommender import SubRecommender

    store = LiveStore()
    live_gw = recorded[-1] if recorded else 1

    st.subheader("Live in-match tracking")
    st.caption(
        "Polls the FPL API and diffs consecutive snapshots to reconstruct "
        "in-match state. Uses the live model (13 FPL-obtainable features, "
        "~58% top-3 hit rate) rather than the full event-data model (~68%)."
    )

    cpoll, cgw = st.columns([1, 3])
    gw_live = cgw.selectbox("Gameweek", list(range(1, 39)),
                            index=live_gw - 1, key="live_gw")

    if cpoll.button("Poll now", type="primary"):
        with st.spinner("polling FPL..."):
            try:
                poller = LivePoller()
                matches = poller.poll(gw_live)
                store.append_snapshot(gw_live, matches)
                st.session_state["live_matches"] = matches
            except Exception as e:
                st.error(f"poll failed: {e}")

    matches = st.session_state.get("live_matches", [])
    in_prog = [m for m in matches if not m.finished]

    if matches:
        st.success(f"{len(matches)} started fixtures, {len(in_prog)} in progress")

    if in_prog:
        coach = SubRecommender(model_name="sub_timing_model_live")
        if coach.bundle is None:
            st.warning("Live model not found - run `python train_live_model.py`. "
                       "Falling back to heuristic ranking.")
        for m in in_prog:
            with st.container(border=True):
                st.markdown(f"**{m.home_team} {m.home_score}-{m.away_score} "
                            f"{m.away_team}** - {m.minute}'")
                for side in ("home", "away"):
                    players = m.players_for(side)
                    if not players:
                        continue
                    state = m.state_for(side)
                    recs = coach.recommend(players, state, top_k=3)
                    store.log_recommendations(
                        gw_live, m.fixture_id, side, m.minute,
                        {"goal_diff": state.goal_diff, "subs_used": state.subs_used},
                        recs, coach.tactical_advice(state))
                    team = m.home_team if side == "home" else m.away_team
                    st.markdown(f"_{team}_ - momentum {state.momentum:+.2f}, "
                                f"{state.subs_used} subs used")
                    for i, r in enumerate(recs, 1):
                        on = f" -> {r['on']}" if r.get("on") else ""
                        st.write(f"{i}. **{r['off']}** ({r['position']}, "
                                 f"{r['minutes_played']}'){on} - "
                                 f"{r['sub_probability']:.1%}")
                        st.caption(" | ".join(r["reasons"]))
    elif matches:
        st.info("No matches currently in progress. Recommendations appear here "
                "during live fixtures.")

    st.divider()
    st.subheader("Recorded trail")
    tl = store.read_timeline(gw_live)
    logged = store.read_recommendations(gw_live)

    t1, t2, t3 = st.columns(3)
    t1.metric("Timeline rows", f"{len(tl):,}")
    t2.metric("Players tracked", tl["player_id"].nunique() if not tl.empty else 0)
    t3.metric("Recommendation sets", len(logged))

    if not tl.empty:
        with st.expander("Per-player trail"):
            names = sorted(tl["name"].dropna().unique())
            pick = st.selectbox("Player", names, key="trail_player")
            trail = tl[tl["name"] == pick].sort_values("ts")
            cols = [c for c in ["ts", "minute", "minutes_played", "xg_total",
                                "on_pitch", "goal_diff", "subs_used"] if c in trail.columns]
            st.dataframe(trail[cols], width="stretch", hide_index=True)

    st.divider()
    st.subheader("Substitution review")
    st.caption("Every substitution actually made, whether we ranked it, and what "
               "the team's metrics did afterwards.")

    from pipeline.live_review import (substitution_hits, substitution_impact,
                                      impact_by_position)

    hits = substitution_hits(gw_live, store)
    if hits.empty:
        st.info("No substitutions detected yet. Detection needs two polls with "
                "the match clock advancing between them.")
    else:
        n, hit = len(hits), int(hits["recommended"].sum())
        h1, h2, h3 = st.columns(3)
        h1.metric("Substitutions seen", n)
        h2.metric("We ranked in top 3", hit)
        h3.metric("Hit rate", f"{hit / n:.0%}" if n else "-",
                  help="Small samples are noisy - the validated figure is 58.4% "
                       "on 418 held-out matches.")

        show = [c for c in ["minute", "team", "player_off", "position",
                            "recommended", "rank", "probability", "reasons"]
                if c in hits.columns]
        st.dataframe(hits[show], width="stretch", hide_index=True)

        imp = substitution_impact(gw_live, store)
        if not imp.empty and "momentum_delta" in imp.columns:
            st.markdown("**Impact — team metrics before vs after**")
            icols = [c for c in ["minute", "team", "player_off", "position",
                                 "momentum_before", "momentum_after",
                                 "momentum_delta", "goal_diff_before",
                                 "goal_diff_after", "note"] if c in imp.columns]
            st.dataframe(imp[icols], width="stretch", hide_index=True)

            bypos = impact_by_position(gw_live, store)
            if not bypos.empty:
                st.markdown("**By position withdrawn**")
                st.dataframe(bypos, width="stretch", hide_index=True)
                if bypos["subs"].max() < 3:
                    st.warning(
                        "Too few substitutions to read anything from this. When "
                        "two players come off together the team-level swing is "
                        "identical for both, so it cannot be attributed to either "
                        "position. Meaningful only across many single changes.")
            st.caption(
                "Observational: a coach substitutes *because* of how the game is "
                "going, so a swing after a change is association, not cause."
            )

    st.caption("Substitution detection needs at least two polls - on a cold "
               "start no player can yet be known to have been withdrawn.")
