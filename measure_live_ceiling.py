"""Measure the accuracy ceiling of a LIVE (FPL-fed) substitution model.

The production model uses 28 features derived from full event data. A live FPL
feed cannot supply all of them. This script retrains on only the subsets that
are actually obtainable live and reports the same Premier League holdout
metrics, so the cost of going live is measured rather than guessed.

Feature availability from FPL (polling event/{gw}/live/ and diffing snapshots):

  AVAILABLE                     source
    minute                      fixture clock
    minutes_played              stats.minutes
    is_starter                  stats.starts
    has_card                    stats.yellow_cards / red_cards
    xg_total                    stats.expected_goals
    goal_diff                   fixture score
    subs_used                   inferred: minutes stop advancing mid-match
    team_xg_w / opp_xg_w        team xG delta between snapshots
    momentum                    derived from the two above
    pos_DEF / pos_MID / pos_FWD element_type

  PROXY ONLY (semantics differ from training)
    actions_* / *_rate          StatsBomb counts every event; FPL exposes only
    rate_decline                counting stats (tackles, recoveries, CBI...).
    involvement_anomaly         A delta-based proxy is possible but is NOT the
                                same quantity the model trained on.

  UNAVAILABLE
    pass_acc, pass_acc_recent   FPL has no pass data
    pressures_recent            not published
    duels_recent                not published
    avg_x, field_tilt_w         no spatial data at all
    possession_w                not published
    shots_w, opp_shots_w        not published

Note: the ICT family (influence/creativity/threat) is also unavailable live --
FPL publishes it only after a gameweek is finalised.
"""
import json
import logging

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from pipeline.sub_model import (FEATURES, TARGET, _calibration_table,
                                _precision_at_k, baseline_scores, load_features)

logger = logging.getLogger(__name__)

LIVE_CORE = [
    "minute", "minutes_played", "is_starter", "has_card", "xg_total",
    "goal_diff", "subs_used", "team_xg_w", "opp_xg_w", "momentum",
    "pos_DEF", "pos_MID", "pos_FWD",
]
INVOLVEMENT_PROXY = [
    "actions_total", "actions_recent", "action_rate", "recent_rate",
    "rate_decline", "involvement_anomaly",
]
SUBSETS = {
    "full (event data, production)": FEATURES,
    "live + involvement proxy": LIVE_CORE + INVOLVEMENT_PROXY,
    "live core only": LIVE_CORE,
}


def evaluate(df: pd.DataFrame, feats: list, holdout: str, seed: int = 0) -> dict:
    """Same protocol as production training: calibrated fit, unseen-competition eval."""
    hold = df[df["competition"] == holdout]
    train = df[df["competition"] != holdout]

    base = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
        l2_regularization=1.0, random_state=seed)
    model = CalibratedClassifierCV(base, method="isotonic", cv=3)
    model.fit(train[feats], train[TARGET].values)

    p = model.predict_proba(hold[feats])[:, 1]
    y = hold[TARGET].values
    return {
        "n_features": len(feats),
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "precision_at_1": float(_precision_at_k(hold, p, k=1)),
        "precision_at_3": float(_precision_at_k(hold, p, k=3)),
        "calibration": _calibration_table(y, p),
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    holdout = "Premier League"
    df = load_features()
    hold = df[df["competition"] == holdout]
    print(f"corpus {len(df):,} rows | holdout {holdout}: "
          f"{hold['match_id'].nunique()} matches, {len(hold):,} rows, "
          f"base rate {hold[TARGET].mean():.4f}\n")

    results = {}
    for name, feats in SUBSETS.items():
        logger.info(f"training: {name} ({len(feats)} features)")
        results[name] = evaluate(df, feats, holdout)

    full = results["full (event data, production)"]
    print(f"\n{'variant':<32}{'feat':>5}{'ROC':>8}{'PR':>8}{'top1':>8}{'top3':>8}{'Brier':>9}")
    print("-" * 78)
    for name, r in results.items():
        print(f"{name:<32}{r['n_features']:>5}{r['roc_auc']:>8.3f}{r['pr_auc']:>8.3f}"
              f"{r['precision_at_1']:>8.1%}{r['precision_at_3']:>8.1%}{r['brier']:>9.4f}")

    print(f"\nretained vs full event data:")
    for name, r in results.items():
        if name.startswith("full"):
            continue
        print(f"  {name:<30} ROC {r['roc_auc'] / full['roc_auc']:.1%}  "
              f"PR {r['pr_auc'] / full['pr_auc']:.1%}  "
              f"top3 {r['precision_at_3'] / full['precision_at_3']:.1%}")

    bl = baseline_scores(hold)
    best_bl = max(v for k, v in bl.items() if k != "random")
    print(f"\nbest heuristic baseline PR-AUC: {best_bl:.3f}")
    for name, r in results.items():
        print(f"  {name:<30} {r['pr_auc'] / best_bl:.2f}x baseline")

    with open("models/live_ceiling_report.json", "w") as f:
        json.dump({"holdout": holdout, "results": results, "baselines": bl}, f, indent=2)
    print("\nsaved models/live_ceiling_report.json")
    print("NOTE: production model at models/sub_timing_model.pkl is untouched.")


if __name__ == "__main__":
    main()
