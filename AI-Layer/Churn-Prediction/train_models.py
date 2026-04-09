"""
train_models.py  --  Churn Classification Training & Evaluation
===============================================================
Trains three classification models and evaluates them with standard
metrics plus ROC-AUC.

Models
------
  * **Logistic Regression** -- interpretable linear baseline.
    (ML concept: models log-odds of churn as a linear combination of
     features.  Coefficients directly tell you "each extra day of
     recency increases churn odds by X %".)

  * **Random Forest** -- ensemble of decorrelated decision trees.
    (ML concept: bagging + feature sub-sampling reduces variance.
     Handles non-linear interactions out of the box.)

  * **XGBoost** -- sequential boosted trees.
    (ML concept: each tree corrects the errors of the previous one.
     Typically the best performer on tabular data.)

Evaluation metrics
------------------
  * **Accuracy** -- overall correct rate.  Misleading when classes are
    imbalanced, but useful as a sanity check.
  * **Precision** -- of all users we *flagged* as churning, how many
    actually churned?  High precision = fewer wasted retention offers.
  * **Recall** -- of all users who *will* churn, how many did we catch?
    High recall = fewer lost customers.
  * **F1-score** -- harmonic mean of precision & recall.  Best single
    metric when you care about both equally.
  * **ROC-AUC** -- area under the ROC curve.  Measures how well the model
    separates churners from actives across all probability thresholds.
    0.5 = random, 1.0 = perfect.

All results are persisted to JSON for downstream reporting & visualisation.
"""

import os
import json
import time
import warnings
import numpy as np
import joblib

from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score, make_scorer,
    confusion_matrix, roc_curve,
)

# XGBoost
try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("[train_models] WARNING: xgboost not installed -- skipping XGB.")

warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED = 42
K_FOLDS = 5
OUTPUT_DIR = "outputs"


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

def _build_models():
    """
    Return a dict of {name: estimator} for the churn task.

    Hyperparameters are tuned for a ~15 k row dataset.
    ML concept: we use class_weight="balanced" (or scale_pos_weight for
    XGBoost) because churn datasets are typically imbalanced (~25-35 %
    positives).  This upweights the minority class so the model does not
    simply predict "no churn" for everything.
    """
    models = {
        "Logistic Regression": LogisticRegression(
            max_iter=1000, C=1.0,
            class_weight="balanced",
            random_state=SEED,
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=400, max_depth=14, min_samples_leaf=5,
            class_weight="balanced",
            n_jobs=-1, random_state=SEED,
        ),
    }
    if HAS_XGB:
        models["XGBoost"] = XGBClassifier(
            n_estimators=500, max_depth=8, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0,
            scale_pos_weight=2.5,     # approximate positive class weight
            random_state=SEED, verbosity=0,
            eval_metric="logloss",
        )
    return models


# ---------------------------------------------------------------------------
# Cross-validated training
# ---------------------------------------------------------------------------

def train_and_evaluate(X: np.ndarray, y: np.ndarray):
    """
    Stratified 5-fold cross-validation for each model.

    ML concept: stratified splitting ensures each fold has the same
    churn ratio as the full dataset, which is critical when classes
    are imbalanced.

    Returns
    -------
    results    : dict  {name: {accuracy, precision, recall, f1, roc_auc, time_s}}
    best_name  : str
    best_model : fitted estimator (re-fit on full data)
    all_models : dict  {name: fitted_estimator}  for per-model plots
    """
    skf = StratifiedKFold(n_splits=K_FOLDS, shuffle=True, random_state=SEED)

    scoring = {
        "accuracy":  "accuracy",
        "precision": make_scorer(precision_score, zero_division=0),
        "recall":    make_scorer(recall_score, zero_division=0),
        "f1":        make_scorer(f1_score, zero_division=0),
        "roc_auc":   "roc_auc",
    }

    results = {}
    models = _build_models()

    print(f"\n{'='*65}")
    print(f"  CHURN CLASSIFICATION  ({K_FOLDS}-fold Stratified CV)")
    print(f"{'='*65}")

    for name, est in models.items():
        t0 = time.time()
        cv = cross_validate(est, X, y, cv=skf, scoring=scoring,
                            return_train_score=False, n_jobs=-1)
        elapsed = time.time() - t0

        results[name] = {
            "accuracy":      round(cv["test_accuracy"].mean(), 4),
            "accuracy_std":  round(cv["test_accuracy"].std(), 4),
            "precision":     round(cv["test_precision"].mean(), 4),
            "precision_std": round(cv["test_precision"].std(), 4),
            "recall":        round(cv["test_recall"].mean(), 4),
            "recall_std":    round(cv["test_recall"].std(), 4),
            "f1":            round(cv["test_f1"].mean(), 4),
            "f1_std":        round(cv["test_f1"].std(), 4),
            "roc_auc":       round(cv["test_roc_auc"].mean(), 4),
            "roc_auc_std":   round(cv["test_roc_auc"].std(), 4),
            "train_time_s":  round(elapsed, 2),
        }

        r = results[name]
        print(f"  {name:22s} | Acc={r['accuracy']:.4f}  Prec={r['precision']:.4f}  "
              f"Rec={r['recall']:.4f}  F1={r['f1']:.4f}  "
              f"AUC={r['roc_auc']:.4f}  ({elapsed:.1f}s)")

    # -----------------------------------------------------------------------
    # Select best model by ROC-AUC (most robust for imbalanced data)
    # ML concept: ROC-AUC is threshold-independent, so it's the fairest
    # way to compare models before we pick an operating threshold.
    # -----------------------------------------------------------------------
    best_name = max(results, key=lambda k: results[k]["roc_auc"])
    print(f"\n  >> Best model: {best_name} "
          f"(ROC-AUC = {results[best_name]['roc_auc']:.4f})")

    # Re-fit all models on full data (for plots & inference)
    all_fitted = {}
    for name, est in models.items():
        est.fit(X, y)
        all_fitted[name] = est

    best_model = all_fitted[best_name]

    return results, best_name, best_model, all_fitted


# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------

def extract_feature_importance(model, feature_names: list) -> dict:
    """
    Extract feature importances from the best model.

    ML concept: tree-based models expose feature_importances_ (mean
    decrease in impurity).  For Logistic Regression, we use absolute
    coefficient values -- larger |coef| = stronger predictor.

    Business value: lets the retention team explain *why* a user is at
    risk -- e.g., "83 % driven by recency + frequency drop".
    """
    if hasattr(model, "feature_importances_"):
        imp = model.feature_importances_
    elif hasattr(model, "coef_"):
        imp = np.abs(model.coef_).flatten()
    else:
        return {}

    imp = imp / (imp.sum() + 1e-9)
    importance = {
        name: round(float(v), 5)
        for name, v in sorted(zip(feature_names, imp), key=lambda x: -x[1])
    }
    return importance


# ---------------------------------------------------------------------------
# Compute ROC curve & confusion matrix for best model
# ---------------------------------------------------------------------------

def compute_plot_data(model, X, y):
    """
    Generate data needed for ROC curve and confusion matrix plots.

    ML concept:
      * ROC curve plots True Positive Rate vs False Positive Rate at
        every possible probability threshold.  A curve hugging the
        top-left corner is ideal.
      * Confusion matrix shows TP / FP / FN / TN counts at the default
        0.5 threshold, giving a concrete "what happens in production" view.
    """
    y_prob = model.predict_proba(X)[:, 1]
    y_pred = model.predict(X)

    fpr, tpr, thresholds = roc_curve(y, y_prob)
    cm = confusion_matrix(y, y_pred)

    return {
        "fpr": fpr.tolist(),
        "tpr": tpr.tolist(),
        "thresholds": thresholds.tolist(),
        "confusion_matrix": cm.tolist(),
        "roc_auc": round(float(roc_auc_score(y, y_prob)), 4),
    }


# ---------------------------------------------------------------------------
# Save artefacts
# ---------------------------------------------------------------------------

def save_results(results, best_name, best_model, feature_importance,
                 plot_data, feature_names):
    """Persist best model, results JSON, and feature names."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Best model
    model_path = os.path.join(OUTPUT_DIR, "best_model.joblib")
    joblib.dump(best_model, model_path)
    print(f"[train_models] Best model saved -> {model_path}")

    # Results JSON
    payload = {
        "best_model": best_name,
        "models": results,
        "feature_importance": feature_importance,
        "plot_data": plot_data,
        "feature_names": feature_names,
    }
    results_path = os.path.join(OUTPUT_DIR, "results.json")
    with open(results_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[train_models] Results JSON -> {results_path}")

    # Feature names
    fn_path = os.path.join(OUTPUT_DIR, "feature_names.json")
    with open(fn_path, "w") as f:
        json.dump(feature_names, f)

    return payload
