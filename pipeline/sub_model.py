"""Substitution recommendation model.

Two layers, deliberately separated because they are validated differently:

1. TIMING MODEL (supervised, rigorously validatable)
   P(player is substituted off within the next 5 minutes | match state).
   Learned from real coach decisions in StatsBomb open data.
   What it captures: fatigue proxies, booking risk, fading involvement,
   game state, momentum. What it does NOT claim: that coaches were optimal.

2. IMPACT LAYER (weaker evidence, applied as a re-ranking prior)
   Measured post-substitution momentum swing, aggregated by context
   (game state x position x minute bucket). Used to re-rank candidates the
   timing model already considers likely -- never to invent candidates.

Validation is by GROUPED split on match_id (no match leaks across folds) plus a
cross-competition holdout, and is scored against explicit heuristic baselines.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss
from sklearn.model_selection import GroupKFold

logger = logging.getLogger(__name__)

DATA = Path("data/statsbomb")
MODEL_DIR = Path("models")

FEATURES = [
    "minute", "minutes_played", "is_starter", "has_card",
    "actions_total", "actions_recent", "action_rate", "recent_rate",
    "rate_decline", "involvement_anomaly", "pass_acc", "pass_acc_recent",
    "pressures_recent", "duels_recent", "xg_total", "avg_x",
    "goal_diff", "subs_used", "team_xg_w", "opp_xg_w", "momentum",
    "possession_w", "field_tilt_w", "shots_w", "opp_shots_w",
    "pos_DEF", "pos_MID", "pos_FWD",
]
TARGET = "subbed_off_next5"


def load_features() -> pd.DataFrame:
    shards = sorted((DATA / "features").glob("*.parquet"))
    if not shards:
        raise FileNotFoundError("no extracted features - run pipeline/statsbomb_extract.py")
    df = pd.concat([pd.read_parquet(s) for s in shards], ignore_index=True)
    return _prep(df)


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    # Substitution risk vs involvement is U-shaped: coaches withdraw both faded
    # players AND heavily-involved ones, while steady players stay on. Distance
    # from the player's own baseline expresses that; the raw ratio cannot.
    df["involvement_anomaly"] = (df["rate_decline"] - 1.0).abs()
    for p in ("DEF", "MID", "FWD"):
        df[f"pos_{p}"] = (df["position"] == p).astype(int)
    df = df.replace([np.inf, -np.inf], np.nan)
    df[FEATURES] = df[FEATURES].fillna(0)
    return df


# ---------------- baselines (what the model must beat) ----------------
def baseline_scores(df: pd.DataFrame) -> Dict[str, float]:
    """Heuristics a coach or a naive system would already use."""
    y = df[TARGET].values
    return {
        "minutes_played": average_precision_score(y, df["minutes_played"]),
        "fatigue_proxy(-rate_decline)": average_precision_score(y, -df["rate_decline"]),
        "low_recent_involvement": average_precision_score(y, -df["recent_rate"]),
        "random": df[TARGET].mean(),
    }


# ---------------- training ----------------
def train(df: Optional[pd.DataFrame] = None, holdout_competition: str = "Premier League",
          seed: int = 0, features: Optional[list] = None,
          model_name: str = "sub_timing_model") -> dict:
    df = load_features() if df is None else df
    features = features or FEATURES

    # Cross-competition holdout: never seen during training or calibration.
    hold = df[df["competition"] == holdout_competition]
    train_df = df[df["competition"] != holdout_competition]
    if hold.empty:
        logger.warning(f"no holdout rows for {holdout_competition}; using random 20% of matches")
        mids = df["match_id"].drop_duplicates().sample(frac=0.2, random_state=seed)
        hold = df[df["match_id"].isin(mids)]
        train_df = df[~df["match_id"].isin(mids)]

    X, y, groups = train_df[features], train_df[TARGET].values, train_df["match_id"].values

    # Grouped CV by match so no match appears in both sides of a fold.
    cv_rows = []
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=5).split(X, y, groups)):
        m = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
            l2_regularization=1.0, random_state=seed)
        m.fit(X.iloc[tr], y[tr])
        p = m.predict_proba(X.iloc[te])[:, 1]
        cv_rows.append({
            "fold": fold,
            "roc_auc": roc_auc_score(y[te], p),
            "pr_auc": average_precision_score(y[te], p),
            "brier": brier_score_loss(y[te], p),
            "precision_at_1": _precision_at_k(train_df.iloc[te], p, k=1),
        })
    cv = pd.DataFrame(cv_rows)

    # Final model, probability-calibrated (recommendation confidence must mean something).
    base = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
        l2_regularization=1.0, random_state=seed)
    model = CalibratedClassifierCV(base, method="isotonic", cv=3)
    model.fit(X, y)

    ph = model.predict_proba(hold[features])[:, 1]
    holdout = {
        "competition": holdout_competition,
        "n_rows": int(len(hold)), "n_matches": int(hold["match_id"].nunique()),
        "base_rate": float(hold[TARGET].mean()),
        "roc_auc": float(roc_auc_score(hold[TARGET], ph)),
        "pr_auc": float(average_precision_score(hold[TARGET], ph)),
        "brier": float(brier_score_loss(hold[TARGET], ph)),
        "precision_at_1": float(_precision_at_k(hold, ph, k=1)),
        "precision_at_3": float(_precision_at_k(hold, ph, k=3)),
    }

    report = {
        "cv_mean": {k: float(cv[k].mean()) for k in
                    ("roc_auc", "pr_auc", "brier", "precision_at_1")},
        "cv_std": {k: float(cv[k].std()) for k in ("roc_auc", "pr_auc")},
        "holdout": holdout,
        "baselines_on_holdout": {k: float(v) for k, v in baseline_scores(hold).items()},
        "n_train_rows": int(len(train_df)),
        "n_train_matches": int(train_df["match_id"].nunique()),
        "positive_rate": float(y.mean()),
        "calibration": _calibration_table(hold[TARGET].values, ph),
        "features": features,
        "model_name": model_name,
    }
    _save(model, report, features=features, name=model_name)
    return report


def _precision_at_k(df: pd.DataFrame, proba: np.ndarray, k: int = 1) -> float:
    """Per decision point: is a truly-substituted player in the top-k ranked?

    This is the metric that matches how the model is actually used -- ranking
    the players on the pitch right now, not scoring rows in isolation.
    """
    d = df.copy()
    d["_p"] = proba
    hits, total = 0, 0
    for _, g in d.groupby(["match_id", "team", "minute"]):
        if g[TARGET].sum() == 0:
            continue
        total += 1
        if g.nlargest(k, "_p")[TARGET].sum() > 0:
            hits += 1
    return hits / total if total else float("nan")


def _calibration_table(y: np.ndarray, p: np.ndarray, bins: int = 5) -> list:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[-1] += 1e-9
    out = []
    for i in range(bins):
        m = (p >= edges[i]) & (p < edges[i + 1])
        if m.sum() == 0:
            continue
        out.append({"bin": i, "n": int(m.sum()),
                    "mean_predicted": float(p[m].mean()),
                    "observed": float(y[m].mean())})
    return out


# ---------------- impact layer ----------------
def build_impact_prior() -> pd.DataFrame:
    """Average measured momentum swing after real subs, by context.

    ponytail: observational and confounded (coaches sub when already chasing a
    game), so this is a re-ranking prior only, never a causal claim. Upgrade
    path: matched control sampling on pre-sub state.
    """
    shards = sorted((DATA / "subs").glob("*.parquet"))
    if not shards:
        return pd.DataFrame()
    s = pd.concat([pd.read_parquet(x) for x in shards], ignore_index=True)
    s["state"] = np.select(
        [s["goal_diff"] > 0, s["goal_diff"] == 0], ["leading", "level"], "trailing")
    s["minute_bucket"] = pd.cut(s["minute"], [0, 60, 70, 80, 95],
                                labels=["<60", "60-70", "70-80", "80+"])
    prior = (s.groupby(["state", "minute_bucket"], observed=True)
               .agg(n=("momentum_delta", "size"),
                    momentum_delta=("momentum_delta", "mean"),
                    xg_delta=("xg_delta", "mean"),
                    goals_for_after=("goals_for_after", "mean"))
               .reset_index())
    prior.to_parquet(MODEL_DIR / "impact_prior.parquet", index=False)
    return prior


def _save(model, report: dict, features: Optional[list] = None,
          name: str = "sub_timing_model"):
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    import pickle
    with open(MODEL_DIR / f"{name}.pkl", "wb") as f:
        pickle.dump({"model": model, "features": features or FEATURES}, f)
    (MODEL_DIR / f"{name}_report.json").write_text(json.dumps(report, indent=2))
    logger.info(f"✓ saved models/{name}.pkl + report")


def load_model(name: str = "sub_timing_model"):
    """Load a trained bundle. Use name='sub_timing_model_live' for the
    FPL-feedable model (13 features, see measure_live_ceiling.py)."""
    import pickle
    with open(MODEL_DIR / f"{name}.pkl", "rb") as f:
        return pickle.load(f)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rep = train()
    print(json.dumps({k: rep[k] for k in ("cv_mean", "holdout", "baselines_on_holdout")}, indent=2))
    print(build_impact_prior().to_string(index=False))
