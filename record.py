"""Record Premier League 2026/27 gameweek data.

Usage:
    python record.py                # record every played GW not yet final
    python record.py --gw 1         # record a single gameweek
    python record.py --all          # re-record everything (force refresh)
    python record.py --fbref        # add FBref tactical enrichment (slow, scrapes)
    python record.py --status       # show what's recorded

Cron-friendly: run it after each gameweek (or nightly) to append the season.
"""
import argparse
import asyncio
import logging

from orchestrator import SeasonOrchestrator


async def _run(args):
    orch = SeasonOrchestrator(use_fbref=args.fbref)

    if args.status:
        s = orch.status()
        print(f"recorded gameweeks: {s['recorded_gameweeks']}")
        print(f"final gameweeks:    {s['final_gameweeks']}")
        return

    if args.gw:
        rec = next((r for r in orch.fpl.recordable_gameweeks() if r["gw"] == args.gw), None)
        result = await orch.record_gameweek(args.gw, final=bool(rec and rec["final"]))
        print(result)
        return

    result = await orch.run_season_update(force=args.all)
    for r in result["recorded"]:
        print(f"  GW{r['gw']}: {r['players']} players, {r['teams']} teams, final={r.get('final')}")
    print(f"skipped (already final): {result['skipped']}")


def main():
    p = argparse.ArgumentParser(description="Record PL 2026/27 gameweek stats")
    p.add_argument("--gw", type=int, help="record a single gameweek (1-38)")
    p.add_argument("--all", action="store_true", help="force re-record every played gameweek")
    p.add_argument("--fbref", action="store_true", help="add FBref tactical enrichment (slow)")
    p.add_argument("--status", action="store_true", help="show recorded gameweeks and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
