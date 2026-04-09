"""
main.py  --  Churn Prediction Pipeline Orchestrator
=====================================================
Runs the full ML pipeline end-to-end with checkpointing:

  Step 1 : Generate synthetic dataset      (dataset_generator.py)
  Step 2 : Feature engineering & transform  (feature_engineering.py)
  Step 3 : Train & evaluate models          (train_models.py)
  Step 4 : Generate visualisations          (generate_graphs.py)
  Step 5 : Print summary

Checkpointing
--------------
Each step writes a checkpoint so that a failed run can be resumed from
the last successful step.  Delete `outputs/.checkpoints` to force a
full re-run.

ML concept: reproducible pipelines are essential in production ML.
Checkpointing avoids re-computing expensive steps (data gen, model
training) when only downstream code changes.
"""

import os
import json
import time
import traceback

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OUTPUT_DIR = "outputs"
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, ".checkpoints")
DATA_DIR = "data"


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _load_checkpoints() -> set:
    """Return set of completed step names."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            return set(json.load(f))
    return set()


def _save_checkpoint(step: str, completed: set):
    """Persist completed step."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    completed.add(step)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(sorted(completed), f)


def _clear_checkpoints():
    """Delete all checkpoints (force full re-run)."""
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def step_generate_dataset(done: set):
    """Step 1: Generate the synthetic churn dataset."""
    tag = "generate_dataset"
    if tag in done:
        print("[main] Step 1 -- dataset already generated (cached).")
        return
    print("\n" + "=" * 65)
    print("  STEP 1 / 4 :  Generate Synthetic Dataset")
    print("=" * 65)

    from dataset_generator import generate_dataset
    df = generate_dataset()
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, "churn_dataset.csv")
    df.to_csv(path, index=False)
    print(f"[main] Dataset saved -> {path}  ({len(df)} rows, {df.shape[1]} cols)")
    print(f"[main] Churn rate: {df['churn'].mean():.2%}")
    _save_checkpoint(tag, done)


def step_feature_engineering(done: set):
    """Step 2: Engineer features and fit the preprocessor."""
    tag = "feature_engineering"
    if tag in done:
        print("[main] Step 2 -- features already engineered (cached).")
        return
    print("\n" + "=" * 65)
    print("  STEP 2 / 4 :  Feature Engineering & Preprocessing")
    print("=" * 65)

    import pandas as pd
    from feature_engineering import prepare_data, save_transformer

    df = pd.read_csv(os.path.join(DATA_DIR, "churn_dataset.csv"))
    X, y, transformer, feature_names, df_eng = prepare_data(df)

    # Persist transformer for the Flask API
    save_transformer(transformer, os.path.join(OUTPUT_DIR, "transformer.joblib"))

    # Store processed arrays for step 3
    import numpy as np
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    np.save(os.path.join(OUTPUT_DIR, "X.npy"), X)
    np.save(os.path.join(OUTPUT_DIR, "y.npy"), y)
    with open(os.path.join(OUTPUT_DIR, "feature_names.json"), "w") as f:
        json.dump(feature_names, f)

    print(f"[main] X shape: {X.shape}   y shape: {y.shape}")
    print(f"[main] Features ({len(feature_names)}): {feature_names[:5]} ... ")
    _save_checkpoint(tag, done)


def step_train_models(done: set):
    """Step 3: Train and evaluate all models."""
    tag = "train_models"
    if tag in done:
        print("[main] Step 3 -- models already trained (cached).")
        return
    print("\n" + "=" * 65)
    print("  STEP 3 / 4 :  Model Training & Evaluation")
    print("=" * 65)

    import numpy as np
    from train_models import (
        train_and_evaluate, extract_feature_importance,
        compute_plot_data, save_results,
    )

    X = np.load(os.path.join(OUTPUT_DIR, "X.npy"))
    y = np.load(os.path.join(OUTPUT_DIR, "y.npy"))
    with open(os.path.join(OUTPUT_DIR, "feature_names.json"), "r") as f:
        feature_names = json.load(f)

    results, best_name, best_model, all_fitted = train_and_evaluate(X, y)
    importance = extract_feature_importance(best_model, feature_names)
    plot_data = compute_plot_data(best_model, X, y)

    save_results(results, best_name, best_model, importance,
                 plot_data, feature_names)

    _save_checkpoint(tag, done)


def step_generate_graphs(done: set):
    """Step 4: Generate all visualisation charts."""
    tag = "generate_graphs"
    if tag in done:
        print("[main] Step 4 -- graphs already generated (cached).")
        return
    print("\n" + "=" * 65)
    print("  STEP 4 / 4 :  Generate Visualisations")
    print("=" * 65)

    from generate_graphs import generate_all_graphs
    generate_all_graphs()
    _save_checkpoint(tag, done)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary():
    """Print a final summary of the pipeline results."""
    results_path = os.path.join(OUTPUT_DIR, "results.json")
    if not os.path.exists(results_path):
        print("[main] No results found -- pipeline may have failed.")
        return

    with open(results_path, "r") as f:
        results = json.load(f)

    best = results["best_model"]
    metrics = results["models"][best]

    print("\n" + "=" * 65)
    print("  PIPELINE COMPLETE -- SUMMARY")
    print("=" * 65)
    print(f"  Best model      : {best}")
    print(f"  Accuracy         : {metrics['accuracy']:.4f} (+/- {metrics['accuracy_std']:.4f})")
    print(f"  Precision        : {metrics['precision']:.4f} (+/- {metrics['precision_std']:.4f})")
    print(f"  Recall           : {metrics['recall']:.4f} (+/- {metrics['recall_std']:.4f})")
    print(f"  F1-Score         : {metrics['f1']:.4f} (+/- {metrics['f1_std']:.4f})")
    print(f"  ROC-AUC          : {metrics['roc_auc']:.4f} (+/- {metrics['roc_auc_std']:.4f})")
    print(f"  Training time    : {metrics['train_time_s']:.1f}s")

    # Top-5 features
    importance = results.get("feature_importance", {})
    if importance:
        top5 = list(importance.items())[:5]
        print(f"\n  Top-5 features:")
        for i, (name, val) in enumerate(top5, 1):
            print(f"    {i}. {name:30s} {val*100:.1f}%")

    # Artefacts
    print(f"\n  Artefacts:")
    for fpath in [
        "outputs/best_model.joblib",
        "outputs/transformer.joblib",
        "outputs/results.json",
        "outputs/graphs/roc_curve.png",
        "outputs/graphs/feature_importance.png",
        "outputs/graphs/confusion_matrix.png",
        "outputs/graphs/model_comparison.png",
    ]:
        exists = "OK" if os.path.exists(fpath) else "MISSING"
        print(f"    [{exists:7s}] {fpath}")
    print("=" * 65)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()

    # Clear checkpoints for clean run (comment out to enable resume)
    _clear_checkpoints()

    done = _load_checkpoints()

    steps = [
        step_generate_dataset,
        step_feature_engineering,
        step_train_models,
        step_generate_graphs,
    ]

    for step_fn in steps:
        try:
            step_fn(done)
        except Exception as exc:
            print(f"\n[main] FAILED at {step_fn.__name__}: {exc}")
            traceback.print_exc()
            return

    print_summary()
    elapsed = time.time() - t0
    print(f"\n  Total pipeline time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
