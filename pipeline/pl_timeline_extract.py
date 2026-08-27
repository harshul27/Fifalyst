"""Build substitution-model training data for PL 2020/21-2024/25 from free sources.

StatsBomb open data stops at PL 2015/16, and event-data sites (Understat, FBref,
Fotmob) are unreachable from this environment, so recent seasons are assembled
from two GitHub-hosted open datasets:

  schochastics/football-data  (ODC-BY)   per-match timed incidents scraped from
      data/goals_time2/england_*.json    worldfootball.net: goals with running
                                         score, substitutions (out/in, minute),
                                         yellow/red cards with minutes.
  vaastav/Fantasy-Premier-League         per-player per-fixture minutes, team,
      data/<season>/gws/merged_gw.csv    position and kickoff times -- used to
                                         reconstruct who was on the pitch.

The two are joined per match on (home, away) and per player by abbreviated-name
matching ("Semenyo A." <-> "Antoine Semenyo") with a minutes-agreement fallback.

Output: data/pl_timeline/features/<season>.parquet, one row per
(match, outfield player on pitch, decision minute), labelled subbed_off_next5.
The feature set is the subset of the production model's features that these
sources can supply, plus cross-match workload features FPL uniquely enables.
"""
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RAW = Path("data/pl_timeline/raw")
OUT = Path("data/pl_timeline/features")

SEASONS = {  # incident-file tag -> FPL directory tag
    "2020-2021": "2020-21",
    "2021-2022": "2021-22",
    "2022-2023": "2022-23",
    "2023-2024": "2023-24",
    "2024-2025": "2024-25",
}

INCIDENT_URL = ("https://raw.githubusercontent.com/schochastics/football-data/"
                "master/data/goals_time2/england_premier-league-{tag}.json")
FPL_URL = ("https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
           "master/data/{tag}/{path}")

# Same decision grid and label window as the StatsBomb extractor.
GRID = list(range(30, 91, 5))
LABEL_WINDOW = 5
GOAL_WINDOW = 15   # rolling window for goal-based momentum

# FPL team name -> worldfootball slug, for every club in PL 2020/21-2024/25.
TEAM_SLUG = {
    "Arsenal": "arsenal", "Aston Villa": "aston-villa", "Bournemouth": "afc-bournemouth",
    "Brentford": "brentford", "Brighton": "brighton-hove-albion", "Burnley": "burnley",
    "Chelsea": "chelsea", "Crystal Palace": "crystal-palace", "Everton": "everton",
    "Fulham": "fulham", "Ipswich": "ipswich-town", "Leeds": "leeds-united",
    "Leicester": "leicester-city", "Liverpool": "liverpool", "Luton": "luton-town",
    "Man City": "manchester-city", "Man Utd": "manchester-united",
    "Newcastle": "newcastle-united", "Norwich": "norwich-city",
    "Nott'm Forest": "nottingham-forest",
    "Sheffield Utd": "sheffield-united", "Southampton": "southampton",
    "Spurs": "tottenham-hotspur", "Watford": "watford",
    "West Brom": "west-bromwich-albion", "West Ham": "west-ham-united",
    "Wolves": "wolverhampton-wanderers",
}


def _norm_slug(slug: str) -> str:
    """worldfootball slugs vary over seasons: fc-chelsea vs chelsea, afc-bournemouth."""
    toks = [t for t in slug.split("-") if t not in ("fc", "afc")]
    return "-".join(toks)


def download(force: bool = False):
    """Fetch both raw sources into data/pl_timeline/raw (skips existing files)."""
    import requests
    (RAW / "incidents").mkdir(parents=True, exist_ok=True)
    for tag, fpl_tag in SEASONS.items():
        ipath = RAW / "incidents" / f"england_premier-league-{tag}.json"
        if force or not ipath.exists():
            ipath.write_bytes(requests.get(INCIDENT_URL.format(tag=tag), timeout=120).content)
        for path in ("gws/merged_gw.csv", "fixtures.csv", "teams.csv"):
            fpath = RAW / "fpl" / fpl_tag / Path(path).name
            fpath.parent.mkdir(parents=True, exist_ok=True)
            if force or not fpath.exists():
                fpath.write_bytes(
                    requests.get(FPL_URL.format(tag=fpl_tag, path=path), timeout=120).content)
    logger.info("raw sources present")


# ---------------- name matching ----------------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]", " ", s.lower().replace("-", " ")).strip()


def _abbrev_keys(full_name: str) -> List[str]:
    """Keys in worldfootball's 'Surname F.' style for one FPL full name."""
    toks = _norm(full_name).split()
    if not toks:
        return []
    keys = set()
    ini = toks[0][0]
    if len(toks) == 1:
        keys.add(toks[0])
    for i in range(1, len(toks)):
        keys.add(f"{' '.join(toks[i:])} {ini}")   # progressively shorter surnames
        keys.add(" ".join(toks[i:]))              # surname alone (Brazilians etc.)
    keys.add(toks[0])                             # known by first name (e.g. Rodri)
    return list(keys)


def _incident_key(name: str) -> str:
    return _norm(name.replace(".", ""))


class PlayerMatcher:
    """Match incident names to the FPL players of one team-fixture."""

    def __init__(self, squad: pd.DataFrame):
        self.squad = squad
        self.by_key: Dict[str, List[int]] = {}
        for idx, r in squad.iterrows():
            for k in _abbrev_keys(r["name"]):
                self.by_key.setdefault(k, []).append(idx)

    def match(self, incident_name: str, expected_minutes: Optional[float] = None,
              tol: float = 4.0) -> Optional[int]:
        cands = self.by_key.get(_incident_key(incident_name), [])
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1 and expected_minutes is not None:
            best = min(cands, key=lambda i: abs(self.squad.at[i, "minutes"] - expected_minutes))
            if abs(self.squad.at[best, "minutes"] - expected_minutes) <= tol:
                return best
        if not cands and expected_minutes is not None:
            near = [i for i in self.squad.index
                    if abs(self.squad.at[i, "minutes"] - expected_minutes) <= 1]
            if len(near) == 1:
                return near[0]
        return None


# ---------------- incident parsing ----------------
def _minute(inc: dict) -> float:
    m = re.match(r"(\d+)", str(inc.get("minute", "")))
    if not m:
        return np.nan
    base = int(m.group(1))
    added = int(inc.get("added_time", 0) or 0)
    # First-half stoppage stays at 45 on the timeline; second-half runs past 90.
    return float(min(base + added, 95)) if base >= 90 else float(base)


def _parse_match(rec: dict) -> dict:
    goals, subs, cards, reds = [], [], [], []
    for inc in rec["incident"]["incidents"]:
        t, minute = inc.get("incident_type"), _minute(inc)
        if np.isnan(minute):
            continue
        if t in ("Goal", "Own goal"):
            try:
                hs, as_ = int(inc["home_score"]), int(inc["away_score"])
            except (KeyError, ValueError, TypeError):
                continue
            goals.append({"minute": minute, "home_score": hs, "away_score": as_})
        elif t == "Substitution":
            subs.append({"minute": minute, "side": inc.get("team"),
                         "out": inc.get("player_out", ""), "in": inc.get("player_in", "")})
        elif t == "Yellow Card":
            cards.append({"minute": minute, "side": inc.get("team"),
                          "player": inc.get("player_name", "")})
        elif t == "Red Card":
            reds.append({"minute": minute, "side": inc.get("team"),
                         "player": inc.get("player_name", "")})
    return {"home": rec["home"], "away": rec["away"], "date": rec["date"],
            "goals": sorted(goals, key=lambda g: g["minute"]),
            "subs": subs, "cards": cards, "reds": reds}


def _score_at(goals: List[dict], minute: float) -> Tuple[int, int]:
    hs = as_ = 0
    for g in goals:
        if g["minute"] <= minute:
            hs, as_ = g["home_score"], g["away_score"]
    return hs, as_


# ---------------- season extraction ----------------
def _load_fpl(fpl_tag: str) -> pd.DataFrame:
    gw = pd.read_csv(RAW / "fpl" / fpl_tag / "merged_gw.csv")
    gw = gw[gw["position"].isin(["GK", "GKP", "DEF", "MID", "FWD"])].copy()
    gw["kickoff_time"] = pd.to_datetime(gw["kickoff_time"], utc=True, format="mixed")
    # Cross-match workload: previous fixture minutes / mean of last three,
    # computed strictly from fixtures that kicked off earlier.
    gw = gw.sort_values(["name", "kickoff_time"]).reset_index(drop=True)
    grp = gw.groupby("name")["minutes"]
    gw["prev_minutes"] = grp.shift(1)
    gw["prev3_minutes"] = grp.transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    gw["days_rest"] = (gw["kickoff_time"]
                       - gw.groupby("name")["kickoff_time"].shift(1)).dt.days
    return gw


def extract_season(tag: str, fpl_tag: str) -> pd.DataFrame:
    matches = [_parse_match(r) for r in
               json.load(open(RAW / "incidents" / f"england_premier-league-{tag}.json"))]
    gw = _load_fpl(fpl_tag)
    slug_to_fpl = {_norm_slug(v): k for k, v in TEAM_SLUG.items()}

    # Each (home, away) pairing occurs once a season; the shared FPL fixture id
    # of the two teams' rows identifies the match.
    stats = {"matched_subs": 0, "unmatched_subs": 0, "matches": 0, "skipped": 0}
    rows = []
    for mi, m in enumerate(matches):
        home = slug_to_fpl.get(_norm_slug(m["home"]))
        away = slug_to_fpl.get(_norm_slug(m["away"]))
        if not home or not away:
            logger.warning(f"unmapped team slug: {m['home']} / {m['away']}")
            stats["skipped"] += 1
            continue
        fx = (set(gw.loc[(gw["team"] == home) & gw["was_home"], "fixture"])
              & set(gw.loc[(gw["team"] == away) & ~gw["was_home"], "fixture"]))
        if len(fx) != 1:
            stats["skipped"] += 1
            continue
        fixture_id = fx.pop()
        match_id = f"{tag}_{fixture_id}"
        stats["matches"] += 1

        played = gw[(gw["fixture"] == fixture_id) & (gw["minutes"] > 0)
                    & (gw["team"].isin([home, away]))].reset_index(drop=True)
        side_of = {home: "home", away: "away"}

        # ---- reconstruct on/off minutes per player ----
        state = {i: {"on": 0.0, "off": None, "reason": None, "card": None}
                 for i in played.index}
        matchers = {t: PlayerMatcher(played[played["team"] == t]) for t in (home, away)}

        def team_of(side: str) -> str:
            return home if side == "home" else away

        for s in m["subs"]:
            t = team_of(s["side"])
            mm = matchers[t]
            i_out = mm.match(s["out"], expected_minutes=min(s["minute"], 90))
            i_in = mm.match(s["in"], expected_minutes=max(0, 90 - s["minute"]))
            if i_out is not None:
                state[i_out]["off"], state[i_out]["reason"] = s["minute"], "sub"
                stats["matched_subs"] += 1
            else:
                stats["unmatched_subs"] += 1
            if i_in is not None:
                state[i_in]["on"] = s["minute"]
        for c in m["cards"]:
            i = matchers[team_of(c["side"])].match(c["player"])
            if i is not None and state[i]["card"] is None:
                state[i]["card"] = c["minute"]
        for r in m["reds"]:
            i = matchers[team_of(r["side"])].match(r["player"])
            if i is not None:
                state[i]["off"], state[i]["reason"] = r["minute"], "red"

        # FPL-minutes fallback for events the name match missed: a starter with
        # fewer than 88 recorded minutes and no red card left via substitution.
        for i, st in state.items():
            mins = played.at[i, "minutes"]
            if st["on"] == 0.0 and mins < 88 and st["off"] is None:
                if played.at[i, "red_cards"] > 0:
                    st["off"], st["reason"] = float(mins), "red"
                else:
                    st["off"], st["reason"] = float(mins), "sub"

        goals = m["goals"]
        subs_by_team = {home: [], away: []}
        for s in m["subs"]:
            subs_by_team[team_of(s["side"])].append(s["minute"])

        # ---- decision-grid rows ----
        for minute in GRID:
            hs, as_ = _score_at(goals, minute)
            hs_prev, as_prev = _score_at(goals, minute - GOAL_WINDOW)
            for i, st in state.items():
                p = played.loc[i]
                if p["position"] in ("GK", "GKP"):
                    continue
                if st["on"] > minute or (st["off"] is not None and st["off"] <= minute):
                    continue
                t = p["team"]
                gd = (hs - as_) if t == home else (as_ - hs)
                gf_w = (hs - hs_prev) if t == home else (as_ - as_prev)
                ga_w = (as_ - as_prev) if t == home else (hs - hs_prev)
                off = st["off"]
                label = int(off is not None and st["reason"] == "sub"
                            and minute < off <= minute + LABEL_WINDOW)
                rows.append({
                    "match_id": match_id, "season": fpl_tag, "competition": "Premier League",
                    "minute": minute, "name": p["name"], "team": t,
                    "position": p["position"],
                    "minutes_played": minute - st["on"],
                    "is_starter": int(st["on"] == 0.0),
                    "is_home": int(t == home),
                    "has_card": int(st["card"] is not None and st["card"] <= minute),
                    "goal_diff": gd, "total_goals": hs + as_,
                    "goals_for_w": gf_w, "goals_against_w": ga_w,
                    "subs_used": sum(1 for x in subs_by_team[t] if x <= minute),
                    "opp_subs_used": sum(1 for x in subs_by_team[home if t == away else away]
                                         if x <= minute),
                    "prev_minutes": p["prev_minutes"],
                    "prev3_minutes": p["prev3_minutes"],
                    "days_rest": p["days_rest"],
                    "subbed_off_next5": label,
                })

    df = pd.DataFrame(rows)
    total = stats["matched_subs"] + stats["unmatched_subs"]
    logger.info(f"{tag}: {stats['matches']}/{len(matches)} matches joined "
                f"({stats['skipped']} skipped), sub name-match rate "
                f"{stats['matched_subs'] / max(1, total):.1%}, "
                f"{len(df):,} rows, positive rate {df['subbed_off_next5'].mean():.4f}")
    return df


def run():
    download()
    OUT.mkdir(parents=True, exist_ok=True)
    for tag, fpl_tag in SEASONS.items():
        out = OUT / f"{fpl_tag}.parquet"
        if out.exists():
            logger.info(f"skip {fpl_tag}: exists")
            continue
        df = extract_season(tag, fpl_tag)
        df.to_parquet(out, index=False)
    logger.info("✓ extraction complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run()
