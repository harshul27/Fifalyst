"""Live in-match substitution coach.

Polls FPL on an interval, reconstructs in-match state by diffing snapshots,
produces ranked substitution recommendations plus tactical advice, and records
both the per-player trail and every recommendation made.

Usage:
    python live_coach.py                  # follow the current gameweek
    python live_coach.py --interval 120   # poll every 2 minutes (default)
    python live_coach.py --once           # single poll, print and exit
    python live_coach.py --gw 1           # a specific gameweek
    python live_coach.py --evaluate       # score logged recommendations

Accuracy note: this runs the LIVE model (13 FPL-obtainable features). Measured
on the Premier League holdout it reaches ~58% top-3 hit rate, against ~68% for
the full event-data model. See measure_live_ceiling.py.

Substitution detection needs at least two polls -- on a cold start no player can
be known to have been withdrawn yet.
"""
import argparse
import logging
import sys
import time

from pipeline.live_poller import LivePoller
from pipeline.live_store import LiveStore
from pipeline.sub_recommender import SubRecommender

logger = logging.getLogger(__name__)


def _print_match(m, side, recs, advice):
    team = m.home_team if side == "home" else m.away_team
    opp = m.away_team if side == "home" else m.home_team
    state = m.state_for(side)
    us = m.home_score if side == "home" else m.away_score
    them = m.away_score if side == "home" else m.home_score
    print(f"\n  {team} {us}-{them} {opp} - {m.minute}' "
          f"(gd {state.goal_diff:+d}, subs {state.subs_used}, "
          f"momentum {state.momentum:+.2f})")
    if not recs:
        print("    no candidates")
        return
    for i, r in enumerate(recs, 1):
        on = f" -> {r['on']}" if r.get("on") else ""
        print(f"    {i}. {r['off']} ({r['position']}, {r['minutes_played']}'){on} "
              f"p={r['sub_probability']:.1%}")
        print(f"       {' · '.join(r['reasons'])}")
    if advice:
        print(f"    tactics: {advice[0]['change']} — {advice[0]['why']}")


def run_once(gw, poller, coach, store, top_k=3, quiet=False):
    matches = poller.poll(gw)
    live = [m for m in matches if not m.finished]
    store.append_snapshot(gw, matches)

    if not live and not quiet:
        print(f"GW{gw}: no matches in progress "
              f"({len(matches)} started, all finished)")

    for m in live:
        for side in ("home", "away"):
            players = m.players_for(side)
            if not players:
                continue
            state = m.state_for(side)
            recs = coach.recommend(players, state, top_k=top_k)
            advice = coach.tactical_advice(state)
            store.log_recommendations(
                gw, m.fixture_id, side, m.minute,
                {"goal_diff": state.goal_diff, "subs_used": state.subs_used,
                 "momentum": round(state.momentum, 3)},
                recs, advice)
            if not quiet:
                _print_match(m, side, recs, advice)
    return len(live)


def main():
    p = argparse.ArgumentParser(description="Live FPL substitution coach")
    p.add_argument("--gw", type=int, help="gameweek (default: current)")
    p.add_argument("--interval", type=int, default=120, help="poll seconds (default 120)")
    p.add_argument("--once", action="store_true", help="single poll then exit")
    p.add_argument("--until-finished", action="store_true",
                   help="stop once every match that was in progress has finished")
    p.add_argument("--evaluate", action="store_true", help="score logged recommendations")
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--model", default="sub_timing_model_live",
                   help="'sub_timing_model_live' (default) or 'sub_timing_model'")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Line-buffer so output streams when redirected to a file, and force UTF-8
    # so player names with non-ASCII characters cannot kill the poller on a
    # cp1252 console (Windows default).
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except AttributeError:  # pragma: no cover - very old Python
        pass

    poller, store = LivePoller(), LiveStore()
    gw = args.gw or next((r["gw"] for r in poller.fpl.recordable_gameweeks()), 1)

    if args.evaluate:
        ev = store.evaluate(gw)
        print(f"GW{gw} recommendation sets: {ev.get('recommendation_sets', 0)}")
        print(f"evaluated against real withdrawals: {ev.get('evaluated', 0)}")
        if ev.get("hit_rate") is not None:
            print(f"hit rate: {ev['hit_rate']:.1%}")
        else:
            print("no substitutions observed yet to score against")
        return

    coach = SubRecommender(model_name=args.model)
    if coach.bundle is None:
        print(f"WARNING: model '{args.model}' not found — using heuristic fallback")
    else:
        print(f"model: {args.model} ({len(coach.bundle['features'])} features)")

    if args.once:
        run_once(gw, poller, coach, store, top_k=args.top_k)
        return

    print(f"following GW{gw}, polling every {args.interval}s (ctrl-c to stop)")
    seen_live, idle = False, 0
    try:
        while True:
            n = run_once(gw, poller, coach, store, top_k=args.top_k)
            if n:
                seen_live, idle = True, 0
            else:
                idle += 1
                logger.info("nothing in progress; still polling")
                # two consecutive idle polls after live football means done
                if args.until_finished and seen_live and idle >= 2:
                    print("\nall tracked matches finished")
                    break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")

    ev = store.evaluate(gw)
    if ev.get("evaluated"):
        print(f"\nrecommendations scored against real withdrawals: "
              f"{ev['hit_rate']:.1%} over {ev['evaluated']} sets")


if __name__ == "__main__":
    main()
