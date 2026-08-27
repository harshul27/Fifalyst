"""Train the live (FPL-feedable) substitution model.

Uses only the 13 features a live FPL feed can supply -- see
measure_live_ceiling.py for the measured cost of that restriction
(ROC 0.855 vs 0.864, top-3 58.4% vs 67.7% on the Premier League holdout).

Saves to models/sub_timing_model_live.pkl, leaving the production
event-data model untouched.

Usage:
    python train_live_model.py                    # cross-competition holdout
    python train_live_model.py --holdout none     # PL-only corpus: random 20% of matches
"""
import argparse
import logging
from pipeline.sub_model import train
from measure_live_ceiling import LIVE_CORE

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--holdout", default="Premier League",
                   help="competition held out entirely from training; a name not "
                        "present in the corpus falls back to a random 20% match holdout")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    r = train(features=LIVE_CORE, model_name="sub_timing_model_live",
              holdout_competition=args.holdout)
    h = r["holdout"]
    print(f"\nlive model | {len(LIVE_CORE)} features | trained on {r['n_train_matches']:,} matches")
    print(f"holdout {h['competition']}: ROC {h['roc_auc']:.3f} PR {h['pr_auc']:.3f} "
          f"top1 {h['precision_at_1']:.1%} top3 {h['precision_at_3']:.1%}")
