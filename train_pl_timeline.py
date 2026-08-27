"""Train the PL 2020/21-2024/25 substitution-timing model (timeline features).

Data: data/pl_timeline/features/*.parquet, built by pipeline/pl_timeline_extract.py
from schochastics/football-data (timed incidents) + vaastav/Fantasy-Premier-League
(lineups, minutes, positions, workload).

Split: within EACH season, 70% of matches train / 30% test (grouped by match, so
no match ever contributes rows to both sides). The test 30% is never touched
during training or calibration; predictions on it are scored against the real
substitutions those coaches actually made.

Usage:
    python train_pl_timeline.py             # train + evaluate + save
    python train_pl_timeline.py --extract   # rebuild the dataset first
"""
import argparse
import json
import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

logger = logging.getLogger(__name__)

DATA = Path("data/pl_timeline/features")
MODEL_DIR = Path("models")
MODEL_NAME = "sub_timing_model_pl"
TARGET = "subbed_off_next5"
TRAIN_FRAC, SEED = 0.7, 42

FEATURES = [
    "minute", "minutes_played", "is_starter", "is_home", "has_card",
    "goal_diff", "total_goals", "goals_for_w", "goals_against_w",
    "subs_used", "opp_subs_used",
    "prev_minutes", "prev3_minutes", "days_rest",
    "pos_DEF", "pos_MID", "pos_FWD",
]


def load() -> pd.DataFrame:
    shards = sorted(DATA.glob("*.parquet"))
    if not shards:
        raise FileNotFoundError("no data - run: python -m pipeline.pl_timeline_extract")
    df = pd.concat([pd.read_parquet(s) for s in shards], ignore_index=True)
    for p in ("DEF", "MID", "FWD"):
        df[f"pos_{p}"] = (df["position"] == p).astype(int)
    df[FEATURES] = df[FEATURES].replace([np.inf, -np.inf], np.nan).fillna(0)
    return df


def split_70_30(df: pd.DataFrame):
    """70/30 by match within each season, so every season is represented on
    both sides and no match leaks across the boundary."""
    rng = np.random.RandomState(SEED)
    test_ids = []
    for _, g in df.groupby("season"):
        mids = np.array(sorted(g["match_id"].unique()))
        rng.shuffle(mids)
        test_ids.extend(mids[int(len(mids) * TRAIN_FRAC):])
    test_ids = set(test_ids)
    mask = df["match_id"].isin(test_ids)
    return df[~mask].copy(), df[mask].copy()


def _precision_at_k(d: pd.DataFrame, proba: np.ndarray, k: int) -> float:
    """Per (match, team, decision minute) with a real sub in the label window:
    was a truly-substituted player among the top-k the model ranked?"""
    d = d.copy()
    d["_p"] = proba
    hits = total = 0
    for _, g in d.groupby(["match_id", "team", "minute"]):
        if g[TARGET].sum() == 0:
            continue
        total += 1
        hits += int(g.nlargest(k, "_p")[TARGET].sum() > 0)
    return hits / total if total else float("nan")


def _evaluate(d: pd.DataFrame, proba: np.ndarray) -> dict:
    y = d[TARGET].values
    return {
        "n_rows": int(len(d)), "n_matches": int(d["match_id"].nunique()),
        "base_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, proba)),
        "pr_auc": float(average_precision_score(y, proba)),
        "brier": float(brier_score_loss(y, proba)),
        "precision_at_1": float(_precision_at_k(d, proba, 1)),
        "precision_at_3": float(_precision_at_k(d, proba, 3)),
    }


def _calibration(y: np.ndarray, p: np.ndarray, bins: int = 5) -> list:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[-1] += 1e-9
    out = []
    for i in range(bins):
        m = (p >= edges[i]) & (p < edges[i + 1])
        if m.sum():
            out.append({"bin": i, "n": int(m.sum()),
                        "mean_predicted": float(p[m].mean()),
                        "observed": float(y[m].mean())})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true", help="rebuild dataset first")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.extract:
        from pipeline.pl_timeline_extract import run
        run()

    df = load()
    train_df, test_df = split_70_30(df)
    X, y = train_df[FEATURES], train_df[TARGET].values
    groups = train_df["match_id"].values

    # Grouped 5-fold CV on the training 70% (model-selection sanity check).
    cv_rows = []
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06,
                                           max_leaf_nodes=31, l2_regularization=1.0,
                                           random_state=SEED)
        m.fit(X.iloc[tr], y[tr])
        p = m.predict_proba(X.iloc[te])[:, 1]
        cv_rows.append({"roc_auc": roc_auc_score(y[te], p),
                        "pr_auc": average_precision_score(y[te], p),
                        "brier": brier_score_loss(y[te], p)})
    cv = pd.DataFrame(cv_rows)

    base = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06,
                                          max_leaf_nodes=31, l2_regularization=1.0,
                                          random_state=SEED)
    model = CalibratedClassifierCV(base, method="isotonic", cv=3)
    model.fit(X, y)

    # ---- score the untouched 30% against the coaches' real decisions ----
    p_test = model.predict_proba(test_df[FEATURES])[:, 1]
    overall = _evaluate(test_df, p_test)
    per_season = {}
    for s, g in test_df.groupby("season"):
        per_season[s] = _evaluate(g, p_test[test_df["season"] == s])

    baselines = {
        "minutes_played": float(average_precision_score(test_df[TARGET],
                                                        test_df["minutes_played"])),
        "late_and_level(minute)": float(average_precision_score(test_df[TARGET],
                                                                test_df["minute"])),
        "random": float(test_df[TARGET].mean()),
    }

    report = {
        "data": {"seasons": sorted(df["season"].unique().tolist()),
                 "n_rows": int(len(df)), "n_matches": int(df["match_id"].nunique()),
                 "split": f"{TRAIN_FRAC:.0%} train / {1-TRAIN_FRAC:.0%} test by match, per season",
                 "seed": SEED},
        "n_train_rows": int(len(train_df)), "n_train_matches": int(train_df["match_id"].nunique()),
        "cv_mean": {k: float(cv[k].mean()) for k in cv.columns},
        "cv_std": {k: float(cv[k].std()) for k in cv.columns},
        "test": overall, "test_per_season": per_season,
        "baselines_on_test": baselines,
        "calibration": _calibration(test_df[TARGET].values, p_test),
        "features": FEATURES,
        "sources": ["schochastics/football-data (ODC-BY): timed incidents",
                    "vaastav/Fantasy-Premier-League: lineups, minutes, positions"],
    }

    MODEL_DIR.mkdir(exist_ok=True)
    with open(MODEL_DIR / f"{MODEL_NAME}.pkl", "wb") as f:
        pickle.dump({"model": model, "features": FEATURES}, f)
    (MODEL_DIR / f"{MODEL_NAME}_report.json").write_text(json.dumps(report, indent=2))

    print(f"\n=== TRAIN (70% = {report['n_train_matches']:,} matches, "
          f"{report['n_train_rows']:,} rows) ===")
    print(f"grouped CV : ROC-AUC {report['cv_mean']['roc_auc']:.3f}  "
          f"PR-AUC {report['cv_mean']['pr_auc']:.3f}  Brier {report['cv_mean']['brier']:.4f}")
    print(f"\n=== TEST (30% = {overall['n_matches']:,} unseen matches) ===")
    print(f"ROC-AUC {overall['roc_auc']:.3f} | PR-AUC {overall['pr_auc']:.3f} "
          f"(base rate {overall['base_rate']:.4f}) | Brier {overall['brier']:.4f}")
    print(f"top-1 hit {overall['precision_at_1']:.1%} | top-3 hit {overall['precision_at_3']:.1%}")
    print("\nper season (test matches only):")
    for s, r in sorted(per_season.items()):
        print(f"  {s}: ROC {r['roc_auc']:.3f}  PR {r['pr_auc']:.3f}  "
              f"top1 {r['precision_at_1']:.1%}  top3 {r['precision_at_3']:.1%}  "
              f"({r['n_matches']} matches)")
    print("\nbaselines (PR-AUC on test):")
    for k, v in sorted(baselines.items(), key=lambda x: -x[1]):
        print(f"  {k:<28} {v:.3f}")
    print("\ncalibration (test):")
    for b in report["calibration"]:
        print(f"  bin {b['bin']}: predicted {b['mean_predicted']:.3f} "
              f"observed {b['observed']:.3f} (n={b['n']:,})")
    print(f"\nsaved: models/{MODEL_NAME}.pkl, models/{MODEL_NAME}_report.json")


if __name__ == "__main__":
    main()
