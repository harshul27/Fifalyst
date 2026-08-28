"""Local FPL API simulator: replay a real match through the live-coach pipeline.

Serves the three endpoints pipeline/live_poller.py consumes -- bootstrap-static/,
fixtures/?event={gw} and event/{gw}/live/ -- reconstructed from a real match's
StatsBomb open-data events, with the match clock advancing in accelerated real
time. Point the pipeline at it with FPL_API_BASE:

    python fpl_match_sim.py --port 8484 --speed 1.0 &     # 1 match-min / sec
    FPL_API_BASE=http://127.0.0.1:8484/api python live_coach.py --gw 1 \
        --interval 5 --until-finished

Every number served is real: lineups, substitutions, cards, goals and shot xG
come from the match's event stream. Only the clock is synthetic. This exists
to exercise the genuine poller (snapshot diffing, stall-based substitution
detection, rolling xG windows) in environments where the live FPL API is
unreachable, and as a deterministic end-to-end test bed.

Default match: Arsenal 2-1 Manchester City, PL 2015/16 (StatsBomb 3754296).
"""
import argparse
import json
import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import requests

from pipeline.statsbomb_extract import POS_GROUP

logger = logging.getLogger(__name__)

SB = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
ETYPE = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
ESHORT = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _pos_group(name):
    for key, grp in POS_GROUP.items():
        if key in (name or ""):
            return grp
    return "MID"


def build_match(match_id: int):
    """Reduce a StatsBomb event stream to the state the FPL API would carry."""
    events = requests.get(f"{SB}/events/{match_id}.json", timeout=120).json()

    teams = {}          # team name -> 1 (home) / 2 (away)
    players = {}        # sb player id -> dict
    goals = []          # (minute, fpl_team_id)
    cards = []          # (minute, sb player id)
    shots = []          # (minute, sb player id, xg)
    subs = []           # (minute, off_id, on_id)

    for ev in events:
        t = ev["type"]["name"]
        team = ev.get("team", {}).get("name")
        if t == "Starting XI":
            tid = len(teams) + 1
            teams[team] = tid
            for slot in ev["tactics"]["lineup"]:
                p = slot["player"]
                players[p["id"]] = {
                    "name": p["name"], "team": tid, "start": 0, "end": None,
                    "pos": _pos_group(slot["position"]["name"]), "starter": True,
                }
        elif t == "Substitution":
            off, on = ev["player"], ev["substitution"]["replacement"]
            m = ev["minute"]
            subs.append((m, off["id"], on["id"]))
            players[off["id"]]["end"] = m
            players[on["id"]] = {
                "name": on["name"], "team": teams[team], "start": m, "end": None,
                "pos": players[off["id"]]["pos"], "starter": False,
            }
        elif t == "Shot":
            xg = ev.get("shot", {}).get("statsbomb_xg") or 0.0
            shots.append((ev["minute"], ev["player"]["id"], float(xg)))
            if ev["shot"].get("outcome", {}).get("name") == "Goal":
                goals.append((ev["minute"], teams[team]))
        elif t == "Own Goal Against":
            goals.append((ev["minute"], 3 - teams[team]))
        elif t in ("Foul Committed", "Bad Behaviour"):
            card = (ev.get("foul_committed") or ev.get("bad_behaviour") or {}).get("card")
            if card:
                cards.append((ev["minute"], ev["player"]["id"]))
                if "Red" in card["name"]:
                    players[ev["player"]["id"]]["end"] = ev["minute"]

    duration = max(e["minute"] for e in events)
    # stable FPL-style element ids
    eid = {sb: i + 1 for i, sb in enumerate(sorted(players))}
    names = {v: k for k, v in teams.items()}
    return {
        "home": names[1], "away": names[2], "duration": duration,
        "players": {eid[sb]: p for sb, p in players.items()},
        "goals": goals,
        "cards": [(m, eid[sb]) for m, sb in cards],
        "shots": [(m, eid[sb], xg) for m, sb, xg in shots],
    }


class Sim:
    def __init__(self, match, gw: int, speed: float):
        self.m, self.gw, self.speed = match, gw, speed
        self.t0 = time.time()

    def minute(self) -> int:
        return min(int((time.time() - self.t0) * self.speed), self.m["duration"])

    def bootstrap(self):
        elements, types_seen = [], set()
        for pid, p in self.m["players"].items():
            et = ETYPE[p["pos"]] if p["pos"] in ETYPE else 3
            types_seen.add(et)
            last = p["name"].split()[-1]
            elements.append({
                "id": pid, "first_name": "", "second_name": p["name"],
                "web_name": last, "team": p["team"], "element_type": et,
            })
        return {
            "events": [{"id": self.gw, "name": f"Gameweek {self.gw} (sim)",
                        "finished": False, "data_checked": False, "is_current": True}],
            "teams": [{"id": 1, "name": self.m["home"], "short_name": self.m["home"][:3].upper()},
                      {"id": 2, "name": self.m["away"], "short_name": self.m["away"][:3].upper()}],
            "element_types": [{"id": t, "singular_name_short": ESHORT[t]}
                              for t in sorted(types_seen | {1, 2, 3, 4})],
            "elements": elements,
        }

    def fixtures(self):
        now = self.minute()
        h = sum(1 for m, t in self.m["goals"] if t == 1 and m <= now)
        a = sum(1 for m, t in self.m["goals"] if t == 2 and m <= now)
        booked = [pid for m, pid in self.m["cards"] if m <= now]
        stats = [{
            "identifier": "yellow_cards",
            "h": [{"element": p} for p in booked if self.m["players"][p]["team"] == 1],
            "a": [{"element": p} for p in booked if self.m["players"][p]["team"] == 2],
        }]
        return [{
            "id": 1, "event": self.gw, "started": True,
            "finished": now >= self.m["duration"],
            "finished_provisional": now >= self.m["duration"],
            "minutes": now, "team_h": 1, "team_a": 2,
            "team_h_score": h, "team_a_score": a, "stats": stats,
        }]

    def live(self):
        now = self.minute()
        out = []
        for pid, p in self.m["players"].items():
            end = p["end"] if p["end"] is not None else self.m["duration"]
            mins = max(0, min(now, end) - p["start"])
            if now >= p["start"]:
                mins = max(mins, 1 if now > p["start"] else 0)
            xg = sum(x for m, q, x in self.m["shots"] if q == pid and m <= now)
            out.append({"id": pid, "stats": {
                "minutes": mins, "starts": 1 if p["starter"] else 0,
                "expected_goals": f"{xg:.2f}",
            }})
        return {"elements": out}


class Handler(BaseHTTPRequestHandler):
    sim: Sim = None

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        if path.endswith("bootstrap-static"):
            body = self.sim.bootstrap()
        elif path.endswith("fixtures"):
            body = self.sim.fixtures()
        elif "/event/" in path and path.endswith("live"):
            body = self.sim.live()
        else:
            self.send_error(404)
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        logger.debug(fmt % args)


def main():
    p = argparse.ArgumentParser(description="Local FPL API simulator")
    p.add_argument("--match", type=int, default=3754296,
                   help="StatsBomb match id (default: Arsenal 2-1 Man City)")
    p.add_argument("--gw", type=int, default=1)
    p.add_argument("--port", type=int, default=8484)
    p.add_argument("--speed", type=float, default=1.0,
                   help="match minutes per real second (default 1.0)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    match = build_match(args.match)
    logger.info(f"{match['home']} v {match['away']}: {len(match['players'])} players, "
                f"{len(match['goals'])} goals, {match['duration']}' -- "
                f"clock starts now at {args.speed} min/s")
    Handler.sim = Sim(match, args.gw, args.speed)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
