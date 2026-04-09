"""
=============================================================================
Model Training, Tuning & Rigorous Evaluation
=============================================================================

Research-grade pipeline:
    1.  Naïve Mean Baseline (sanity check)
    2.  10-fold Cross-Validation with mean ± std
    3.  Hyperparameter tuning via RandomizedSearchCV
    4.  Statistical significance (paired t-test + Wilcoxon signed-rank)
    5.  Ablation study (drop one feature-engineering step at a time)
    6.  Learning curves (train-size vs. error)
    7.  Inference latency benchmark
    8.  Residual diagnostics (saved for graphing)
    9.  Persist best model + all artefacts
"""

import json
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from sklearn.base import clone
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.model_selection import (
    KFold, cross_validate, RandomizedSearchCV, learning_curve,
    train_test_split,
)
from sklearn.metrics import (
    mean_absolute_error, root_mean_squared_error, r2_score, make_scorer,
)

try:
    from xgboost import XGBRegressor
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    warnings.warn("xgboost not installed – skipping XGBRegressor.")

from feature_engineering import (
    engineer_features, engineer_features_ablation, NUMERIC_COLS,
    CATEGORICAL_COLS, TARGET,
)

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE     = Path(__file__).parent
DATA_DIR = BASE / "data"
OUT_DIR  = BASE / "outputs"
OUT_DIR.mkdir(exist_ok=True)

# ─── Scorers ──────────────────────────────────────────────────────────────────
neg_rmse = make_scorer(root_mean_squared_error, greater_is_better=False)
neg_mae  = make_scorer(mean_absolute_error, greater_is_better=False)

K_FOLDS = 5
SEED    = 42


# ═══════════════════════════════════════════════════════════════════════════════
#  MODEL DEFINITIONS + SEARCH SPACES
# ═══════════════════════════════════════════════════════════════════════════════
def get_models(seed=SEED):
    models = {
        "Mean Baseline": (
            DummyRegressor(strategy="mean"), {},
        ),
        "Linear Regression": (
            LinearRegression(), {},
        ),
        "Random Forest": (
            RandomForestRegressor(n_jobs=-1, random_state=seed),
            {
                "n_estimators":     [100, 200, 300, 500],
                "max_depth":        [8, 12, 16, 20, None],
                "min_samples_leaf": [1, 2, 4, 8],
                "max_features":     ["sqrt", "log2", 0.5, 0.8],
            },
        ),
        "Neural Network (MLP)": (
            MLPRegressor(activation="relu", early_stopping=True,
                         validation_fraction=0.1, random_state=seed),
            {
                "hidden_layer_sizes": [
                    (64, 32), (128, 64), (128, 64, 32),
                    (256, 128, 64), (128, 64, 32, 16),
                ],
                "learning_rate_init": [1e-4, 5e-4, 1e-3, 5e-3],
                "alpha":              [1e-5, 1e-4, 1e-3, 1e-2],
                "max_iter":           [200, 300, 500],
                "batch_size":         [32, 64, 128, 256],
            },
        ),
    }
    if HAS_XGB:
        models["XGBoost"] = (
            XGBRegressor(n_jobs=-1, random_state=seed, verbosity=0),
            {
                "n_estimators":     [100, 200, 300, 500],
                "max_depth":        [4, 6, 8, 10, 12],
                "learning_rate":    [0.01, 0.05, 0.1, 0.2],
                "subsample":        [0.6, 0.7, 0.8, 0.9, 1.0],
                "colsample_bytree": [0.6, 0.7, 0.8, 0.9, 1.0],
                "reg_alpha":        [0, 0.01, 0.1, 1.0],
                "reg_lambda":       [0.5, 1.0, 2.0, 5.0],
            },
        )
    return models


# ═══════════════════════════════════════════════════════════════════════════════
#  HYPERPARAMETER TUNING
# ═══════════════════════════════════════════════════════════════════════════════
def tune_model(name, estimator, param_dist, X, y, n_iter=10):
    if not param_dist:
        return estimator
    print(f"  [tune] {name}: {n_iter} random combos x 3-fold ...")
    tune_cv = KFold(n_splits=3, shuffle=True, random_state=SEED)
    search = RandomizedSearchCV(
        estimator, param_dist, n_iter=n_iter, cv=tune_cv,
        scoring="neg_root_mean_squared_error",
        n_jobs=-1, random_state=SEED, error_score="raise",
    )
    search.fit(X, y)
    print(f"  [tune] {name}: best CV-RMSE={-search.best_score_:.4f}")
    return search.best_estimator_


# ═══════════════════════════════════════════════════════════════════════════════
#  k-FOLD CROSS-VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════
def kfold_evaluate(models_tuned, X, y, cv):
    results = {}
    for name, model in models_tuned.items():
        print(f"  [CV] {name} …")
        cv_out = cross_validate(
            model, X, y, cv=cv,
            scoring={"MAE": neg_mae, "RMSE": neg_rmse, "R2": "r2"},
            return_train_score=False, n_jobs=-1,
        )
        results[name] = {
            "MAE_mean":  round(float(-cv_out["test_MAE"].mean()), 4),
            "MAE_std":   round(float(cv_out["test_MAE"].std()), 4),
            "RMSE_mean": round(float(-cv_out["test_RMSE"].mean()), 4),
            "RMSE_std":  round(float(cv_out["test_RMSE"].std()), 4),
            "R2_mean":   round(float(cv_out["test_R2"].mean()), 4),
            "R2_std":    round(float(cv_out["test_R2"].std()), 4),
            "fold_rmses": (-cv_out["test_RMSE"]).tolist(),
        }
        r = results[name]
        print(f"       MAE={r['MAE_mean']:.3f}+/-{r['MAE_std']:.3f}  "
              f"RMSE={r['RMSE_mean']:.3f}+/-{r['RMSE_std']:.3f}  "
              f"R2={r['R2_mean']:.4f}+/-{r['R2_std']:.4f}")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  STATISTICAL SIGNIFICANCE
# ═══════════════════════════════════════════════════════════════════════════════
def significance_tests(cv_results):
    best_name = min(cv_results, key=lambda k: cv_results[k]["RMSE_mean"])
    best_rmses = np.array(cv_results[best_name]["fold_rmses"])
    tests = {}
    for name, r in cv_results.items():
        if name == best_name:
            continue
        other = np.array(r["fold_rmses"])
        t_stat, t_p = sp_stats.ttest_rel(best_rmses, other)
        try:
            w_stat, w_p = sp_stats.wilcoxon(best_rmses, other, alternative="less")
        except ValueError:
            w_stat, w_p = float("nan"), float("nan")
        tests[name] = {
            "paired_t": {"statistic": round(float(t_stat), 4),
                         "p_value":   round(float(t_p), 6)},
            "wilcoxon": {"statistic": round(float(w_stat) if not np.isnan(w_stat) else 0, 4),
                         "p_value":   round(float(w_p) if not np.isnan(w_p) else 1, 6)},
        }
        sig = "✓" if t_p < 0.05 else "✗"
        print(f"  {best_name} vs {name}: p={t_p:.5f} {sig}")
    return {"reference": best_name, "tests": tests}


# ═══════════════════════════════════════════════════════════════════════════════
#  ABLATION STUDY
# ═══════════════════════════════════════════════════════════════════════════════
def ablation_study(df, best_model, cv):
    configs = {
        "Full pipeline":  dict(drop_haversine=False, drop_cyclical=False,
                               drop_categories=False, skip_scaling=False),
        "w/o Haversine":  dict(drop_haversine=True,  drop_cyclical=False,
                               drop_categories=False, skip_scaling=False),
        "w/o Cyclical":   dict(drop_haversine=False, drop_cyclical=True,
                               drop_categories=False, skip_scaling=False),
        "w/o Categories": dict(drop_haversine=False, drop_cyclical=False,
                               drop_categories=True,  skip_scaling=False),
        "w/o Scaling":    dict(drop_haversine=False, drop_cyclical=False,
                               drop_categories=False, skip_scaling=True),
    }
    results = {}
    for label, cfg in configs.items():
        X_a, y_a, _, _ = engineer_features_ablation(df, **cfg)
        m = clone(best_model)
        cv_out = cross_validate(m, X_a, y_a, cv=cv,
                                scoring={"MAE": neg_mae, "RMSE": neg_rmse, "R2": "r2"},
                                n_jobs=-1)
        mae  = round(float(-cv_out["test_MAE"].mean()), 4)
        rmse = round(float(-cv_out["test_RMSE"].mean()), 4)
        r2   = round(float(cv_out["test_R2"].mean()), 4)
        results[label] = {"MAE": mae, "RMSE": rmse, "R2": r2}
        print(f"  {label:20s}  MAE={mae:.4f}  RMSE={rmse:.4f}  R2={r2:.4f}")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  LEARNING CURVES
# ═══════════════════════════════════════════════════════════════════════════════
def compute_learning_curves(best_model, X, y, cv=None):
    lc_cv = KFold(n_splits=5, shuffle=True, random_state=SEED)
    train_sizes_abs, train_scores, test_scores = learning_curve(
        best_model, X, y, cv=lc_cv,
        train_sizes=np.linspace(0.1, 1.0, 10),
        scoring="neg_root_mean_squared_error",
        n_jobs=-1, random_state=SEED,
    )
    return {
        "train_sizes":     train_sizes_abs.tolist(),
        "train_rmse_mean": (-train_scores.mean(axis=1)).round(4).tolist(),
        "train_rmse_std":  train_scores.std(axis=1).round(4).tolist(),
        "test_rmse_mean":  (-test_scores.mean(axis=1)).round(4).tolist(),
        "test_rmse_std":   test_scores.std(axis=1).round(4).tolist(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  INFERENCE LATENCY
# ═══════════════════════════════════════════════════════════════════════════════
def benchmark_latency(models_tuned, X_single, n_warmup=50, n_runs=500):
    latencies = {}
    for name, model in models_tuned.items():
        for _ in range(n_warmup):
            model.predict(X_single)
        times = []
        for _ in range(n_runs):
            t0 = time.perf_counter()
            model.predict(X_single)
            times.append((time.perf_counter() - t0) * 1000)
        arr = np.array(times)
        latencies[name] = {
            "mean_ms": round(float(arr.mean()), 4),
            "std_ms":  round(float(arr.std()), 4),
            "p50_ms":  round(float(np.percentile(arr, 50)), 4),
            "p99_ms":  round(float(np.percentile(arr, 99)), 4),
        }
        print(f"  {name:25s}  mean={latencies[name]['mean_ms']:.3f}ms  "
              f"p99={latencies[name]['p99_ms']:.3f}ms")
    return latencies


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════
def train_and_compare(csv_path=None):
    csv_path = csv_path or DATA_DIR / "delivery_dataset.csv"
    df = pd.read_csv(csv_path)
    print(f"[train] Loaded {len(df):,} rows")

    X, y, transformer, feature_names = engineer_features(df)
    cv = KFold(n_splits=K_FOLDS, shuffle=True, random_state=SEED)

    # Phase 1: Hyperparameter tuning
    print("\n" + "=" * 60)
    print("PHASE 1 -- Hyperparameter Tuning")
    print("=" * 60)
    raw = get_models(SEED)
    models_tuned = {}
    best_params = {}
    for name, (est, params) in raw.items():
        tuned = tune_model(name, est, params, X, y)
        models_tuned[name] = tuned
        if params:
            best_params[name] = {
                k: (int(v) if isinstance(v, (np.integer,)) else v)
                for k, v in tuned.get_params().items() if k in params
            }

    # Phase 2: k-fold CV
    print("\n" + "=" * 60)
    print(f"PHASE 2 -- {K_FOLDS}-Fold Cross-Validation")
    print("=" * 60)
    cv_results = kfold_evaluate(models_tuned, X, y, cv)

    non_baseline = {k: v for k, v in cv_results.items() if k != "Mean Baseline"}
    best_name = min(non_baseline, key=lambda k: non_baseline[k]["RMSE_mean"])
    print(f"\n*  Best: {best_name}  "
          f"RMSE={cv_results[best_name]['RMSE_mean']:.4f}"
          f"+/-{cv_results[best_name]['RMSE_std']:.4f}")

    # Phase 3: Significance
    print("\n" + "=" * 60)
    print("PHASE 3 -- Statistical Significance")
    print("=" * 60)
    sig = significance_tests(non_baseline)

    # Phase 4: Ablation
    print("\n" + "=" * 60)
    print("PHASE 4 -- Ablation Study")
    print("=" * 60)
    abl = ablation_study(df, models_tuned[best_name], cv)

    # Phase 5: Learning curves
    print("\n" + "=" * 60)
    print("PHASE 5 -- Learning Curves")
    print("=" * 60)
    lc = compute_learning_curves(models_tuned[best_name], X, y, cv)
    print(f"  Test RMSE @ 100%: {lc['test_rmse_mean'][-1]:.4f}")

    # Phase 6: Latency
    print("\n" + "=" * 60)
    print("PHASE 6 -- Inference Latency")
    print("=" * 60)
    # Ensure all models are fitted (baseline/linear have no tuning step)
    for name, model in models_tuned.items():
        try:
            model.predict(X[:1])
        except Exception:
            model.fit(X, y)
    lat = benchmark_latency(models_tuned, X[:1])

    # Phase 7: Holdout predictions + save
    print("\n" + "=" * 60)
    print("PHASE 7 -- Final Fit & Saving")
    print("=" * 60)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2,
                                                random_state=SEED)
    predictions = {}
    holdout = {}
    for name, model in models_tuned.items():
        m = clone(model)
        t0 = time.perf_counter()
        m.fit(X_tr, y_tr)
        elapsed = round(time.perf_counter() - t0, 2)
        yp = m.predict(X_te)
        holdout[name] = {
            "MAE":  round(float(mean_absolute_error(y_te, yp)), 4),
            "RMSE": round(float(root_mean_squared_error(y_te, yp)), 4),
            "R2":   round(float(r2_score(y_te, yp)), 4),
            "train_time_s": elapsed,
        }
        predictions[name] = yp.tolist()

    # Refit best on everything
    best_full = clone(models_tuned[best_name])
    best_full.fit(X, y)

    # Save
    joblib.dump(best_full,     OUT_DIR / "best_model.joblib")
    joblib.dump(transformer,   OUT_DIR / "transformer.joblib")
    joblib.dump(feature_names, OUT_DIR / "feature_names.joblib")
    for name, model in models_tuned.items():
        safe = name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        joblib.dump(model, OUT_DIR / f"model_{safe}.joblib")

    pred_df = pd.DataFrame(predictions)
    pred_df["actual"] = y_te
    pred_df.to_csv(OUT_DIR / "test_predictions.csv", index=False)

    imps = {}
    for name, model in models_tuned.items():
        if hasattr(model, "feature_importances_"):
            imps[name] = dict(zip(feature_names,
                                  model.feature_importances_.round(4).tolist()))
    if imps:
        with open(OUT_DIR / "feature_importances.json", "w") as f:
            json.dump(imps, f, indent=2)

    all_results = {
        "cv_results":      cv_results,
        "holdout_results": holdout,
        "best_model":      best_name,
        "best_params":     best_params,
        "significance":    sig,
        "ablation":        abl,
        "learning_curves": lc,
        "latency":         lat,
    }
    for m in all_results["cv_results"].values():
        m["fold_rmses"] = [round(float(v), 4) for v in m["fold_rmses"]]

    with open(OUT_DIR / "results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    with open(OUT_DIR / "feature_names.json", "w") as f:
        json.dump(feature_names, f)

    print(f"\n[train] All artefacts -> {OUT_DIR.resolve()}")
    return all_results


if __name__ == "__main__":
    train_and_compare()
