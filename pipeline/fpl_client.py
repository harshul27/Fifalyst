"""Fantasy Premier League API client - per-gameweek player stats for PL 2026/27.

Public, no-auth, no 403s. This replaces the retired ESPN/Sofascore/FotMob
scraper stack. FPL data is natively organised by gameweek (1-38), which maps
directly onto the season-recording requirement.

Endpoints used:
  bootstrap-static/   -> teams, players (elements), positions, events (GW flags)
  event/{gw}/live/    -> per-player stats for a single gameweek
"""
import asyncio
import logging
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Override to point at a mirror or local simulator (e.g. fpl_match_sim.py)
# when fantasy.premierleague.com is unreachable.
BASE = os.environ.get("FPL_API_BASE", "https://fantasy.premierleague.com/api")

# Per-GW stat fields we keep from event/{gw}/live element['stats'].
# Everything FPL exposes at gameplay level; physical stats come separately.
STAT_FIELDS = [
    "minutes", "starts", "goals_scored", "assists",
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "goals_conceded", "expected_goals_conceded", "clean_sheets", "own_goals",
    "penalties_saved", "penalties_missed", "saves",
    "yellow_cards", "red_cards",
    "tackles", "clearances_blocks_interceptions", "recoveries",
    "defensive_contribution",
    "influence", "creativity", "threat", "ict_index",
    "bonus", "bps", "total_points",
]


def _num(v):
    """FPL returns xG/ICT-family stats as strings ("0.80"); coerce to float."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


class FPLClient:
    """Fetch teams, players and per-gameweek stats from the FPL API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        # A 90-minute poller cannot die on one dropped connection. FPL resets
        # sockets under load (ConnectionResetError 10054) and rate-limits at the
        # edge, so every request retries with backoff: 0/1.5/3/6/12s, ~22s worst
        # case, well inside the 120s poll interval.
        # ponytail: urllib3's Retry, already a requests dependency. Only network
        # and 5xx/429 failures are covered -- a bug in poll() still stops the run.
        retry = Retry(
            total=5, connect=5, read=5, backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self._bootstrap: Dict[str, Any] | None = None

    def _get(self, path: str) -> dict:
        r = self.session.get(f"{BASE}/{path}", timeout=15)
        r.raise_for_status()
        return r.json()

    # ---- bootstrap-derived lookups (cached) ----
    def bootstrap(self) -> dict:
        if self._bootstrap is None:
            self._bootstrap = self._get("bootstrap-static/")
        return self._bootstrap

    def teams(self) -> Dict[int, Dict[str, str]]:
        return {
            t["id"]: {"name": t["name"], "short": t["short_name"]}
            for t in self.bootstrap()["teams"]
        }

    def positions(self) -> Dict[int, str]:
        return {p["id"]: p["singular_name_short"] for p in self.bootstrap()["element_types"]}

    def players_index(self) -> Dict[int, Dict[str, Any]]:
        teams, pos = self.teams(), self.positions()
        idx = {}
        for e in self.bootstrap()["elements"]:
            team = teams.get(e["team"], {})
            idx[e["id"]] = {
                "name": f"{e['first_name']} {e['second_name']}".strip(),
                "web_name": e["web_name"],
                "team": team.get("name", ""),
                "team_short": team.get("short", ""),
                "team_id": e["team"],
                "position": pos.get(e["element_type"], "?"),
            }
        return idx

    def events(self) -> List[Dict[str, Any]]:
        """Gameweeks with status flags."""
        return [
            {k: e.get(k) for k in ("id", "name", "finished", "data_checked", "is_current")}
            for e in self.bootstrap()["events"]
        ]

    def recordable_gameweeks(self) -> List[Dict[str, Any]]:
        """GWs worth recording: any that has been played (current/finished).

        A GW is 'final' once finished AND data_checked; otherwise it's still
        in progress and should be re-recorded on the next run.
        """
        out = []
        for e in self.events():
            if e["is_current"] or e["finished"]:
                out.append({"gw": e["id"], "final": bool(e["finished"] and e["data_checked"])})
        return out

    # ---- per-gameweek player stats ----
    def get_gw_player_stats(self, gw: int) -> List[Dict[str, Any]]:
        """Normalised per-player stats for a gameweek (only players who featured)."""
        live = self._get(f"event/{gw}/live/")
        idx = self.players_index()
        rows = []
        for el in live.get("elements", []):
            stats = el.get("stats", {})
            if not stats.get("minutes"):  # skip players who didn't play
                continue
            meta = idx.get(el["id"], {})
            row = {"gw": gw, "player_id": el["id"], **meta}
            row.update({f: _num(stats.get(f, 0)) for f in STAT_FIELDS})
            rows.append(row)
        return rows

    async def get_gw_player_stats_async(self, gw: int) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_gw_player_stats, gw)


def demo():
    """Self-check against the live API."""
    c = FPLClient()
    assert len(c.teams()) == 20, "expected 20 PL teams"
    assert set(c.positions().values()) >= {"GKP", "DEF", "MID", "FWD"}
    recs = c.recordable_gameweeks()
    print(f"recordable gameweeks: {[r['gw'] for r in recs]}")
    if recs:
        gw = recs[0]["gw"]
        rows = c.get_gw_player_stats(gw)
        assert rows, f"GW{gw} returned no players with minutes"
        assert {"player_id", "team", "position", "goals_scored", "expected_goals"} <= rows[0].keys()
        assert all(isinstance(r["expected_goals"], float) for r in rows), "xG must be numeric"
        print(f"GW{gw}: {len(rows)} players played | sample: "
              f"{rows[0]['web_name']} ({rows[0]['team_short']}) "
              f"min={rows[0]['minutes']} pts={rows[0]['total_points']}")
    print("fpl_client self-check OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo()
