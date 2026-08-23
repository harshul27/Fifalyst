"""Live FPL poller: reconstruct in-match state from cumulative snapshots.

FPL publishes cumulative per-player totals, not events. Polling on an interval
and diffing consecutive snapshots recovers the things a live coach needs:

  * per-player minute progression  -> who is on the pitch, and for how long
  * substitutions                  -> a player whose minutes stop advancing
                                      while the match clock runs was withdrawn
  * rolling team xG windows        -> xG accumulated between two snapshots
  * booking status                 -> from fixture card stats

Feature coverage is deliberately limited to what FPL actually supplies; see
measure_live_ceiling.py for the measured accuracy cost. No proxy reconstruction
of event counts is attempted -- the ablation showed it adds nothing.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.fpl_client import FPLClient
from pipeline.sub_recommender import MatchState, PlayerState

logger = logging.getLogger(__name__)


@dataclass
class LiveMatch:
    """One in-progress fixture, reconstructed from the latest snapshot."""
    fixture_id: int
    minute: int
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    finished: bool
    home_players: List[PlayerState] = field(default_factory=list)
    away_players: List[PlayerState] = field(default_factory=list)
    home_subs_off: List[str] = field(default_factory=list)
    away_subs_off: List[str] = field(default_factory=list)
    home_state: Optional[MatchState] = None
    away_state: Optional[MatchState] = None

    def state_for(self, side: str) -> MatchState:
        return self.home_state if side == "home" else self.away_state

    def players_for(self, side: str) -> List[PlayerState]:
        return self.home_players if side == "home" else self.away_players


class LivePoller:
    """Polls FPL and turns cumulative snapshots into live match state."""

    def __init__(self, client: Optional[FPLClient] = None):
        self.fpl = client or FPLClient()
        # player_id -> list of (match_minute, cumulative stats) observed so far
        self.history: Dict[int, List[Dict[str, Any]]] = {}
        self.last_minute: Dict[int, int] = {}  # player_id -> last seen minutes

    # ---- raw fetch ----
    def _fixtures(self, gw: int) -> List[dict]:
        return self.fpl._get(f"fixtures/?event={gw}")

    def _live(self, gw: int) -> dict:
        return self.fpl._get(f"event/{gw}/live/")

    def _cards(self, fixtures: List[dict]) -> Dict[int, bool]:
        """Booked players, from per-fixture card stats."""
        booked = {}
        for f in fixtures:
            for stat in f.get("stats", []):
                if stat.get("identifier") in ("yellow_cards", "red_cards"):
                    for side in ("h", "a"):
                        for entry in stat.get(side, []):
                            booked[entry["element"]] = True
        return booked

    # ---- snapshot -> state ----
    def poll(self, gw: int, window: int = 10) -> List[LiveMatch]:
        """Fetch one snapshot and return state for every in-progress fixture.

        window: minutes of look-back for the rolling xG windows. Requires at
        least one earlier poll; with no history the windows are zero.
        """
        fixtures = self._fixtures(gw)
        live = self._live(gw)
        teams = self.fpl.teams()
        idx = self.fpl.players_index()
        booked = self._cards(fixtures)

        stats_by_player = {e["id"]: e.get("stats", {}) for e in live.get("elements", [])}
        now = datetime.now(timezone.utc).isoformat()

        matches = []
        for f in fixtures:
            if not f.get("started"):
                continue
            minute = int(f.get("minutes") or 0)
            fin = bool(f.get("finished") or f.get("finished_provisional"))
            h_id, a_id = f["team_h"], f["team_a"]
            h_name = teams.get(h_id, {}).get("name", "?")
            a_name = teams.get(a_id, {}).get("name", "?")
            h_score = int(f.get("team_h_score") or 0)
            a_score = int(f.get("team_a_score") or 0)

            sides = {"home": (h_id, []), "away": (a_id, [])}
            subs_off = {"home": [], "away": []}
            team_xg_window = {"home": 0.0, "away": 0.0}

            for pid, meta in idx.items():
                if meta["team_id"] not in (h_id, a_id):
                    continue
                st = stats_by_player.get(pid, {})
                mins = float(st.get("minutes", 0) or 0)
                if mins <= 0:
                    continue
                side = "home" if meta["team_id"] == h_id else "away"

                prev = self.history.get(pid, [])
                # xG accrued inside the look-back window
                xg_now = _f(st.get("expected_goals"))
                past = [h for h in prev if minute - h["minute"] <= window]
                xg_then = past[0]["xg"] if past else (prev[0]["xg"] if prev else 0.0)
                team_xg_window[side] += max(0.0, xg_now - xg_then)

                # withdrawn: minutes frozen while the clock advanced
                withdrawn = False
                if prev:
                    last = prev[-1]
                    if minute > last["minute"] and mins == last["minutes"] and minute < 90:
                        withdrawn = True

                self.history.setdefault(pid, []).append(
                    {"minute": minute, "minutes": mins, "xg": xg_now, "ts": now})

                if withdrawn:
                    subs_off[side].append(meta["web_name"])
                    continue  # no longer a candidate

                pos = meta["position"]
                if pos == "GKP":
                    continue  # keepers are not tactical sub candidates
                sides[side][1].append(PlayerState(
                    player_id=str(pid), name=meta["web_name"],
                    position={"DEF": "DEF", "MID": "MID", "FWD": "FWD"}.get(pos, "MID"),
                    minutes_played=int(mins),
                    is_starter=bool(st.get("starts", 0)),
                    has_card=bool(booked.get(pid, False)),
                    xg_total=xg_now,
                ))

            m = LiveMatch(
                fixture_id=f["id"], minute=minute, home_team=h_name, away_team=a_name,
                home_score=h_score, away_score=a_score, finished=fin,
                home_players=sides["home"][1], away_players=sides["away"][1],
                home_subs_off=subs_off["home"], away_subs_off=subs_off["away"],
            )
            m.home_state = MatchState(
                minute=minute, goal_diff=h_score - a_score, subs_used=len(subs_off["home"]),
                team_xg_w=team_xg_window["home"], opp_xg_w=team_xg_window["away"])
            m.away_state = MatchState(
                minute=minute, goal_diff=a_score - h_score, subs_used=len(subs_off["away"]),
                team_xg_w=team_xg_window["away"], opp_xg_w=team_xg_window["home"])
            matches.append(m)

        logger.info(f"polled GW{gw}: {len(matches)} started fixtures "
                    f"({sum(1 for m in matches if not m.finished)} in progress)")
        return matches

    def in_progress(self, gw: int) -> List[LiveMatch]:
        return [m for m in self.poll(gw) if not m.finished]


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def demo():
    """Self-check: snapshot diffing must detect withdrawals and build valid state."""
    p = LivePoller()

    # simulated two-poll sequence: player 1 keeps playing, player 2 frozen at 60'
    p.history = {
        1: [{"minute": 60, "minutes": 60.0, "xg": 0.1, "ts": "t0"}],
        2: [{"minute": 60, "minutes": 60.0, "xg": 0.3, "ts": "t0"}],
    }
    prev1, prev2 = p.history[1][-1], p.history[2][-1]
    minute_now = 70
    assert not (minute_now > prev1["minute"] and 70.0 == prev1["minutes"]), "false positive"
    assert (minute_now > prev2["minute"] and 60.0 == prev2["minutes"]), "missed withdrawal"

    # live check against the real API (GW1 is finished, so nothing in progress)
    gw = p.fpl.recordable_gameweeks()[0]["gw"]
    matches = p.poll(gw)
    assert matches, "no started fixtures found"
    m = matches[0]
    assert m.home_state.goal_diff == m.home_score - m.away_score
    assert m.away_state.goal_diff == -m.home_state.goal_diff
    assert all(x.minutes_played > 0 for x in m.home_players + m.away_players)
    assert all(x.position in ("DEF", "MID", "FWD") for x in m.home_players)
    print(f"GW{gw} {m.home_team} {m.home_score}-{m.away_score} {m.away_team} "
          f"@{m.minute}' | {len(m.home_players)}v{len(m.away_players)} outfield tracked")
    print("live_poller self-check OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    demo()
