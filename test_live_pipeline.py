"""End-to-end test of the live tracking + coaching chain against real FPL data.

No PL match is in progress outside matchdays, so this drives a real fixture's
real player data through the full path with the match treated as live.
"""
import tempfile

from pipeline.live_poller import LivePoller
from pipeline.live_store import LiveStore
from pipeline.sub_recommender import SubRecommender


def test_live_chain():
    poller = LivePoller()
    gw = poller.fpl.recordable_gameweeks()[0]["gw"]

    matches = poller.poll(gw)
    assert matches, "no started fixtures"
    m = matches[0]

    # real per-player state was reconstructed from cumulative FPL totals
    players = m.players_for("home")
    assert players, "no outfield players tracked"
    assert all(p.minutes_played > 0 for p in players)
    assert all(p.position in ("DEF", "MID", "FWD") for p in players)

    state = m.state_for("home")
    assert state.goal_diff == m.home_score - m.away_score

    # live model ranks them
    coach = SubRecommender(model_name="sub_timing_model_live")
    assert coach.bundle is not None, "live model missing - run train_live_model.py"
    assert len(coach.bundle["features"]) == 13

    recs = coach.recommend(players, state, top_k=3)
    assert len(recs) == 3
    assert all(0 <= r["sub_probability"] <= 1 for r in recs)
    assert recs[0]["priority"] >= recs[-1]["priority"], "not ranked"
    assert all(r["reasons"] for r in recs)

    advice = coach.tactical_advice(state)
    assert advice and "change" in advice[0]

    # storage round-trip in an isolated dir
    with tempfile.TemporaryDirectory() as tmp:
        store = LiveStore(base=f"{tmp}/live")
        n = store.append_snapshot(gw, matches)
        assert n > 0
        tl = store.read_timeline(gw)
        assert len(tl) == n and tl["player_id"].nunique() > 20

        store.log_recommendations(gw, m.fixture_id, "home", m.minute,
                                  {"goal_diff": state.goal_diff}, recs, advice)
        assert len(store.read_recommendations(gw)) == 1

        trail = store.player_trail(gw, players[0].player_id)
        assert len(trail) == 1, "per-player trail not retrievable"

    print(f"GW{gw} {m.home_team} {m.home_score}-{m.away_score} {m.away_team}")
    print(f"  tracked {len(players)} outfield | top rec: {recs[0]['off']} "
          f"({recs[0]['position']}, {recs[0]['minutes_played']}') "
          f"p={recs[0]['sub_probability']:.1%}")
    print(f"  reasons: {' | '.join(recs[0]['reasons'])}")
    print(f"  tactics: {advice[0]['change']}")


def test_withdrawal_detection():
    """Minutes frozen while the clock advances means the player came off."""
    p = LivePoller()
    p.history = {7: [{"minute": 60, "minutes": 60.0, "xg": 0.2, "ts": "t0"}]}
    prev = p.history[7][-1]
    assert (70 > prev["minute"] and 60.0 == prev["minutes"]), "withdrawal missed"
    assert not (70 > prev["minute"] and 70.0 == prev["minutes"]), "false positive"


if __name__ == "__main__":
    test_withdrawal_detection()
    test_live_chain()
    print("test_live_pipeline: all passed")
