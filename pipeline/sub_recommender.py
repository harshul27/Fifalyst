"""Near-real-time substitution & tactic recommender.

Combines:
  - the trained timing model (pipeline/sub_model.py) -> calibrated P(sub next 5')
  - the measured impact prior -> context re-ranking
  - live constraints via the existing SubstitutionTracker (5-sub limit, players
    already withdrawn, bench availability)
  - a momentum read -> tactical suggestions

Feature construction here MUST mirror pipeline/sub_model.FEATURES exactly; the
self-check asserts that, because a silent drift would poison every prediction.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from pipeline.sub_model import FEATURES, MODEL_DIR, load_model

logger = logging.getLogger(__name__)


@dataclass
class PlayerState:
    """A player currently on the pitch."""
    player_id: str
    name: str
    position: str                 # DEF / MID / FWD (GK is never a candidate)
    minutes_played: int
    is_starter: bool = True
    has_card: bool = False
    actions_total: int = 0
    actions_recent: int = 0       # last 15 minutes
    passes: int = 0
    passes_completed: int = 0
    passes_recent: int = 0
    passes_completed_recent: int = 0
    pressures_recent: int = 0
    duels_recent: int = 0
    xg_total: float = 0.0
    avg_x: float = 60.0           # mean action x-position (0-120)


@dataclass
class MatchState:
    """Team-level state at the decision minute."""
    minute: int
    goal_diff: int
    subs_used: int
    team_xg_w: float = 0.0        # rolling 10-minute windows
    opp_xg_w: float = 0.0
    possession_w: float = 0.5
    field_tilt_w: float = 0.0
    shots_w: int = 0
    opp_shots_w: int = 0

    @property
    def momentum(self) -> float:
        return self.team_xg_w - self.opp_xg_w


def build_row(p: PlayerState, m: MatchState) -> Dict[str, float]:
    """One feature row, matching the training schema exactly."""
    mins_on = max(1, p.minutes_played)
    overall_rate = p.actions_total / mins_on
    recent_rate = p.actions_recent / min(15, mins_on)
    return {
        "minute": m.minute,
        "minutes_played": mins_on,
        "is_starter": int(p.is_starter),
        "has_card": int(p.has_card),
        "actions_total": p.actions_total,
        "actions_recent": p.actions_recent,
        "action_rate": overall_rate,
        "recent_rate": recent_rate,
        "rate_decline": (rd := recent_rate / overall_rate if overall_rate > 0 else 1.0),
        "involvement_anomaly": abs(rd - 1.0),
        "pass_acc": p.passes_completed / max(1, p.passes),
        "pass_acc_recent": p.passes_completed_recent / max(1, p.passes_recent),
        "pressures_recent": p.pressures_recent,
        "duels_recent": p.duels_recent,
        "xg_total": p.xg_total,
        "avg_x": p.avg_x,
        "goal_diff": m.goal_diff,
        "subs_used": m.subs_used,
        "team_xg_w": m.team_xg_w,
        "opp_xg_w": m.opp_xg_w,
        "momentum": m.momentum,
        "possession_w": m.possession_w,
        "field_tilt_w": m.field_tilt_w,
        "shots_w": m.shots_w,
        "opp_shots_w": m.opp_shots_w,
        "pos_DEF": int(p.position == "DEF"),
        "pos_MID": int(p.position == "MID"),
        "pos_FWD": int(p.position == "FWD"),
    }


def _reasons(p: PlayerState, m: MatchState, row: Dict[str, float]) -> List[str]:
    """Human-readable drivers. Explanatory, not the model's internals."""
    out = []
    if row["rate_decline"] < 0.6:
        out.append(f"involvement down {(1 - row['rate_decline']) * 100:.0f}% vs own match baseline")
    if p.minutes_played >= 70:
        out.append(f"{p.minutes_played}' on the pitch")
    if p.has_card:
        out.append("booked - dismissal risk")
    if row["pass_acc_recent"] < 0.6 and p.passes_recent >= 5:
        out.append(f"recent pass accuracy {row['pass_acc_recent'] * 100:.0f}%")
    if m.momentum < -0.3:
        out.append("team losing the momentum battle")
    if p.position == "FWD" and p.xg_total < 0.05 and m.minute >= 60 and m.goal_diff <= 0:
        out.append("no attacking threat generated")
    return out or ["routine rotation candidate"]


class SubRecommender:
    """Rank substitution candidates and suggest tactical shifts."""

    def __init__(self, model_name: str = "sub_timing_model"):
        """model_name: 'sub_timing_model' (28 event features, highest accuracy)
        or 'sub_timing_model_live' (13 features obtainable from a live FPL feed).
        """
        self.bundle = None
        self.model_name = model_name
        self.impact_prior = None
        try:
            self.bundle = load_model(model_name)
            missing = set(self.bundle["features"]) - set(FEATURES)
            assert not missing, f"model needs features build_row cannot supply: {missing}"
        except Exception as e:
            logger.warning(f"timing model unavailable ({e}); falling back to heuristic ranking")
        p = MODEL_DIR / "impact_prior.parquet"
        if p.exists():
            self.impact_prior = pd.read_parquet(p)

    # ---- scoring ----
    def _score(self, rows: List[Dict[str, float]]) -> np.ndarray:
        df = pd.DataFrame(rows)
        X = df[self.bundle["features"]] if self.bundle else df[FEATURES]
        if self.bundle is None:
            # transparent fallback: fatigue + minutes, scaled to [0,1]
            h = (1 - X["rate_decline"].clip(0, 2) / 2) * 0.6 + (X["minutes_played"] / 90) * 0.4
            return h.clip(0, 1).values
        return self.bundle["model"].predict_proba(X)[:, 1]

    def _impact_multiplier(self, m: MatchState) -> float:
        """Context prior: how much did subs move momentum in this situation?"""
        if self.impact_prior is None or self.impact_prior.empty:
            return 1.0
        state = "leading" if m.goal_diff > 0 else "level" if m.goal_diff == 0 else "trailing"
        bucket = ("<60" if m.minute < 60 else "60-70" if m.minute < 70
                  else "70-80" if m.minute < 80 else "80+")
        row = self.impact_prior[(self.impact_prior["state"] == state)
                                & (self.impact_prior["minute_bucket"].astype(str) == bucket)]
        if row.empty or row.iloc[0]["n"] < 30:
            return 1.0
        # map mean momentum swing onto a mild multiplier; deliberately bounded
        return float(np.clip(1.0 + row.iloc[0]["momentum_delta"], 0.8, 1.25))

    # ---- public API ----
    def recommend(self, players: List[PlayerState], match: MatchState,
                  bench: Optional[List[PlayerState]] = None,
                  tracker=None, team_key: str = "home",
                  top_k: int = 3) -> List[Dict[str, Any]]:
        """Ranked substitution recommendations, constraint-filtered."""
        if not players:
            return []

        rows = [build_row(p, match) for p in players]
        probs = self._score(rows)
        mult = self._impact_multiplier(match)

        recs = []
        for p, row, prob in zip(players, rows, probs):
            recs.append({
                "off_id": p.player_id, "off": p.name, "position": p.position,
                "minutes_played": p.minutes_played,
                "sub_probability": round(float(prob), 3),
                "priority": round(float(prob * mult), 3),
                "impact_context_multiplier": round(mult, 3),
                "reasons": _reasons(p, match, row),
                "on_id": None, "on": None,
            })

        recs.sort(key=lambda r: r["priority"], reverse=True)

        if bench:
            self._pair_bench(recs, bench, match)

        # Constraints: already-withdrawn players, 5-sub limit. Reuses the
        # existing SubstitutionTracker rather than reimplementing the rules.
        if tracker is not None:
            recs = tracker.filter_recommendations(recs, team_key)
            remaining = tracker.get_available_subs(team_key)
            for r in recs:
                r["subs_remaining"] = remaining
        return recs[:top_k]

    def _pair_bench(self, recs: List[Dict], bench: List[PlayerState], match: MatchState):
        """Attach the freshest same-position bench option to each candidate."""
        used = set()
        for r in recs:
            pool = [b for b in bench if b.position == r["position"] and b.player_id not in used]
            pool = pool or [b for b in bench if b.player_id not in used]
            if not pool:
                continue
            pick = max(pool, key=lambda b: (b.position == r["position"], -b.minutes_played))
            used.add(pick.player_id)
            r["on_id"], r["on"] = pick.player_id, pick.name

    def tactical_advice(self, match: MatchState) -> List[Dict[str, str]]:
        """Momentum-driven shape/approach suggestions.

        ponytail: rule-based, grounded in the observed impact prior rather than
        learned end-to-end. Upgrade path: train on formation-change events once
        a tactics-labelled corpus is available.
        """
        out = []
        m = match
        if m.goal_diff < 0 and m.minute >= 65:
            out.append({"change": "Commit an extra attacker",
                        "why": f"trailing by {abs(m.goal_diff)} with {max(0, 90 - m.minute)}' left"})
        if m.goal_diff < 0 and m.field_tilt_w < 0.25:
            out.append({"change": "Push the line higher / go more direct",
                        "why": f"only {m.field_tilt_w * 100:.0f}% of actions in the final third"})
        if m.goal_diff > 0 and m.momentum < -0.25:
            out.append({"change": "Shore up midfield, drop the block",
                        "why": f"leading but conceding momentum ({m.momentum:+.2f} xG swing)"})
        if m.possession_w < 0.4 and m.goal_diff <= 0:
            out.append({"change": "Add a ball-retention midfielder",
                        "why": f"possession share {m.possession_w * 100:.0f}%"})
        if m.opp_shots_w >= 3:
            out.append({"change": "Reinforce the defensive line",
                        "why": f"{m.opp_shots_w} opposition shots in the last 10'"})
        return out or [{"change": "Hold current shape", "why": "no adverse momentum signal"}]


def demo():
    """Self-check: schema parity, ranking sanity, and constraint filtering."""
    from pipeline.substitution_tracker import SubstitutionTracker

    match = MatchState(minute=70, goal_diff=-1, subs_used=1, team_xg_w=0.2,
                       opp_xg_w=0.7, possession_w=0.38, field_tilt_w=0.18,
                       shots_w=1, opp_shots_w=4)

    tired = PlayerState("p1", "Tired Winger", "FWD", minutes_played=70, actions_total=60,
                        actions_recent=3, passes=40, passes_completed=30,
                        passes_recent=6, passes_completed_recent=3, has_card=True)
    fresh = PlayerState("p2", "Busy Midfielder", "MID", minutes_played=70, actions_total=70,
                        actions_recent=18, passes=50, passes_completed=45,
                        passes_recent=14, passes_completed_recent=13)
    bench = [PlayerState("b1", "Fresh Forward", "FWD", minutes_played=0, is_starter=False)]

    # schema parity is the thing most likely to break silently
    assert set(build_row(tired, match)) == set(FEATURES), "feature schema drift"

    r = SubRecommender()
    recs = r.recommend([tired, fresh], match, bench=bench, top_k=2)
    assert len(recs) == 2 and all(0 <= x["sub_probability"] <= 1 for x in recs)
    assert recs[0]["priority"] >= recs[1]["priority"], "results not ranked"
    assert any(x["on_id"] == "b1" for x in recs), "bench pairing failed"
    assert all(x["reasons"] for x in recs), "no reasons generated"

    # Behavioural check on a driver the data actually supports: more minutes on
    # the pitch => higher withdrawal risk, all else equal. (Deliberately NOT
    # asserting that faded involvement outranks steady involvement -- the corpus
    # shows that relationship is U-shaped and weak, dominated by minutes and
    # position. See README "what the model actually keys on".)
    def clone(pid, mins):
        return PlayerState(pid, pid, "MID", minutes_played=mins, actions_total=int(mins),
                           actions_recent=10, passes=40, passes_completed=32,
                           passes_recent=10, passes_completed_recent=8)

    young, old = r.recommend([clone("fresh", 35), clone("weary", 85)], match, top_k=2)
    assert old["off_id"] == "weary" or young["off_id"] == "weary", "minutes ignored"
    ranked = {x["off_id"]: x["sub_probability"] for x in (young, old)}
    assert ranked["weary"] > ranked["fresh"], "more minutes must raise withdrawal risk"

    # constraint layer: once withdrawn, a player must not be recommended again
    t = SubstitutionTracker(match_id="m1", home_team="A", away_team="B")
    t.record_substitution("home", 71, "p1", "Tired Winger", "b1", "Fresh Forward", "FATIGUE")
    recs2 = r.recommend([fresh], match, bench=[], tracker=t, team_key="home")
    assert all(x["off_id"] != "p1" for x in recs2), "withdrawn player was re-recommended"
    assert recs2[0]["subs_remaining"] == 4

    advice = r.tactical_advice(match)
    assert any("attacker" in a["change"].lower() or "higher" in a["change"].lower()
               for a in advice), "expected attacking advice when trailing"

    print(f"top rec: {recs[0]['off']} -> {recs[0]['on']} "
          f"(p={recs[0]['sub_probability']}, {recs[0]['reasons'][0]})")
    print(f"tactics: {advice[0]['change']} ({advice[0]['why']})")
    print("sub_recommender self-check OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    demo()
