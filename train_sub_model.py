"""Train and validate the substitution timing model.

Usage:
    python train_sub_model.py              # train on extracted StatsBomb features
    python train_sub_model.py --extract    # extract corpus first (slow, downloads)
    python train_sub_model.py --holdout "La Liga"
"""
import argparse
import json
import logging

from pipeline.sub_model import train, build_impact_prior


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--extract", action="store_true", help="run StatsBomb extraction first")
    p.add_argument("--holdout", default="Premier League",
                   help="competition held out entirely from training")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.extract:
        from pipeline.statsbomb_extract import run
        run()

    report = train(holdout_competition=args.holdout)

    h, cv = report["holdout"], report["cv_mean"]
    print("\n=== TRAINING ===")
    print(f"rows {report['n_train_rows']:,} from {report['n_train_matches']:,} matches "
          f"| positive rate {report['positive_rate']:.4f}")
    print(f"grouped CV : ROC-AUC {cv['roc_auc']:.3f}  PR-AUC {cv['pr_auc']:.3f}  "
          f"Brier {cv['brier']:.4f}")
    print(f"\n=== HOLDOUT: {h['competition']} ({h['n_matches']} matches, unseen) ===")
    print(f"ROC-AUC {h['roc_auc']:.3f} | PR-AUC {h['pr_auc']:.3f} "
          f"(base rate {h['base_rate']:.4f}) | Brier {h['brier']:.4f}")
    print(f"top-1 hit {h['precision_at_1']:.1%} | top-3 hit {h['precision_at_3']:.1%}")
    print("\n=== BASELINES (PR-AUC on same holdout) ===")
    for k, v in sorted(report["baselines_on_holdout"].items(), key=lambda x: -x[1]):
        print(f"  {k:<32} {v:.3f}")
    lift = h["pr_auc"] / max(v for k, v in report["baselines_on_holdout"].items()
                             if k != "random")
    print(f"\nmodel / best-heuristic PR-AUC ratio: {lift:.2f}x")

    print("\n=== CALIBRATION (holdout) ===")
    for b in report["calibration"]:
        print(f"  bin {b['bin']}: predicted {b['mean_predicted']:.3f} "
              f"observed {b['observed']:.3f} (n={b['n']:,})")

    prior = build_impact_prior()
    if not prior.empty:
        print("\n=== IMPACT PRIOR (measured post-sub momentum swing) ===")
        print(prior.to_string(index=False))

    print("\nsaved: models/sub_timing_model.pkl, models/sub_model_report.json")


if __name__ == "__main__":
    main()
