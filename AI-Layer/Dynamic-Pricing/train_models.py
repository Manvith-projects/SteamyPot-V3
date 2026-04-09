"""
train_models.py
===============
Trains and evaluates four model families for TWO tasks:

  1. **Regression** -- predict the continuous surge_multiplier [1.0, 2.5].
  2. **Classification** -- detect peak-hour periods (is_peak_hour 0/1).

Models compared
---------------
  * Linear Regression / Logistic Regression  (baseline)
  * Random Forest Regressor / Classifier
  * XGBoost Regressor / Classifier
  * Gradient Boosting Regressor / Classifier

Business reasoning
------------------
  * Linear models provide an interpretable, auditable baseline -- important
    for pricing transparency and regulatory compliance.
  * Ensemble tree models (RF, XGB, GB) capture non-linear demand-supply
    interactions and are production-proven in pricing engines.
  * Training both regression AND classification gives the business two
    levers: a continuous surge multiplier *and* a binary peak-hour flag
    that can trigger different UX flows (e.g., "High demand in your area").

Evaluation
----------
  * Regression : MAE, RMSE, R-squared  (5-fold cross-validation)
  * Classification : Accuracy, F1-score  (5-fold cross-validation)
  * All results persisted to JSON for downstream comparison & reporting.
"""

import os
import json
import time
import warnings
import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import cross_validate, StratifiedKFold, KFold
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.ensemble import (
    RandomForestRegressor, RandomForestClassifier,
    GradientBoostingRegressor, GradientBoostingClassifier,
)

# XGBoost ------------------------------------------------------------------
try:
    from xgboost import XGBRegressor, XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("[train_models] WARNING: xgboost not installed -- skipping XGB models.")

from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    accuracy_score, f1_score, make_scorer,
)

warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED = 42
K_FOLDS = 5
OUTPUT_DIR = "outputs"

# ---------------------------------------------------------------------------
# Model registries
# ---------------------------------------------------------------------------

def _regression_models():
    """Return a dict of {name: estimator} for the regression task."""
    models = {
        "Linear Regression": LinearRegression(),
        "Random Forest": RandomForestRegressor(
            n_estimators=300, max_depth=12, min_samples_leaf=5,
            n_jobs=-1, random_state=SEED,
        ),
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=300, max_depth=6, learning_rate=0.08,
            subsample=0.8, random_state=SEED,
        ),
    }
    if HAS_XGB:
        models["XGBoost"] = XGBRegressor(
            n_estimators=400, max_depth=7, learning_rate=0.06,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0,
            random_state=SEED, verbosity=0,
        )
    return models


def _classification_models():
    """Return a dict of {name: estimator} for the peak-hour detection task."""
    models = {
        "Logistic Regression": LogisticRegression(
            max_iter=1000, random_state=SEED,
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=300, max_depth=12, min_samples_leaf=5,
            n_jobs=-1, random_state=SEED,
        ),
        "Gradient Boosting": GradientBoostingClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.08,
            subsample=0.8, random_state=SEED,
        ),
    }
    if HAS_XGB:
        models["XGBoost"] = XGBClassifier(
            n_estimators=400, max_depth=7, learning_rate=0.06,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0,
            random_state=SEED, verbosity=0, use_label_encoder=False,
            eval_metric="logloss",
        )
    return models


# ---------------------------------------------------------------------------
# Cross-validation runner  (regression)
# ---------------------------------------------------------------------------

def train_regression(X: np.ndarray, y: np.ndarray):
    """
    5-fold CV for each regression model.

    Returns
    -------
    results : dict  {model_name: {mae, rmse, r2, train_time_s}}
    best_name : str
    best_model : fitted estimator (re-fit on full data)
    """
    kf = KFold(n_splits=K_FOLDS, shuffle=True, random_state=SEED)
    scoring = {
        "mae": make_scorer(mean_absolute_error, greater_is_better=False),
        "rmse": make_scorer(mean_squared_error, greater_is_better=False),
        "r2": "r2",
    }

    results = {}
    models = _regression_models()
    print(f"\n{'='*60}")
    print(f"  REGRESSION -- Surge Multiplier Prediction  ({K_FOLDS}-fold CV)")
    print(f"{'='*60}")

    for name, est in models.items():
        t0 = time.time()
        cv = cross_validate(est, X, y, cv=kf, scoring=scoring,
                            return_train_score=False, n_jobs=-1)
        elapsed = time.time() - t0

        mae  = -cv["test_mae"].mean()
        rmse = np.sqrt(-cv["test_rmse"].mean())
        r2   = cv["test_r2"].mean()

        results[name] = {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "r2": round(r2, 4),
            "mae_std": round(-cv["test_mae"].std(), 4),
            "rmse_std": round(np.sqrt(-cv["test_rmse"]).std(), 4),
            "r2_std": round(cv["test_r2"].std(), 4),
            "train_time_s": round(elapsed, 2),
        }

        print(f"  {name:25s} | MAE={mae:.4f}  RMSE={rmse:.4f}  "
              f"R2={r2:.4f}  ({elapsed:.1f}s)")

    # Pick best by lowest RMSE
    best_name = min(results, key=lambda k: results[k]["rmse"])
    print(f"\n  >> Best regression model: {best_name} "
          f"(RMSE={results[best_name]['rmse']:.4f})")

    # Re-fit best on full training data
    best_model = models[best_name]
    best_model.fit(X, y)

    return results, best_name, best_model


# ---------------------------------------------------------------------------
# Cross-validation runner  (classification)
# ---------------------------------------------------------------------------

def train_classification(X: np.ndarray, y: np.ndarray):
    """
    Stratified 5-fold CV for each classification model.

    Returns
    -------
    results : dict  {model_name: {accuracy, f1, train_time_s}}
    best_name : str
    best_model : fitted estimator (re-fit on full data)
    """
    skf = StratifiedKFold(n_splits=K_FOLDS, shuffle=True, random_state=SEED)
    scoring = {
        "accuracy": "accuracy",
        "f1": make_scorer(f1_score, average="binary"),
    }

    results = {}
    models = _classification_models()
    print(f"\n{'='*60}")
    print(f"  CLASSIFICATION -- Peak-Hour Detection  ({K_FOLDS}-fold CV)")
    print(f"{'='*60}")

    for name, est in models.items():
        t0 = time.time()
        cv = cross_validate(est, X, y, cv=skf, scoring=scoring,
                            return_train_score=False, n_jobs=-1)
        elapsed = time.time() - t0

        acc = cv["test_accuracy"].mean()
        f1  = cv["test_f1"].mean()

        results[name] = {
            "accuracy": round(acc, 4),
            "accuracy_std": round(cv["test_accuracy"].std(), 4),
            "f1": round(f1, 4),
            "f1_std": round(cv["test_f1"].std(), 4),
            "train_time_s": round(elapsed, 2),
        }

        print(f"  {name:25s} | Acc={acc:.4f}  F1={f1:.4f}  ({elapsed:.1f}s)")

    # Pick best by F1
    best_name = max(results, key=lambda k: results[k]["f1"])
    print(f"\n  >> Best classification model: {best_name} "
          f"(F1={results[best_name]['f1']:.4f})")

    # Re-fit best on full training data
    best_model = models[best_name]
    best_model.fit(X, y)

    return results, best_name, best_model


# ---------------------------------------------------------------------------
# Feature importance extraction
# ---------------------------------------------------------------------------

def extract_feature_importance(model, feature_names: list) -> dict:
    """
    Extract feature importances from the best model (if tree-based).

    Business value: lets the pricing team explain *why* surge rose --
    e.g., "72 % driven by demand/supply ratio, 11 % by bad weather".
    """
    if hasattr(model, "feature_importances_"):
        imp = model.feature_importances_
    elif hasattr(model, "coef_"):
        imp = np.abs(model.coef_).flatten()
    else:
        return {}

    # Normalise to sum=1
    imp = imp / (imp.sum() + 1e-9)
    importance = {name: round(float(v), 5) for name, v in
                  sorted(zip(feature_names, imp), key=lambda x: -x[1])}
    return importance


# ---------------------------------------------------------------------------
# Save artefacts
# ---------------------------------------------------------------------------

def save_results(reg_results, clf_results,
                 best_reg_name, best_clf_name,
                 reg_model, clf_model,
                 feature_importance_reg, feature_importance_clf,
                 feature_names):
    """Persist models, results JSON, and feature-name lists."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Models
    joblib.dump(reg_model, os.path.join(OUTPUT_DIR, "best_regression_model.joblib"))
    joblib.dump(clf_model, os.path.join(OUTPUT_DIR, "best_classification_model.joblib"))
    print(f"[train_models] Saved best regression model    -> outputs/best_regression_model.joblib")
    print(f"[train_models] Saved best classification model -> outputs/best_classification_model.joblib")

    # Results JSON
    results = {
        "regression": {
            "best_model": best_reg_name,
            "models": reg_results,
            "feature_importance": feature_importance_reg,
        },
        "classification": {
            "best_model": best_clf_name,
            "models": clf_results,
            "feature_importance": feature_importance_clf,
        },
        "feature_names": feature_names,
    }
    results_path = os.path.join(OUTPUT_DIR, "results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[train_models] Results JSON -> {results_path}")

    # Feature names
    fn_path = os.path.join(OUTPUT_DIR, "feature_names.json")
    with open(fn_path, "w") as f:
        json.dump(feature_names, f)

    return results
