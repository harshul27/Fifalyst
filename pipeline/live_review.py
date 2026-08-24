"""Review what the live coach recommended against what actually happened.

Answers three questions the raw poll output cannot:

  1. Which recommendations HIT? For every substitution actually made, was that
     player in our ranked list at the preceding poll, and at what rank?
  2. What did the substitution do to the team's metrics -- xG window, momentum,
     scoreline -- comparing polls before and after?
  3. Does that differ by the POSITION of the player withdrawn?

Everything is reconstructed from what the poller already stored, so it works
during a match and afterwards.
"""
import logging
from typing import Any, Dict, Optional

import pandas as pd

from pipeline.live_poller import rederive_withdrawals
from pipeline.live_store import LiveStore

logger = logging.getLogger(__name__)


def _position_of(tl: pd.DataFrame, name: str) -> str:
    """Withdrawn rows carry no position; recover it from on-pitch history."""
    rows = tl[(tl["name"] == name) & tl["on_pitch"].astype(bool)]
    if rows.empty or rows["position"].isna().all():
        return "?"
    return str(rows["position"].dropna().iloc[-1])


def substitution_hits(gw: int, store: Optional[LiveStore] = None) -> pd.DataFrame:
    """One row per detected substitution, with whether we recommended it."""
    store = store or LiveStore()
    tl, recs = store.read_timeline(gw), store.read_recommendations(gw)
    if tl.empty:
        return pd.DataFrame()

    # Re-derive rather than trusting stored `on_pitch`: snapshots written before
    # the detection fix flagged whole teams at full time.
    off = rederive_withdrawals(tl)
    if off.empty:
        return pd.DataFrame()

    rows = []
    for _, w in off.iterrows():
        w = dict(w)
        rank, prob, reasons, covered = None, None, "", False
        if not recs.empty:
            # Align on the minute the player actually left the pitch, NOT the
            # minute we noticed. Detection lags the substitution by 7-19 minutes,
            # so scoring against the detection poll grades the model on a list
            # built for a decision point that had already passed.
            prior = recs[(recs["fixture_id"] == w["fixture_id"])
                         & (recs["side"] == w["side"])
                         & (recs["minute"] <= w["minute"])].sort_values(["minute", "ts"])
            # covered = we had issued a recommendation by the time of the change.
            # A sub made before polling began can be neither hit nor missed, so
            # it must not count against the hit rate.
            covered = not prior.empty
            if covered:
                latest = prior.iloc[-1]["recommendations"]
                for i, r in enumerate(latest, 1):
                    if r.get("off") == w["name"]:
                        rank, prob = i, r.get("sub_probability")
                        reasons = " | ".join(r.get("reasons", []))
                        break
        rows.append({
            "minute": int(w["minute"]), "team": w["team"], "side": w["side"],
            "player_off": w["name"],
            "position": w.get("position") or _position_of(tl, w["name"]),
            "covered": covered,
            "recommended": rank is not None, "rank": rank,
            "probability": prob, "reasons": reasons,
        })
    return pd.DataFrame(rows).sort_values(["minute", "team"])


def substitution_impact(gw: int, store: Optional[LiveStore] = None,
                        window_polls: int = 3) -> pd.DataFrame:
    """Team metrics before vs after each substitution.

    ponytail: observational -- a coach substitutes *because* of how the game is
    going, so a swing after the change is association, not proof of cause.
    """
    store = store or LiveStore()
    tl = store.read_timeline(gw)
    if tl.empty:
        return pd.DataFrame()

    hits = substitution_hits(gw, store)
    if hits.empty:
        return pd.DataFrame()

    rows = []
    for _, h in hits.iterrows():
        side_rows = (tl[(tl["side"] == h["side"]) & (tl["team"] == h["team"])]
                     .sort_values("ts"))
        if side_rows.empty:
            continue
        # one record per poll for this team
        per_poll = (side_rows.groupby("ts")
                    .agg(minute=("minute", "max"),
                         team_xg_w=("team_xg_w", "max"),
                         opp_xg_w=("opp_xg_w", "max"),
                         goal_diff=("goal_diff", "max"))
                    .reset_index().sort_values("minute"))
        per_poll["momentum"] = per_poll["team_xg_w"] - per_poll["opp_xg_w"]

        before = per_poll[per_poll["minute"] <= h["minute"]].tail(window_polls)
        after = per_poll[per_poll["minute"] > h["minute"]].head(window_polls)
        if before.empty or after.empty:
            rows.append({**_base(h), "polls_after": 0, "note": "not enough data yet"})
            continue

        rows.append({
            **_base(h),
            "polls_after": int(len(after)),
            "momentum_before": round(float(before["momentum"].mean()), 3),
            "momentum_after": round(float(after["momentum"].mean()), 3),
            "momentum_delta": round(float(after["momentum"].mean()
                                          - before["momentum"].mean()), 3),
            "team_xg_before": round(float(before["team_xg_w"].mean()), 3),
            "team_xg_after": round(float(after["team_xg_w"].mean()), 3),
            "goal_diff_before": int(before["goal_diff"].iloc[-1]),
            "goal_diff_after": int(after["goal_diff"].iloc[-1]),
            "note": "",
        })
    return pd.DataFrame(rows)


def _base(h) -> Dict[str, Any]:
    return {"minute": int(h["minute"]), "team": h["team"],
            "player_off": h["player_off"], "position": h["position"],
            "recommended": bool(h["recommended"]), "rank": h["rank"]}


def impact_by_position(gw: int, store: Optional[LiveStore] = None) -> pd.DataFrame:
    """Average metric swing grouped by the position withdrawn."""
    imp = substitution_impact(gw, store)
    if imp.empty or "momentum_delta" not in imp.columns:
        return pd.DataFrame()
    valid = imp[imp["polls_after"] > 0]
    if valid.empty:
        return pd.DataFrame()
    return (valid.groupby("position")
            .agg(subs=("player_off", "size"),
                 momentum_delta=("momentum_delta", "mean"),
                 team_xg_delta=("team_xg_after", "mean"))
            .round(3).reset_index())


def decision_point_hit_rate(gw: int, store: Optional[LiveStore] = None) -> Dict[str, Any]:
    """Hit rate scored the same way the model was validated.

    Training measured: at a decision point where a substitution followed, did the
    top-3 contain ANY player who was withdrawn? Scoring per-player instead
    penalises double substitutions (two players off, only three slots), so this
    is the apples-to-apples comparison against the 58.4% holdout figure.
    """
    hits = substitution_hits(gw, store)
    if hits.empty:
        return {"decision_points": 0}
    cov = hits[hits["covered"].astype(bool)]
    if cov.empty:
        return {"decision_points": 0}
    grp = cov.groupby(["team", "minute"])["recommended"].any()
    return {"decision_points": int(len(grp)),
            "hit": int(grp.sum()),
            "hit_rate": round(float(grp.mean()), 3)}


def report(gw: int, store: Optional[LiveStore] = None) -> Dict[str, Any]:
    """Print the full review. Returns the summary numbers."""
    store = store or LiveStore()
    hits = substitution_hits(gw, store)

    print(f"=== GW{gw} SUBSTITUTION REVIEW ===")
    if hits.empty:
        print("no substitutions detected yet "
              "(detection needs two polls with the clock advancing)")
        return {"substitutions": 0}

    cols = ["minute", "team", "player_off", "position", "covered", "recommended",
            "rank", "probability", "reasons"]
    print(hits[[c for c in cols if c in hits.columns]].to_string(index=False))

    covered = hits[hits["covered"].astype(bool)] if "covered" in hits else hits
    n_all, n_cov = len(hits), len(covered)
    hit = int(covered["recommended"].sum())
    print(f"\nsubstitutions detected: {n_all} "
          f"({n_all - n_cov} happened before we were tracking that side - "
          f"not scorable either way)")
    if n_cov:
        print(f"scored on the {n_cov} we were tracking: {hit} ranked in top 3 "
              f"({hit / n_cov:.0%} hit rate)")
    else:
        print("none occurred while we were tracking, so nothing is scorable")

    imp = substitution_impact(gw, store)
    if not imp.empty:
        print("\n=== IMPACT (team metrics before vs after) ===")
        icols = [c for c in ["minute", "team", "player_off", "position",
                             "momentum_before", "momentum_after", "momentum_delta",
                             "goal_diff_before", "goal_diff_after", "note"]
                 if c in imp.columns]
        print(imp[icols].to_string(index=False))

    bypos = impact_by_position(gw, store)
    if not bypos.empty:
        print("\n=== BY POSITION WITHDRAWN ===")
        print(bypos.to_string(index=False))
        print("\nnote: observational -- coaches substitute because of how the "
              "game is going, so these swings are association, not cause.")

    return {"substitutions": n_all, "scorable": n_cov, "recommended": hit,
            "hit_rate": round(hit / n_cov, 3) if n_cov else None}


def demo():
    """Self-check on a synthetic store, using a realistic poll sequence."""
    import tempfile
    from pipeline.sub_recommender import MatchState, PlayerState

    class M:
        fixture_id = 1
        home_team, away_team = "A", "B"
        away_players, away_subs_off = [], []
        home_subs_off = []

        def __init__(self, minute, alpha_minutes, txg, oxg):
            self.minute = minute
            self.home_players = [PlayerState("1", "Alpha", "MID", alpha_minutes),
                                 PlayerState("2", "Beta", "FWD", minute)]
            self.home_state = MatchState(minute=minute, goal_diff=0, subs_used=0,
                                         team_xg_w=txg, opp_xg_w=oxg)
            self.away_state = MatchState(minute=minute, goal_diff=0, subs_used=0)

        def players_for(self, s):
            return self.home_players if s == "home" else self.away_players

        def state_for(self, s):
            return self.home_state if s == "home" else self.away_state

    with tempfile.TemporaryDirectory() as tmp:
        st = LiveStore(base=f"{tmp}/live")
        # Alpha frozen at 60' while the clock runs on; Beta keeps accruing.
        for minute, txg, oxg in [(60, 0.1, 0.4), (65, 0.1, 0.4),
                                 (70, 0.5, 0.1), (75, 0.5, 0.1)]:
            st.append_snapshot(1, [M(minute, 60, txg, oxg)])
            st.log_recommendations(1, 1, "home", minute, {"goal_diff": 0},
                                   [{"off": "Alpha", "sub_probability": 0.4,
                                     "reasons": ["60' on the pitch"]}])

        h = substitution_hits(1, st)
        assert len(h) == 1, f"expected exactly Alpha withdrawn, got {len(h)}"
        a = h.iloc[0]
        assert a["player_off"] == "Alpha" and a["position"] == "MID"
        assert a["minute"] == 60, f"sub minute should be the frozen value, got {a['minute']}"
        assert bool(a["recommended"]) and a["rank"] == 1 and bool(a["covered"])

        # Beta accrued minutes throughout and must never be flagged
        assert "Beta" not in set(h["player_off"]), "false positive on an active player"

        imp = substitution_impact(1, st)
        assert not imp.empty and "momentum_delta" in imp.columns

        r = report(1, st)
        assert r["substitutions"] == 1 and r["recommended"] == 1

        # A change that predates every recommendation is not scorable. Scoring
        # used to align on the detection poll, which always has a prior set, so
        # subs made before tracking began were counted as misses.
        st2 = LiveStore(base=f"{tmp}/live2")
        for minute, txg, oxg in [(70, 0.1, 0.4), (75, 0.1, 0.4),
                                 (80, 0.5, 0.1), (85, 0.5, 0.1)]:
            st2.append_snapshot(1, [M(minute, 66, txg, oxg)])
            st2.log_recommendations(1, 1, "home", minute, {"goal_diff": 0},
                                    [{"off": "Alpha", "sub_probability": 0.4,
                                      "reasons": []}])
        h2 = substitution_hits(1, st2)
        assert not h2.empty, "Alpha frozen at 66' should still be detected"
        assert int(h2.iloc[0]["minute"]) == 66
        assert not bool(h2.iloc[0]["covered"]), \
            "a sub at 66' predates the first recommendation at 70' - not scorable"
    print("live_review self-check OK")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if "--demo" in sys.argv:
        demo()
    else:
        gw = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
        report(gw)
