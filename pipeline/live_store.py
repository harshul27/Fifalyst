"""Persistence for live in-match tracking.

Two things are recorded, because they answer different questions later:

  timeline.parquet      one row per (poll, fixture, player) -- the per-player
                        in-match trail: minutes, xG, on/off pitch, booking
  recommendations.jsonl one line per recommendation set, with the match state
                        that produced it

Keeping the recommendations means accuracy can be evaluated against what the
real coach subsequently did, rather than only against historical StatsBomb data.

Layout:
    data/live/gw{n}/timeline.parquet
    data/live/gw{n}/recommendations.jsonl
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class LiveStore:
    def __init__(self, base: str = "data/live"):
        self.base = Path(base)

    def _dir(self, gw: int) -> Path:
        d = self.base / f"gw{gw}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---- per-player timeline ----
    def append_snapshot(self, gw: int, matches: List[Any]) -> int:
        """Append one poll's worth of per-player rows."""
        ts = datetime.now(timezone.utc).isoformat()
        rows = []
        for m in matches:
            for side in ("home", "away"):
                on_pitch = m.players_for(side)
                withdrawn = m.home_subs_off if side == "home" else m.away_subs_off
                state = m.state_for(side)
                for p in on_pitch:
                    rows.append({
                        "ts": ts, "gw": gw, "fixture_id": m.fixture_id,
                        "minute": m.minute, "side": side,
                        "team": m.home_team if side == "home" else m.away_team,
                        "player_id": p.player_id, "name": p.name,
                        "position": p.position, "minutes_played": p.minutes_played,
                        "is_starter": p.is_starter, "has_card": p.has_card,
                        "xg_total": p.xg_total, "on_pitch": True,
                        "goal_diff": state.goal_diff, "subs_used": state.subs_used,
                        "team_xg_w": state.team_xg_w, "opp_xg_w": state.opp_xg_w,
                    })
                for name in withdrawn:
                    rows.append({
                        "ts": ts, "gw": gw, "fixture_id": m.fixture_id,
                        "minute": m.minute, "side": side,
                        "team": m.home_team if side == "home" else m.away_team,
                        "player_id": None, "name": name, "position": None,
                        "minutes_played": None, "is_starter": None, "has_card": None,
                        "xg_total": None, "on_pitch": False,
                        "goal_diff": state.goal_diff, "subs_used": state.subs_used,
                        "team_xg_w": state.team_xg_w, "opp_xg_w": state.opp_xg_w,
                    })
        if not rows:
            return 0

        df = pd.DataFrame(rows)
        path = self._dir(gw) / "timeline.parquet"
        if path.exists():
            df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
        df.to_parquet(path, index=False)
        logger.info(f"✓ timeline: +{len(rows)} rows (total {len(df)})")
        return len(rows)

    def read_timeline(self, gw: int) -> pd.DataFrame:
        path = self.base / f"gw{gw}" / "timeline.parquet"
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()

    def player_trail(self, gw: int, player_id: str) -> pd.DataFrame:
        """Everything recorded for one player this gameweek, in time order."""
        df = self.read_timeline(gw)
        if df.empty:
            return df
        return df[df["player_id"] == str(player_id)].sort_values("ts")

    # ---- recommendations ----
    def log_recommendations(self, gw: int, fixture_id: int, side: str,
                            minute: int, state: Dict[str, Any],
                            recs: List[Dict[str, Any]],
                            advice: Optional[List[Dict[str, str]]] = None):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "gw": gw, "fixture_id": fixture_id, "side": side, "minute": minute,
            "state": state, "recommendations": recs, "tactical_advice": advice or [],
        }
        path = self._dir(gw) / "recommendations.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def read_recommendations(self, gw: int) -> pd.DataFrame:
        path = self.base / f"gw{gw}" / "recommendations.jsonl"
        if not path.exists():
            return pd.DataFrame()
        with open(path, encoding="utf-8") as f:
            return pd.DataFrame([json.loads(line) for line in f if line.strip()])

    # ---- evaluation ----
    def evaluate(self, gw: int) -> Dict[str, Any]:
        """Did the coach's real substitutions appear in our recommendations?

        Compares each logged recommendation set against players observed to be
        withdrawn later in the same fixture.
        """
        recs, tl = self.read_recommendations(gw), self.read_timeline(gw)
        if recs.empty or tl.empty:
            return {"evaluated": 0}

        withdrawn = (tl[~tl["on_pitch"].astype(bool)]
                     .groupby(["fixture_id", "side"])["name"].apply(set).to_dict())
        hits = total = 0
        for _, r in recs.iterrows():
            actual = withdrawn.get((r["fixture_id"], r["side"]), set())
            if not actual:
                continue
            total += 1
            named = {x.get("off") for x in r["recommendations"]}
            if named & actual:
                hits += 1
        return {"evaluated": total,
                "hit_rate": round(hits / total, 3) if total else None,
                "recommendation_sets": int(len(recs))}


def demo():
    import tempfile
    from pipeline.sub_recommender import MatchState, PlayerState

    class FakeMatch:
        fixture_id = 1
        minute = 70
        home_team, away_team = "A", "B"
        home_subs_off, away_subs_off = ["Withdrawn Guy"], []
        home_players = [PlayerState("1", "Still On", "MID", 70)]
        away_players = [PlayerState("2", "Other", "FWD", 70)]
        home_state = MatchState(minute=70, goal_diff=-1, subs_used=1)
        away_state = MatchState(minute=70, goal_diff=1, subs_used=0)

        def players_for(self, s):
            return self.home_players if s == "home" else self.away_players

        def state_for(self, s):
            return self.home_state if s == "home" else self.away_state

    with tempfile.TemporaryDirectory() as tmp:
        s = LiveStore(base=f"{tmp}/live")
        n = s.append_snapshot(1, [FakeMatch()])
        assert n == 3, f"expected 2 on-pitch + 1 withdrawn, got {n}"

        tl = s.read_timeline(1)
        assert len(tl) == 3 and (~tl["on_pitch"].astype(bool)).sum() == 1
        assert len(s.player_trail(1, "1")) == 1

        # appending again must accumulate, not overwrite
        s.append_snapshot(1, [FakeMatch()])
        assert len(s.read_timeline(1)) == 6, "snapshots must accumulate"

        s.log_recommendations(1, 1, "home", 70, {"goal_diff": -1},
                              [{"off": "Withdrawn Guy", "sub_probability": 0.3}])
        assert len(s.read_recommendations(1)) == 1
        ev = s.evaluate(1)
        assert ev["evaluated"] == 1 and ev["hit_rate"] == 1.0, ev
    print("live_store self-check OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    demo()
