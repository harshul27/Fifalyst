"""Aggregate per-gameweek FPL player rows into team attacking / midfield /
defensive profiles + derived tactical indicators.

These are genuine per-GW team stats (summed from the players who featured), so
they reflect what a team actually did that gameweek. FBref adds possession/
passing depth on top when reachable (see fbref_client.enrich_teams).
"""
import numpy as np
import pandas as pd

# Player stats summed across a team for the gameweek.
_SUM = [
    "goals_scored", "assists", "expected_goals", "expected_assists",
    "expected_goal_involvements", "threat", "creativity", "influence",
    "ict_index", "saves", "tackles", "clearances_blocks_interceptions",
    "recoveries", "defensive_contribution", "bonus", "bps",
    "yellow_cards", "red_cards",
]
# Team-shared stats: every player carries the team's value, so take the max
# (a player who lasted 90' holds the full-match team figure).
_MAX = ["goals_conceded", "expected_goals_conceded"]

# Which aggregated columns belong to which tactical bucket (for the dashboard).
BUCKETS = {
    "attacking": ["goals_scored", "expected_goals", "expected_goal_involvements",
                  "threat", "assists"],
    "midfield": ["creativity", "expected_assists", "influence", "recoveries",
                 "ict_index"],
    "defensive": ["goals_conceded", "expected_goals_conceded", "clean_sheet",
                  "tackles", "clearances_blocks_interceptions", "saves"],
}


def aggregate_teams(players: pd.DataFrame) -> pd.DataFrame:
    """One row per team for the gameweek with buckets + tactical indicators."""
    if players.empty:
        return pd.DataFrame()

    grp = players.groupby(["team", "team_short", "team_id"], as_index=False)
    agg = {c: "sum" for c in _SUM if c in players.columns}
    agg.update({c: "max" for c in _MAX if c in players.columns})
    teams = grp.agg(agg)
    teams["gw"] = players["gw"].iloc[0]
    teams["clean_sheet"] = (teams["goals_conceded"] == 0).astype(int)

    # ---- derived tactical indicators (ratios, per GW) ----
    # ponytail: rough heuristics, not a trained model. Upgrade path: fit against
    # match outcomes / FBref possession once multiple GWs are recorded.
    teams["finishing_edge"] = teams["goals_scored"] - teams["expected_goals"]
    teams["defensive_actions"] = (teams.get("tackles", 0)
                                  + teams.get("clearances_blocks_interceptions", 0)
                                  + teams.get("recoveries", 0))
    # threat (vertical/direct) vs creativity (build-up): >1 = direct, <1 = creative.
    # FPL only publishes the ICT family once a gameweek is finalised, so while a
    # GW is in progress these are absent -> NaN, never a fabricated 0.
    ict_available = (teams["threat"].sum() + teams["creativity"].sum()) > 0
    teams["directness"] = (teams["threat"] / (teams["creativity"] + 1.0)
                           if ict_available else np.nan)

    teams["tactical_label"] = _label(teams, ict_available)
    return teams


def _label(teams: pd.DataFrame, ict_available: bool = True) -> pd.Series:
    """Short auto-label per team, relative to that gameweek's league medians.

    Wording is xG-explicit ("high-xG", not "high-scoring") because these are
    chance-quality measures, not the scoreline. The style term is dropped
    entirely when the ICT family has not been published yet.
    """
    atk_med = teams["expected_goals"].median()
    def_med = teams["expected_goals_conceded"].median()
    dir_med = teams["directness"].median() if ict_available else None

    labels = []
    for _, r in teams.iterrows():
        parts = [
            "high-xG" if r["expected_goals"] >= atk_med else "low-xG",
            "solid" if r["expected_goals_conceded"] <= def_med else "leaky",
        ]
        if ict_available and pd.notna(r["directness"]):
            parts.append("direct" if r["directness"] >= dir_med else "possession-based")
        labels.append(", ".join(parts))
    return pd.Series(labels, index=teams.index)


def demo():
    players = pd.DataFrame({
        "gw": [1] * 4,
        "team": ["Arsenal", "Arsenal", "Chelsea", "Chelsea"],
        "team_short": ["ARS", "ARS", "CHE", "CHE"],
        "team_id": [1, 1, 6, 6],
        "goals_scored": [1, 1, 0, 0], "assists": [1, 0, 0, 0],
        "expected_goals": [0.8, 0.5, 0.3, 0.2], "expected_assists": [0.4, 0.1, 0.2, 0.0],
        "expected_goal_involvements": [1.2, 0.6, 0.5, 0.2],
        "threat": [40, 30, 20, 10], "creativity": [20, 10, 25, 5],
        "influence": [30, 20, 15, 10], "ict_index": [9, 6, 6, 2],
        "recoveries": [5, 6, 7, 8], "tackles": [2, 3, 4, 1],
        "clearances_blocks_interceptions": [3, 2, 5, 4], "saves": [0, 0, 3, 0],
        "goals_conceded": [0, 0, 2, 2], "expected_goals_conceded": [0.5, 0.4, 1.6, 1.5],
        "defensive_contribution": [10, 12, 14, 9], "bonus": [3, 1, 0, 0],
        "bps": [30, 20, 10, 8], "yellow_cards": [0, 1, 1, 0], "red_cards": [0, 0, 0, 0],
    })
    t = aggregate_teams(players)
    assert len(t) == 2
    ars = t[t["team"] == "Arsenal"].iloc[0]
    assert ars["goals_scored"] == 2 and ars["clean_sheet"] == 1
    assert ars["goals_conceded"] == 0  # max, not sum
    che = t[t["team"] == "Chelsea"].iloc[0]
    assert che["goals_conceded"] == 2  # shared value via max, not 4
    assert isinstance(ars["tactical_label"], str) and "," in ars["tactical_label"]
    assert pd.notna(ars["directness"])

    # in-progress GW: FPL has not published ICT -> no fabricated directness/style
    blank = players.copy()
    blank[["threat", "creativity"]] = 0
    t2 = aggregate_teams(blank)
    assert t2["directness"].isna().all(), "directness must be NaN without ICT data"
    assert "direct" not in t2.iloc[0]["tactical_label"]
    assert "possession-based" not in t2.iloc[0]["tactical_label"]

    print("team_stats self-check OK |", ars["team"], "->", ars["tactical_label"])


if __name__ == "__main__":
    demo()
