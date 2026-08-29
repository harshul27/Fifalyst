"""Record PL 2026/27 fixtures and results from openfootball/football.json.

Complements record_mirror.py for egress-restricted environments where only
raw.githubusercontent.com is reachable: openfootball carries the full 380-match
fixture list with kickoff times and full-time/half-time scores, and its results
land within hours of full time - typically ahead of the vaastav mirror's
per-player gameweek files. It is match-level only (no player stats).

Writes data/pl_2026_27/fixtures.parquet with one row per fixture:
    round, date, time, kickoff_utc, team1, team2, played,
    ft_home, ft_away, ht_home, ht_away

Usage:
    python record_openfootball.py             # fetch and store all fixtures
    python record_openfootball.py --status    # summary of stored fixtures
    python record_openfootball.py --today     # show today's fixtures/results
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

SEASON_DIR = Path("data/pl_2026_27")
FIXTURES_PATH = SEASON_DIR / "fixtures.parquet"
URL = ("https://raw.githubusercontent.com/openfootball/football.json/"
       "master/2026-27/en.1.json")
# openfootball kickoff times are UK local
UK = ZoneInfo("Europe/London")


def fetch() -> pd.DataFrame:
    matches = requests.get(URL, timeout=60).json()["matches"]
    rows = []
    for m in matches:
        score = m.get("score") or {}
        ft = score.get("ft") or [None, None]
        ht = score.get("ht") or [None, None]
        kickoff = None
        if m.get("date") and m.get("time"):
            kickoff = (datetime.fromisoformat(f"{m['date']}T{m['time']}")
                       .replace(tzinfo=UK).astimezone(timezone.utc))
        rows.append({
            "round": int(m["round"].split()[-1]),
            "date": m.get("date"),
            "time": m.get("time"),
            "kickoff_utc": kickoff,
            "team1": m["team1"],
            "team2": m["team2"],
            "played": ft[0] is not None,
            "ft_home": ft[0], "ft_away": ft[1],
            "ht_home": ht[0], "ht_away": ht[1],
        })
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame):
    played = df[df.played]
    print(f"fixtures: {len(df)}  played: {len(played)}"
          f"  rounds with results: {sorted(played['round'].unique().tolist())}")
    if not played.empty:
        last = played.sort_values("kickoff_utc").tail(3)
        for _, r in last.iterrows():
            print(f"  latest: R{r['round']} {r['date']} {r['team1']} "
                  f"{r['ft_home']:.0f}-{r['ft_away']:.0f} {r['team2']}")


def show_today(df: pd.DataFrame):
    today = datetime.now(UK).date().isoformat()
    day = df[df.date == today].sort_values("kickoff_utc")
    if day.empty:
        print(f"no fixtures on {today}")
        return
    now = datetime.now(timezone.utc)
    for _, r in day.iterrows():
        if r.played:
            state = f"FT {r.ft_home:.0f}-{r.ft_away:.0f}"
        elif r.kickoff_utc is not None and r.kickoff_utc <= now:
            state = "in progress / awaiting result"
        else:
            state = f"kicks off {r.time} UK"
        print(f"R{r['round']} {r['team1']} vs {r['team2']}: {state}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true",
                   help="summarize stored fixtures without fetching")
    p.add_argument("--today", action="store_true",
                   help="fetch and show today's fixtures/results")
    args = p.parse_args()

    if args.status:
        if not FIXTURES_PATH.exists():
            print("no fixtures recorded yet - run without --status first")
            return
        summarize(pd.read_parquet(FIXTURES_PATH))
        return

    df = fetch()
    SEASON_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(FIXTURES_PATH, index=False)
    print(f"stored {FIXTURES_PATH}")
    summarize(df)
    if args.today:
        print("--- today ---")
        show_today(df)


if __name__ == "__main__":
    main()
