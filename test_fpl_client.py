"""Network-backed smoke test for the FPL data path.

Run: python test_fpl_client.py   (or: pytest test_fpl_client.py)
"""
from pipeline.fpl_client import FPLClient
from pipeline.team_stats import aggregate_teams
import pandas as pd


def test_bootstrap_has_20_teams():
    assert len(FPLClient().teams()) == 20


def test_gameweek_stats_are_numeric_and_populated():
    c = FPLClient()
    recordable = c.recordable_gameweeks()
    assert recordable, "no gameweek has been played yet"
    gw = recordable[0]["gw"]
    rows = c.get_gw_player_stats(gw)
    assert rows, f"GW{gw} returned no players"
    r = rows[0]
    assert r["minutes"] > 0
    assert isinstance(r["expected_goals"], float), "xG must be coerced from FPL's string"
    assert r["team"] and r["position"]


def test_team_aggregation_matches_player_rows():
    c = FPLClient()
    gw = c.recordable_gameweeks()[0]["gw"]
    players = pd.DataFrame(c.get_gw_player_stats(gw))
    teams = aggregate_teams(players)
    assert not teams.empty
    # goals summed per team must equal total goals across all players
    assert teams["goals_scored"].sum() == players["goals_scored"].sum()
    # a team's conceded figure is shared, never summed across its players
    assert teams["goals_conceded"].max() <= 15


if __name__ == "__main__":
    test_bootstrap_has_20_teams()
    test_gameweek_stats_are_numeric_and_populated()
    test_team_aggregation_matches_player_rows()
    print("test_fpl_client: all passed")
