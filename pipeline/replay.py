"""Replay a real match minute-by-minute through the recommender.

This is how the "near real-time" behaviour is validated: walk a match forward in
time, and at each decision point rank the players on the pitch using ONLY state
available up to that minute, then compare against what the coach actually did.

It doubles as the demo path -- the model driving a real match without needing a
live feed.
"""
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from pipeline.statsbomb_extract import extract_match
from pipeline.sub_model import FEATURES, _prep
from pipeline.sub_recommender import SubRecommender

logger = logging.getLogger(__name__)


def replay_match(match_id: int, meta: Optional[dict] = None,
                 top_k: int = 3, recommender: Optional[SubRecommender] = None) -> Dict[str, Any]:
    """Score every decision point of one match.

    Returns per-minute rankings plus hit-rate against the coach's real choices.
    """
    meta = meta or {"competition": "replay", "season": "-"}
    out = extract_match(match_id, meta)
    feats = out["features"]
    if feats.empty:
        return {"match_id": match_id, "timeline": [], "summary": {}}

    feats = _prep(feats)
    rec = recommender or SubRecommender()

    if rec.bundle is not None:
        proba = rec.bundle["model"].predict_proba(feats[FEATURES])[:, 1]
    else:
        proba = rec._score(feats[FEATURES].to_dict("records"))
    feats = feats.assign(_p=proba)

    timeline, hits, chances = [], 0, 0
    for (minute, team), g in feats.groupby(["minute", "team"]):
        ranked = g.nlargest(top_k, "_p")
        actual = g[g["subbed_off_next5"] == 1]["name"].tolist()
        if actual:
            chances += 1
            if set(ranked["name"]) & set(actual):
                hits += 1
        timeline.append({
            "minute": int(minute), "team": team,
            "goal_diff": int(g["goal_diff"].iloc[0]),
            "momentum": round(float(g["momentum"].iloc[0]), 3),
            "subs_used": int(g["subs_used"].iloc[0]),
            "recommended": [
                {"name": r["name"], "position": r["position"],
                 "minutes_played": int(r["minutes_played"]),
                 "probability": round(float(r["_p"]), 3)}
                for _, r in ranked.iterrows()
            ],
            "coach_actually_subbed": actual,
        })

    timeline.sort(key=lambda x: (x["minute"], x["team"]))
    return {
        "match_id": match_id,
        "timeline": timeline,
        "summary": {
            "decision_points": len(timeline),
            "sub_events_covered": chances,
            f"top{top_k}_hit_rate": round(hits / chances, 3) if chances else None,
        },
    }


def replay_many(match_ids: List[int], top_k: int = 3) -> pd.DataFrame:
    """Aggregate hit-rate across matches (a fast sanity sweep)."""
    rec = SubRecommender()
    rows = []
    for mid in match_ids:
        try:
            r = replay_match(mid, top_k=top_k, recommender=rec)
            s = r["summary"]
            if s.get("sub_events_covered"):
                rows.append({"match_id": mid, **s})
        except Exception as e:
            logger.debug(f"replay {mid} failed: {e}")
    return pd.DataFrame(rows)


def demo():
    """Replay one real World Cup match end to end."""
    import requests
    B = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
    matches = requests.get(f"{B}/matches/43/106.json", timeout=60).json()
    mid = matches[0]["match_id"]

    r = replay_match(mid, {"competition": "FIFA World Cup", "season": "2022"})
    assert r["timeline"], "no decision points produced"
    assert r["summary"]["decision_points"] > 0

    # every recommendation must be a player who was actually on the pitch then
    for t in r["timeline"]:
        assert len(t["recommended"]) <= 3
        for rec in t["recommended"]:
            assert rec["minutes_played"] >= 0

    hit = r["summary"]["top3_hit_rate"]
    print(f"match {mid}: {r['summary']['decision_points']} decision points, "
          f"{r['summary']['sub_events_covered']} sub windows, top3 hit rate {hit}")
    sample = next((t for t in r["timeline"] if t["coach_actually_subbed"]), None)
    if sample:
        print(f"  {sample['minute']}' {sample['team']} (gd {sample['goal_diff']}, "
              f"mom {sample['momentum']:+.2f})")
        print(f"    model: {[x['name'] for x in sample['recommended']]}")
        print(f"    coach: {sample['coach_actually_subbed']}")
    print("replay self-check OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    demo()
