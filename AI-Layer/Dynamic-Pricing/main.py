"""
main.py  --  Dynamic Pricing Pipeline Orchestrator
===================================================
Runs the complete pipeline end-to-end:

  Step 1  --  Generate synthetic dataset  (25 000 rows)
  Step 2  --  Feature engineering & preprocessing
  Step 3  --  Train regression + classification models  (5-fold CV)
  Step 4  --  Apply safety layer to predictions
  Step 5  --  Generate 10 research-ready visualizations
  Step 6  --  Print final summary

All artefacts are saved under  outputs/  :
  * best_regression_model.joblib
  * best_classification_model.joblib
  * transformer.joblib
  * results.json
  * feature_names.json
  * figures/*.png

Usage
-----
    python main.py

The pipeline has a lightweight checkpoint so that on re-run it skips
already-completed steps.  Delete  outputs/.checkpoint.json  to force
a full re-run.
"""

import os
import sys
import json
import time
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
OUTPUT_DIR = "outputs"
CHECKPOINT = os.path.join(OUTPUT_DIR, ".checkpoint.json")

# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            return json.load(f)
    return {"completed": []}

def _save_checkpoint(ckpt):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(CHECKPOINT, "w") as f:
        json.dump(ckpt, f)

def _done(ckpt, step):
    return step in ckpt["completed"]

def _mark(ckpt, step):
    ckpt["completed"].append(step)
    _save_checkpoint(ckpt)


# ===================================================================
# STEP 1 -- Dataset Generation
# ===================================================================

def step_generate(ckpt):
    """
    Generate 25 000 synthetic delivery records.
    Business reasoning: a realistic dataset must cover all 15 zones,
    24 hours, 7 days, 5 weather types, and the full surge range.
    """
    if _done(ckpt, "generate"):
        print("[STEP 1] Dataset -- already generated, skipping.")
        return
    print("\n" + "=" * 65)
    print("  STEP 1 -- Generate Synthetic Dataset")
    print("=" * 65)

    from dataset_generator import generate_dataset
    df = generate_dataset()

    print(f"  Rows:    {len(df)}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Surge range: [{df['surge_multiplier'].min():.3f}, "
          f"{df['surge_multiplier'].max():.3f}]")
    print(f"  Peak-hour ratio: "
          f"{df['is_peak_hour'].mean()*100:.1f}% of rows")
    _mark(ckpt, "generate")


# ===================================================================
# STEP 2 -- Feature Engineering
# ===================================================================

def step_engineer(ckpt):
    """
    Transform raw data into ML-ready features:
      * Cyclical encoding (hour, day)
      * Demand/supply ratio
      * Moving-average demand
      * Interaction terms
      * Weather one-hot encoding
    """
    if _done(ckpt, "engineer"):
        print("[STEP 2] Feature Engineering -- already done, skipping.")
        return
    print("\n" + "=" * 65)
    print("  STEP 2 -- Feature Engineering & Preprocessing")
    print("=" * 65)

    import pandas as pd
    from feature_engineering import prepare_data, save_transformer

    df = pd.read_csv("data/surge_pricing_dataset.csv")
    X, y_reg, y_clf, transformer, feature_names, df_eng = prepare_data(df)

    save_transformer(transformer)

    # Save feature names (needed by training step)
    with open(os.path.join(OUTPUT_DIR, "feature_names.json"), "w") as f:
        json.dump(feature_names, f)

    # Persist engineered data for later steps
    df_eng.to_csv(os.path.join(OUTPUT_DIR, "engineered_data.csv"), index=False)
    np.save(os.path.join(OUTPUT_DIR, "X.npy"), X)
    np.save(os.path.join(OUTPUT_DIR, "y_reg.npy"), y_reg)
    np.save(os.path.join(OUTPUT_DIR, "y_clf.npy"), y_clf)

    print(f"  Feature matrix shape: {X.shape}")
    print(f"  Feature names ({len(feature_names)}): {feature_names[:8]} ...")
    print(f"  Regression target  (surge_multiplier): "
          f"mean={y_reg.mean():.3f}, std={y_reg.std():.3f}")
    print(f"  Classification target (is_peak_hour) : "
          f"{y_clf.sum():.0f} positives / {len(y_clf)} total")
    _mark(ckpt, "engineer")


# ===================================================================
# STEP 3 -- Model Training
# ===================================================================

def step_train(ckpt):
    """
    Train 4 regression models and 4 classification models with 5-fold CV.
    Compare: Linear/Logistic, Random Forest, XGBoost, Gradient Boosting.
    Save the best of each task.
    """
    if _done(ckpt, "train"):
        print("[STEP 3] Training -- already done, skipping.")
        return
    print("\n" + "=" * 65)
    print("  STEP 3 -- Model Training & Comparison")
    print("=" * 65)

    from train_models import (
        train_regression, train_classification,
        extract_feature_importance, save_results,
    )

    X = np.load(os.path.join(OUTPUT_DIR, "X.npy"))
    y_reg = np.load(os.path.join(OUTPUT_DIR, "y_reg.npy"))
    y_clf = np.load(os.path.join(OUTPUT_DIR, "y_clf.npy"))

    with open(os.path.join(OUTPUT_DIR, "feature_names.json")) as f:
        feature_names = json.load(f)

    # --- Regression --------------------------------------------------------
    reg_results, best_reg_name, reg_model = train_regression(X, y_reg)

    # --- Classification ----------------------------------------------------
    clf_results, best_clf_name, clf_model = train_classification(X, y_clf)

    # --- Feature importances -----------------------------------------------
    fi_reg = extract_feature_importance(reg_model, feature_names)
    fi_clf = extract_feature_importance(clf_model, feature_names)

    # --- Persist -----------------------------------------------------------
    save_results(
        reg_results, clf_results,
        best_reg_name, best_clf_name,
        reg_model, clf_model,
        fi_reg, fi_clf,
        feature_names,
    )
    _mark(ckpt, "train")


# ===================================================================
# STEP 4 -- Safety Layer Demonstration
# ===================================================================

def step_safety(ckpt):
    """
    Run the best regression model on all data, then apply the
    rule-based safety layer to demonstrate clamping & discounts.
    Saves raw vs safe surge arrays for the visualization step.
    """
    if _done(ckpt, "safety"):
        print("[STEP 4] Safety layer -- already done, skipping.")
        return
    print("\n" + "=" * 65)
    print("  STEP 4 -- Rule-Based Safety Layer")
    print("=" * 65)

    import joblib
    from safety_layer import apply_safety_rules

    X = np.load(os.path.join(OUTPUT_DIR, "X.npy"))
    reg_model = joblib.load(os.path.join(OUTPUT_DIR, "best_regression_model.joblib"))
    clf_model = joblib.load(os.path.join(OUTPUT_DIR, "best_classification_model.joblib"))

    raw_surge = reg_model.predict(X)
    peak_pred = clf_model.predict(X)

    # Apply safety to each prediction
    safe_surge = np.array([
        apply_safety_rules(rs, int(pp)).surge_multiplier
        for rs, pp in zip(raw_surge, peak_pred)
    ])

    # Stats
    clamped_up = (raw_surge < 1.0).sum()
    clamped_down = (raw_surge > 2.5).sum()
    unchanged = len(raw_surge) - clamped_up - clamped_down
    print(f"  Total predictions:  {len(raw_surge)}")
    print(f"  Clamped up (< 1.0): {clamped_up}")
    print(f"  Clamped down (>2.5): {clamped_down}")
    print(f"  Unchanged:          {unchanged}")
    print(f"  Safe surge range:   [{safe_surge.min():.3f}, {safe_surge.max():.3f}]")

    np.save(os.path.join(OUTPUT_DIR, "raw_surge.npy"), raw_surge)
    np.save(os.path.join(OUTPUT_DIR, "safe_surge.npy"), safe_surge)
    _mark(ckpt, "safety")


# ===================================================================
# STEP 5 -- Visualization
# ===================================================================

def step_graphs(ckpt):
    """Generate 10 publication-ready charts."""
    if _done(ckpt, "graphs"):
        print("[STEP 5] Graphs -- already generated, skipping.")
        return
    print("\n" + "=" * 65)
    print("  STEP 5 -- Generate Research Visualizations")
    print("=" * 65)

    import pandas as pd
    from generate_graphs import generate_all_graphs

    df_eng = pd.read_csv(os.path.join(OUTPUT_DIR, "engineered_data.csv"))
    with open(os.path.join(OUTPUT_DIR, "results.json")) as f:
        results = json.load(f)

    raw_surges = np.load(os.path.join(OUTPUT_DIR, "raw_surge.npy"))
    safe_surges = np.load(os.path.join(OUTPUT_DIR, "safe_surge.npy"))

    generate_all_graphs(df_eng, results, raw_surges, safe_surges)
    _mark(ckpt, "graphs")


# ===================================================================
# STEP 6 -- Summary
# ===================================================================

def print_summary():
    """Print a final summary of everything produced."""
    print("\n" + "=" * 65)
    print("  PIPELINE COMPLETE -- Summary")
    print("=" * 65)

    with open(os.path.join(OUTPUT_DIR, "results.json")) as f:
        results = json.load(f)

    reg = results["regression"]
    clf = results["classification"]

    print(f"\n  REGRESSION (Surge Multiplier Prediction)")
    print(f"  {'Model':<25s} {'MAE':>8s} {'RMSE':>8s} {'R2':>8s}")
    print(f"  {'-'*49}")
    for name, m in reg["models"].items():
        print(f"  {name:<25s} {m['mae']:>8.4f} {m['rmse']:>8.4f} {m['r2']:>8.4f}")
    print(f"  >> Best: {reg['best_model']}")

    print(f"\n  CLASSIFICATION (Peak-Hour Detection)")
    print(f"  {'Model':<25s} {'Accuracy':>10s} {'F1':>8s}")
    print(f"  {'-'*43}")
    for name, m in clf["models"].items():
        print(f"  {name:<25s} {m['accuracy']:>10.4f} {m['f1']:>8.4f}")
    print(f"  >> Best: {clf['best_model']}")

    print(f"\n  Artefacts saved to: {os.path.abspath(OUTPUT_DIR)}")
    print(f"  Figures:  outputs/figures/ (10 PNGs)")
    print(f"  Models:   best_regression_model.joblib, best_classification_model.joblib")
    print(f"  API:      python app.py  ->  POST /calculate-price")
    print("=" * 65)


# ===================================================================
# Main
# ===================================================================

def main():
    t0 = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ckpt = _load_checkpoint()

    steps = [
        ("generate", step_generate),
        ("engineer", step_engineer),
        ("train",    step_train),
        ("safety",   step_safety),
        ("graphs",   step_graphs),
    ]

    for name, fn in steps:
        fn(ckpt)

    # Clean up checkpoint on full success
    if os.path.exists(CHECKPOINT):
        os.remove(CHECKPOINT)

    print_summary()
    elapsed = time.time() - t0
    print(f"\n  Total pipeline time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
