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
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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


# Substitution detection thresholds.
# FPL updates `minutes` in chunks, not every minute, so a single lagging poll
# leaves EVERY player on the pitch looking frozen. Detection therefore demands
# sustained evidence rather than one stalled observation.
MIN_CLOCK_ADVANCE = 3      # clock must move this far with minutes unchanged
REQUIRED_CONFIRMATIONS = 2  # ...across this many consecutive polls
MAX_SUBS_PER_TEAM = 5      # rule of the game; a hard guard on false positives


def advance_stall(stall: int, clock_moved: float, mins_moved: float) -> int:
    """The single withdrawal rule, shared by live detection and offline replay.

    Returns the updated consecutive-stall count. A player accruing minutes
    resets it; a player frozen while the clock moves meaningfully increments it.
    """
    if mins_moved > 0:
        return 0
    if clock_moved >= MIN_CLOCK_ADVANCE:
        return stall + 1
    return stall


def rederive_withdrawals(timeline: "pd.DataFrame") -> "pd.DataFrame":
    """Replay stored snapshots through the current rule.

    Snapshots recorded before the detection fix carry bad `on_pitch` labels, and
    the learning loop harvests its training labels from them -- so history is
    re-derived rather than trusted.
    """
    import pandas as pd

    # Use every row, on-pitch or not, and group by name rather than player_id:
    # the poller flips `on_pitch` to False on the very poll that confirms a
    # withdrawal, and the store writes withdrawn rows with player_id/minutes
    # as null - so an on-pitch-only, id-keyed pass severs every player's trail
    # one frozen observation short of REQUIRED_CONFIRMATIONS and re-derives a
    # correctly-labelled trail to zero substitutions. The frozen-minutes rule
    # itself does not care about the stored label, which is exactly why
    # history is re-derived. Null minutes count as frozen, never as movement.
    onp = timeline.copy()
    if onp.empty:
        return pd.DataFrame()

    rows = []
    for (fx, side, nm), g in onp.groupby(["fixture_id", "side", "name"]):
        g = g.sort_values("ts")
        stall, prev, last_mins, pid, pos = 0, None, None, None, None
        for _, r in g.iterrows():
            mins = r["minutes_played"]
            if prev is not None:
                mins_moved = (0.0 if pd.isna(mins) or last_mins is None
                              else mins - last_mins)
                stall = advance_stall(stall, r["minute"] - prev["minute"],
                                      mins_moved)
                if (stall >= REQUIRED_CONFIRMATIONS and r["minute"] < 90
                        and last_mins is not None):
                    rows.append({
                        "fixture_id": fx, "side": side, "player_id": pid,
                        "name": nm, "team": r["team"],
                        "position": pos,
                        # the frozen minutes value is the minute they came off
                        "minute": int(last_mins),
                        "detected_at_minute": int(r["minute"]),
                    })
                    break
            if not pd.isna(mins):
                last_mins = mins
            if not pd.isna(r["player_id"]):
                pid = str(r["player_id"])
            if isinstance(r.get("position"), str):
                pos = r["position"]
            prev = r

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # enforce the laws of the game: at most 5 per team per fixture
    out = (out.sort_values("minute")
              .groupby(["fixture_id", "side"], group_keys=False)
              .head(MAX_SUBS_PER_TEAM)
              .reset_index(drop=True))
    return out


class LivePoller:
    """Polls FPL and turns cumulative snapshots into live match state."""

    def __init__(self, client: Optional[FPLClient] = None,
                 state_file: str = "data/live/poller_state.json"):
        self.fpl = client or FPLClient()
        # player_id -> list of (match_minute, cumulative stats) observed so far
        self.history: Dict[int, List[Dict[str, Any]]] = {}
        # player_id -> consecutive polls seen frozen while the clock advanced
        self.stall: Dict[int, int] = {}
        # player_id -> minute they were concluded to have left the pitch (sticky)
        self.withdrawn: Dict[int, float] = {}
        self.state_file = Path(state_file) if state_file else None
        self._load_state()

    # ---- state persistence (a restart must not lose withdrawal history) ----
    def _load_state(self):
        if not self.state_file or not self.state_file.exists():
            return
        try:
            raw = json.loads(self.state_file.read_text())
            self.history = {int(k): v for k, v in raw.get("history", {}).items()}
            self.stall = {int(k): v for k, v in raw.get("stall", {}).items()}
            self.withdrawn = {int(k): v for k, v in raw.get("withdrawn", {}).items()}
            logger.info(f"restored poller state: {len(self.withdrawn)} known withdrawals")
        except Exception as e:
            logger.warning(f"could not restore poller state ({e}); starting fresh")

    def _save_state(self):
        if not self.state_file:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps({
                # keep history bounded: only the recent tail is ever consulted
                "history": {str(k): v[-12:] for k, v in self.history.items()},
                "stall": {str(k): v for k, v in self.stall.items()},
                "withdrawn": {str(k): v for k, v in self.withdrawn.items()},
            }))
        except Exception as e:
            logger.warning(f"could not persist poller state: {e}")

    def _check_withdrawal(self, pid: int, minute: int, mins: float,
                          finished: bool) -> bool:
        """Sustained-evidence withdrawal test. Returns True once confirmed.

        A player is only judged withdrawn when their cumulative minutes stay
        flat while the match clock advances meaningfully, repeatedly. At full
        time everything freezes, so nothing is ever flagged then.
        """
        if pid in self.withdrawn:
            return True
        if finished:
            return False  # full time freezes every player's minutes

        prev = self.history.get(pid)
        if not prev:
            return False
        last = prev[-1]
        clock_moved = minute - last["minute"]
        mins_moved = mins - last["minutes"]

        self.stall[pid] = advance_stall(self.stall.get(pid, 0), clock_moved, mins_moved)

        if self.stall.get(pid, 0) >= REQUIRED_CONFIRMATIONS:
            # A starter's frozen `minutes` IS the minute they left the pitch --
            # more precise than the clock reading when we noticed.
            self.withdrawn[pid] = mins
            return True
        return False

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

                withdrawn = self._check_withdrawal(pid, minute, mins, fin)

                self.history.setdefault(pid, []).append(
                    {"minute": minute, "minutes": mins, "xg": xg_now, "ts": now})

                if withdrawn:
                    # A team cannot exceed the substitution limit. More than
                    # that means the feed stalled, not that 6 players came off.
                    if len(subs_off[side]) >= MAX_SUBS_PER_TEAM:
                        logger.warning(
                            f"fixture {f['id']} {side}: >{MAX_SUBS_PER_TEAM} withdrawals "
                            f"detected - treating {meta['web_name']} as still on "
                            f"(stalled feed, not a substitution)")
                        self.withdrawn.pop(pid, None)
                        self.stall[pid] = 0
                    else:
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

        self._save_state()
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
    """Self-check: detection must survive a lagging feed and full time."""
    p = LivePoller(state_file=None)

    # --- regression: the bug that produced 15 phantom withdrawals at 88' ---
    # FPL updates minutes in chunks. One lagging poll leaves every player frozen.
    p.history = {1: [{"minute": 60, "minutes": 60.0, "xg": 0.1, "ts": "t0"}]}
    assert not p._check_withdrawal(1, 63, 60.0, finished=False),         "one stalled poll must NOT flag a withdrawal"
    p.history[1].append({"minute": 63, "minutes": 60.0, "xg": 0.1, "ts": "t1"})
    # second consecutive stall with the clock advancing = confirmed
    assert p._check_withdrawal(1, 66, 60.0, finished=False),         "sustained stall should be detected"
    assert p.withdrawn[1] == 60.0, "withdrawal minute should be the frozen minutes value"

    # --- full time must never flag anyone ---
    p2 = LivePoller(state_file=None)
    p2.history = {2: [{"minute": 85, "minutes": 85.0, "xg": 0.0, "ts": "t0"}],
                  3: [{"minute": 85, "minutes": 85.0, "xg": 0.0, "ts": "t0"}]}
    p2.stall = {2: 5, 3: 5}
    assert not p2._check_withdrawal(2, 90, 85.0, finished=True),         "full time freezes everyone - must not be read as substitutions"

    # --- a player still accruing minutes resets the stall counter ---
    p3 = LivePoller(state_file=None)
    p3.history = {4: [{"minute": 60, "minutes": 60.0, "xg": 0.0, "ts": "t0"}]}
    p3.stall = {4: 1}
    assert not p3._check_withdrawal(4, 65, 65.0, finished=False)
    assert p3.stall[4] == 0, "minutes advancing must clear the stall counter"

    # --- small clock movement is not evidence ---
    p4 = LivePoller(state_file=None)
    p4.history = {5: [{"minute": 60, "minutes": 60.0, "xg": 0.0, "ts": "t0"}]}
    assert not p4._check_withdrawal(5, 61, 60.0, finished=False)
    assert p4.stall.get(5, 0) == 0, "a 1-minute tick is within feed lag"

    # --- state persistence survives a restart ---
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "state.json")
        a = LivePoller(state_file=path)
        a.withdrawn = {9: 61.0}
        a.history = {9: [{"minute": 61, "minutes": 61.0, "xg": 0.0, "ts": "t"}]}
        a._save_state()
        b = LivePoller(state_file=path)
        assert b.withdrawn.get(9) == 61.0, "withdrawal history lost across restart"

    # --- live check against the real API ---
    p5 = LivePoller(state_file=None)
    gw = p5.fpl.recordable_gameweeks()[0]["gw"]
    matches = p5.poll(gw)
    assert matches, "no started fixtures found"
    m = matches[0]
    assert m.home_state.goal_diff == m.home_score - m.away_score
    assert m.away_state.goal_diff == -m.home_state.goal_diff
    # a cold first poll has no history, so nothing may be flagged yet
    assert not m.home_subs_off and not m.away_subs_off,         "a first poll cannot know any withdrawal"
    assert all(x.position in ("DEF", "MID", "FWD") for x in m.home_players)
    print(f"GW{gw} {m.home_team} {m.home_score}-{m.away_score} {m.away_team} "
          f"@{m.minute}' | {len(m.home_players)}v{len(m.away_players)} outfield tracked")
    print("live_poller self-check OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    demo()
