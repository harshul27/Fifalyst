"""Extract substitution-model training features from StatsBomb open data.

Streams each match's event feed, derives per-(player, decision-minute) rows, and
discards the raw JSON -- so the full corpus costs bandwidth, not disk.

Two outputs per competition-season shard:
  features/*.parquet  one row per (match, player on pitch, decision minute)
                      label: subbed_off_next5
  subs/*.parquet      one row per actual substitution, with measured post-sub
                      impact (used by the impact-weighting layer)

Resumable: shards already on disk are skipped.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
OUT = Path("data/statsbomb")

# Decision grid: evaluate every 5th minute of the window where subs actually happen.
GRID = list(range(30, 91, 5))
LABEL_WINDOW = 5      # subbed off within the next N minutes
FORM_WINDOW = 15      # rolling window for player form / fatigue proxies
MOM_WINDOW = 10       # rolling window for team momentum
IMPACT_WINDOW = 15    # post-substitution measurement window

POS_GROUP = {
    "Goalkeeper": "GK",
    "Back": "DEF", "Centre Back": "DEF", "Left Back": "DEF", "Right Back": "DEF",
    "Wing Back": "DEF",
    "Midfield": "MID", "Defensive Midfield": "MID", "Central Midfield": "MID",
    "Attacking Midfield": "MID", "Wing": "MID",
    "Forward": "FWD", "Striker": "FWD",
}


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=32))
    s.headers.update({"User-Agent": "pl-sub-model/1.0"})
    return s


SESSION = _session()


def _get(url: str) -> Any:
    r = SESSION.get(url, timeout=60)
    r.raise_for_status()
    return r.json()


def _pos_group(name: Optional[str]) -> str:
    if not name:
        return "MID"
    for key, grp in POS_GROUP.items():
        if key in name:
            return grp
    return "MID"


def _parse_events(events: List[dict]) -> Dict[str, Any]:
    """Flatten the event feed into the arrays the feature builder needs."""
    lineups, subs, acts = {}, [], []
    cards: Dict[int, int] = {}

    for e in events:
        etype = e.get("type", {}).get("name", "")
        team = e.get("team", {}).get("name", "")
        minute = e.get("minute", 0)

        if etype == "Starting XI":
            for p in e.get("tactics", {}).get("lineup", []):
                pid = p.get("player", {}).get("id")
                lineups[pid] = {
                    "player_id": pid,
                    "name": p.get("player", {}).get("name", ""),
                    "team": team,
                    "position": _pos_group(p.get("position", {}).get("name")),
                    "on": 0, "off": None, "starter": 1,
                }
            continue

        if etype == "Substitution":
            off_id = e.get("player", {}).get("id")
            rep = e.get("substitution", {}).get("replacement", {})
            if off_id in lineups:
                lineups[off_id]["off"] = minute
            rep_id = rep.get("id")
            if rep_id:
                lineups[rep_id] = {
                    "player_id": rep_id, "name": rep.get("name", ""), "team": team,
                    "position": lineups.get(off_id, {}).get("position", "MID"),
                    "on": minute, "off": None, "starter": 0,
                }
            subs.append({"minute": minute, "team": team,
                         "player_off_id": off_id, "player_on_id": rep_id})
            continue

        # yellow/red cards arrive on several event types
        card = ((e.get("foul_committed") or {}).get("card")
                or (e.get("bad_behaviour") or {}).get("card"))
        if card:
            pid = e.get("player", {}).get("id")
            if pid:
                cards[pid] = min(cards.get(pid, 99), minute)

        pid = e.get("player", {}).get("id")
        if pid is None:
            continue
        loc = e.get("location") or [np.nan, np.nan]
        shot = e.get("shot") or {}
        passd = e.get("pass") or {}
        acts.append({
            "minute": minute, "team": team, "player_id": pid, "type": etype,
            "x": loc[0] if len(loc) > 0 else np.nan,
            "xg": float(shot.get("statsbomb_xg", 0.0)) if etype == "Shot" else 0.0,
            "is_pass": etype == "Pass",
            "pass_ok": etype == "Pass" and "outcome" not in passd,
            "is_press": etype == "Pressure",
            "is_duel": etype in ("Duel", "50/50"),
        })

    return {"lineups": lineups, "subs": subs,
            "acts": pd.DataFrame(acts), "cards": cards}


def _team_window(acts: pd.DataFrame, team: str, lo: int, hi: int) -> Dict[str, float]:
    w = acts[(acts["minute"] >= lo) & (acts["minute"] < hi)]
    if w.empty:
        return {"xg": 0.0, "shots": 0, "share": 0.5, "tilt": 0.0}
    tw = w[w["team"] == team]
    return {
        "xg": float(tw["xg"].sum()),
        "shots": int((tw["xg"] > 0).sum()),
        "share": float(len(tw) / len(w)),
        # field tilt: share of this team's actions in the attacking third
        "tilt": float((tw["x"] > 80).mean()) if len(tw) else 0.0,
    }


def extract_match(match_id: int, meta: dict) -> Dict[str, pd.DataFrame]:
    ev = _get(f"{BASE}/events/{match_id}.json")
    p = _parse_events(ev)
    acts, lineups, cards = p["acts"], p["lineups"], p["cards"]
    if acts.empty or not lineups:
        return {"features": pd.DataFrame(), "subs": pd.DataFrame()}

    teams = list({v["team"] for v in lineups.values()})
    if len(teams) != 2:
        return {"features": pd.DataFrame(), "subs": pd.DataFrame()}

    # goals by minute (shots that resulted in a goal)
    goals = [e for e in ev if e.get("type", {}).get("name") == "Shot"
             and (e.get("shot") or {}).get("outcome", {}).get("name") == "Goal"]
    goal_ev = [{"minute": g.get("minute", 0), "team": g.get("team", {}).get("name", "")}
               for g in goals]

    def score_at(minute: int, team: str) -> int:
        gf = sum(1 for g in goal_ev if g["minute"] <= minute and g["team"] == team)
        ga = sum(1 for g in goal_ev if g["minute"] <= minute and g["team"] != team)
        return gf - ga

    subs_by_team: Dict[str, List[int]] = {t: [] for t in teams}
    for s in p["subs"]:
        subs_by_team.setdefault(s["team"], []).append(s["minute"])

    off_minute = {v["player_id"]: v["off"] for v in lineups.values()}
    rows = []
    for minute in GRID:
        team_state = {}
        for t in teams:
            mom = _team_window(acts, t, max(0, minute - MOM_WINDOW), minute)
            opp = _team_window(acts, [x for x in teams if x != t][0],
                               max(0, minute - MOM_WINDOW), minute)
            team_state[t] = {
                "goal_diff": score_at(minute, t),
                "subs_used": sum(1 for m in subs_by_team.get(t, []) if m <= minute),
                "team_xg_w": mom["xg"], "opp_xg_w": opp["xg"],
                "momentum": mom["xg"] - opp["xg"],
                "possession_w": mom["share"], "field_tilt_w": mom["tilt"],
                "shots_w": mom["shots"], "opp_shots_w": opp["shots"],
            }

        for pl in lineups.values():
            on, off = pl["on"], off_minute.get(pl["player_id"])
            if on > minute or (off is not None and off <= minute):
                continue  # not on the pitch at this decision point
            if pl["position"] == "GK":
                continue  # keepers are not tactical sub candidates

            pa = acts[acts["player_id"] == pl["player_id"]]
            upto = pa[pa["minute"] <= minute]
            recent = pa[(pa["minute"] > minute - FORM_WINDOW) & (pa["minute"] <= minute)]
            mins_on = max(1, minute - on)
            overall_rate = len(upto) / mins_on
            recent_rate = len(recent) / min(FORM_WINDOW, mins_on)

            ts = team_state[pl["team"]]
            label = int(off is not None and minute < off <= minute + LABEL_WINDOW)
            rows.append({
                "match_id": match_id,
                "competition": meta["competition"], "season": meta["season"],
                "minute": minute, "player_id": pl["player_id"], "name": pl["name"],
                "team": pl["team"], "position": pl["position"],
                "minutes_played": mins_on, "is_starter": pl["starter"],
                "has_card": int(pl["player_id"] in cards and cards[pl["player_id"]] <= minute),
                "actions_total": len(upto), "actions_recent": len(recent),
                "action_rate": overall_rate, "recent_rate": recent_rate,
                # <1 means the player has faded relative to their own match baseline
                "rate_decline": recent_rate / overall_rate if overall_rate > 0 else 1.0,
                "pass_acc": float(upto["pass_ok"].sum() / max(1, upto["is_pass"].sum())),
                "pass_acc_recent": float(recent["pass_ok"].sum() / max(1, recent["is_pass"].sum())),
                "pressures_recent": int(recent["is_press"].sum()),
                "duels_recent": int(recent["is_duel"].sum()),
                "xg_total": float(upto["xg"].sum()),
                "avg_x": float(upto["x"].mean()) if len(upto) else 60.0,
                **ts,
                "subbed_off_next5": label,
            })

    # ---- measured impact of each actual substitution ----
    sub_rows = []
    for s in p["subs"]:
        m, t = s["minute"], s["team"]
        if m > 90 - 5:
            continue  # too little football left to measure anything
        opp = [x for x in teams if x != t][0]
        pre_t = _team_window(acts, t, max(0, m - IMPACT_WINDOW), m)
        post_t = _team_window(acts, t, m, m + IMPACT_WINDOW)
        pre_o = _team_window(acts, opp, max(0, m - IMPACT_WINDOW), m)
        post_o = _team_window(acts, opp, m, m + IMPACT_WINDOW)
        goals_for = sum(1 for g in goal_ev if m < g["minute"] <= m + IMPACT_WINDOW and g["team"] == t)
        goals_against = sum(1 for g in goal_ev if m < g["minute"] <= m + IMPACT_WINDOW and g["team"] != t)
        sub_rows.append({
            "match_id": match_id, "competition": meta["competition"], "season": meta["season"],
            "minute": m, "team": t,
            "player_off_id": s["player_off_id"], "player_on_id": s["player_on_id"],
            "goal_diff": score_at(m, t),
            "xg_delta": (post_t["xg"] - pre_t["xg"]),
            "xg_against_delta": (post_o["xg"] - pre_o["xg"]),
            "momentum_delta": (post_t["xg"] - post_o["xg"]) - (pre_t["xg"] - pre_o["xg"]),
            "tilt_delta": post_t["tilt"] - pre_t["tilt"],
            "possession_delta": post_t["share"] - pre_t["share"],
            "goals_for_after": goals_for, "goals_against_after": goals_against,
        })

    return {"features": pd.DataFrame(rows), "subs": pd.DataFrame(sub_rows)}


def extract_competition(comp: dict, workers: int = 8) -> Optional[tuple]:
    cid, sid = comp["competition_id"], comp["season_id"]
    tag = f"{cid}_{sid}"
    fpath, spath = OUT / "features" / f"{tag}.parquet", OUT / "subs" / f"{tag}.parquet"
    if fpath.exists():
        return None  # resumable: already done

    meta = {"competition": comp["competition_name"], "season": comp["season_name"]}
    try:
        matches = _get(f"{BASE}/matches/{cid}/{sid}.json")
    except Exception as e:
        logger.warning(f"skip {tag}: {e}")
        return None

    feats, subs = [], []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(extract_match, m["match_id"], meta): m["match_id"] for m in matches}
        for fut in futures:
            try:
                out = fut.result()
                if not out["features"].empty:
                    feats.append(out["features"])
                if not out["subs"].empty:
                    subs.append(out["subs"])
            except Exception as e:
                logger.debug(f"match fail: {e}")

    if not feats:
        return None
    fpath.parent.mkdir(parents=True, exist_ok=True)
    spath.parent.mkdir(parents=True, exist_ok=True)
    fdf = pd.concat(feats, ignore_index=True)
    fdf.to_parquet(fpath, index=False)
    sdf = pd.concat(subs, ignore_index=True) if subs else pd.DataFrame()
    if not sdf.empty:
        sdf.to_parquet(spath, index=False)
    logger.info(f"✓ {meta['competition']} {meta['season']}: "
                f"{len(matches)} matches, {len(fdf)} rows, {len(sdf)} subs")
    return len(fdf), len(sdf)


def run(gender: str = "male", workers: int = 8):
    comps = _get(f"{BASE}/competitions.json")
    todo = [c for c in comps if c.get("competition_gender") == gender]
    logger.info(f"extracting {len(todo)} competition-seasons")
    for c in todo:
        extract_competition(c, workers=workers)
    logger.info("✓ extraction complete")


def demo():
    """Single-match check against a known World Cup 2022 fixture."""
    matches = _get(f"{BASE}/matches/43/106.json")
    mid = matches[0]["match_id"]
    out = extract_match(mid, {"competition": "FIFA World Cup", "season": "2022"})
    f, s = out["features"], out["subs"]
    assert not f.empty, "no feature rows"
    assert f["subbed_off_next5"].sum() > 0, "no positive labels in a full match"
    assert f["minutes_played"].min() >= 0 and f["momentum"].notna().all()
    assert not s.empty and {"momentum_delta", "xg_delta"} <= set(s.columns)
    print(f"match {mid}: {len(f)} rows, {f['subbed_off_next5'].sum()} positives, "
          f"{len(s)} subs, base rate {f['subbed_off_next5'].mean():.3f}")
    print("statsbomb_extract self-check OK")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    demo() if "--demo" in sys.argv else run()
