"""Record gameweeks from the vaastav/Fantasy-Premier-League GitHub mirror.

Drop-in alternative to `record.py` for environments where
fantasy.premierleague.com is unreachable (e.g. egress-restricted cloud
sessions) but raw.githubusercontent.com is not. The mirror republishes the
official FPL per-gameweek stats, so the data is real - just hours behind the
live API rather than minutes.

Produces byte-identical storage to the live path: the same player rows are
enriched (physical columns), aggregated into team buckets and written as
parquet by pipeline/season_store.py.

Usage:
    python record_mirror.py             # record all mirrored gameweeks
    python record_mirror.py --gw 1      # one gameweek
    python record_mirror.py --status    # list recorded gameweeks
"""
import argparse
import io
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from pipeline.fpl_client import STAT_FIELDS
from pipeline.physical_adapter import PhysicalStatsAdapter
from pipeline.season_store import SeasonStore
from pipeline.team_stats import aggregate_teams

logger = logging.getLogger(__name__)

SEASON = "2026-27"
BASE = f"https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{SEASON}"
# A GW whose last kickoff is older than this is treated as final (FPL's
# data_checked flag lands within a day or two of the last fixture).
FINAL_AFTER = timedelta(days=3)


def _csv(path: str) -> pd.DataFrame:
    r = requests.get(f"{BASE}/{path}", timeout=60)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def build_gameweek(merged: pd.DataFrame, players_raw: pd.DataFrame,
                   teams_meta: pd.DataFrame, gw: int) -> pd.DataFrame:
    """Reshape one mirror gameweek into the fpl_client row schema."""
    g = merged[(merged["GW"] == gw) & (merged["minutes"] > 0)].copy()
    if g.empty:
        return pd.DataFrame()

    short = dict(zip(teams_meta["name"], teams_meta["short_name"]))
    praw = players_raw.set_index("id")

    rows = pd.DataFrame({
        "gw": gw,
        "player_id": g["element"],
        "name": g["name"],
        "web_name": g["element"].map(praw["web_name"]).fillna(g["name"]),
        "team": g["team"],
        "team_short": g["team"].map(short).fillna(""),
        "team_id": g["element"].map(praw["team"]).fillna(0).astype(int),
        "position": g["position"],
    })
    for f in STAT_FIELDS:
        rows[f] = pd.to_numeric(g[f], errors="coerce").fillna(0).values
    return rows


def gw_is_final(merged: pd.DataFrame, gw: int) -> bool:
    kicks = pd.to_datetime(merged.loc[merged["GW"] == gw, "kickoff_time"], utc=True)
    return bool(len(kicks)) and (datetime.now(timezone.utc) - kicks.max()) > FINAL_AFTER


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gw", type=int, help="record a single gameweek")
    p.add_argument("--status", action="store_true", help="list recorded gameweeks")
    args = p.parse_args()

    store = SeasonStore()
    if args.status:
        done = store.recorded_gameweeks()
        print(f"recorded gameweeks: {sorted(done)}")
        print(f"final gameweeks:    {sorted(g for g, m in done.items() if m.get('final'))}")
        return

    merged = _csv("gws/merged_gw.csv")
    players_raw = _csv("players_raw.csv")
    teams_meta = _csv("teams.csv")
    physical = PhysicalStatsAdapter()

    gws = [args.gw] if args.gw else sorted(merged["GW"].unique())
    for gw in gws:
        players = build_gameweek(merged, players_raw, teams_meta, int(gw))
        if players.empty:
            logger.info(f"GW{gw}: no player data in mirror - skipped")
            continue
        players = physical.enrich(players)
        teams = aggregate_teams(players)
        final = gw_is_final(merged, int(gw))
        store.write_gameweek(int(gw), players, teams, final=final)
        print(f"GW{gw}: {len(players)} players, {len(teams)} teams (final={final})")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
