"""
=============================================================================
Research-Ready Graphs & Visualisations
=============================================================================

Figures produced:
    1.  Feature importance (horizontal bar)
    2.  Error distribution (overlaid histograms)
    3.  Model comparison bar chart (MAE / RMSE / R2 with +/- std)
    4.  Actual vs Predicted scatter (best model)
    5.  Training-time comparison
    6.  Learning curves (train size vs RMSE)
    7.  Ablation study bar chart
    8.  Residual Q-Q plot (normality check)
    9.  Residual vs Predicted (heteroscedasticity check)
   10.  Inference latency bar chart
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from scipy import stats as sp_stats

BASE    = Path(__file__).parent
OUT     = BASE / "outputs"
FIG_DIR = OUT / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

COLOURS = ["#4C72B0", "#55A868", "#C44E52", "#8172B2", "#CCB974"]


def load_artefacts():
    with open(OUT / "results.json") as f:
        res = json.load(f)
    preds = pd.read_csv(OUT / "test_predictions.csv")
    imps = {}
    p = OUT / "feature_importances.json"
    if p.exists():
        with open(p) as f:
            imps = json.load(f)
    return res, preds, imps


# ─── 1. Feature Importance ───────────────────────────────────────────────────
def plot_feature_importance(imps, res):
    best = res["best_model"]
    if best in imps:
        imp, title = imps[best], best
    elif imps:
        title = list(imps.keys())[0]
        imp = imps[title]
    else:
        print("[graphs] No feature importances – skipping.")
        return
    features = list(imp.keys())
    values   = list(imp.values())
    order    = np.argsort(values)
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh([features[i] for i in order], [values[i] for i in order],
            color=COLOURS[0], edgecolor="white")
    ax.set_xlabel("Importance", fontsize=12)
    ax.set_title(f"Feature Importance – {title}", fontsize=14, weight="bold")
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(xmax=1.0))
    plt.tight_layout()
    fig.savefig(FIG_DIR / "feature_importance.png", dpi=300)
    plt.close(fig)
    print("[graphs] feature_importance.png")


# ─── 2. Error Distribution ───────────────────────────────────────────────────
def plot_error_distribution(preds):
    model_cols = [c for c in preds.columns if c != "actual"]
    actual = preds["actual"].values
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, col in enumerate(model_cols):
        residuals = preds[col].values - actual
        ax.hist(residuals, bins=60, alpha=0.4, label=col,
                color=COLOURS[i % len(COLOURS)], edgecolor="white")
    ax.axvline(0, color="black", ls="--", lw=1)
    ax.set_xlabel("Residual (predicted − actual) [min]", fontsize=12)
    ax.set_ylabel("Count", fontsize=12)
    ax.set_title("Prediction Error Distribution", fontsize=14, weight="bold")
    ax.legend(fontsize=9)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "error_distribution.png", dpi=300)
    plt.close(fig)
    print("[graphs] error_distribution.png")


# ─── 3. Model Comparison (CV scores with error bars) ─────────────────────────
def plot_model_comparison(res):
    cv = res["cv_results"]
    models = [k for k in cv if k != "Mean Baseline"]
    metrics = ["MAE", "RMSE", "R2"]
    x = np.arange(len(models))
    width = 0.25
    fig, ax = plt.subplots(figsize=(11, 5))
    for j, metric in enumerate(metrics):
        means = [cv[m][f"{metric}_mean"] for m in models]
        stds  = [cv[m][f"{metric}_std"]  for m in models]
        bars = ax.bar(x + j * width, means, width, yerr=stds,
                      label=metric, color=COLOURS[j], edgecolor="white",
                      capsize=3)
        for bar, v in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.02,
                    f"{v:.3f}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x + width)
    ax.set_xticklabels(models, fontsize=10)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title(f"Model Comparison ({len(cv.get(models[0],{}).get('fold_rmses',[]))}–Fold CV, mean ± std)",
                 fontsize=14, weight="bold")
    ax.legend(fontsize=10)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "model_comparison.png", dpi=300)
    plt.close(fig)
    print("[graphs] model_comparison.png")


# ─── 4. Actual vs Predicted ──────────────────────────────────────────────────
def plot_actual_vs_predicted(preds, res):
    best = res["best_model"]
    if best not in preds.columns:
        return
    actual = preds["actual"].values
    pred   = preds[best].values
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(actual, pred, alpha=0.25, s=8, color=COLOURS[0])
    lims = [min(actual.min(), pred.min()) - 2,
            max(actual.max(), pred.max()) + 2]
    ax.plot(lims, lims, "k--", lw=1, label="y = x (perfect)")
    ax.set_xlim(lims); ax.set_ylim(lims)
    ax.set_xlabel("Actual (min)", fontsize=12)
    ax.set_ylabel("Predicted (min)", fontsize=12)
    ax.set_title(f"Actual vs Predicted – {best}", fontsize=14, weight="bold")
    ax.legend(fontsize=10)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "actual_vs_predicted.png", dpi=300)
    plt.close(fig)
    print("[graphs] actual_vs_predicted.png")


# ─── 5. Training Time ────────────────────────────────────────────────────────
def plot_training_time(res):
    ho = res["holdout_results"]
    models = [k for k in ho if k != "Mean Baseline"]
    times  = [ho[m]["train_time_s"] for m in models]
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.barh(models, times, color=COLOURS[:len(models)], edgecolor="white")
    for bar, t in zip(bars, times):
        ax.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height() / 2,
                f"{t:.2f}s", va="center", fontsize=10)
    ax.set_xlabel("Training Time (s)", fontsize=12)
    ax.set_title("Model Training Time", fontsize=14, weight="bold")
    plt.tight_layout()
    fig.savefig(FIG_DIR / "training_time.png", dpi=300)
    plt.close(fig)
    print("[graphs] training_time.png")


# ─── 6. Learning Curves ──────────────────────────────────────────────────────
def plot_learning_curves(res):
    lc = res.get("learning_curves")
    if not lc:
        return
    sizes = np.array(lc["train_sizes"])
    tr_m  = np.array(lc["train_rmse_mean"])
    tr_s  = np.array(lc["train_rmse_std"])
    te_m  = np.array(lc["test_rmse_mean"])
    te_s  = np.array(lc["test_rmse_std"])

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.fill_between(sizes, tr_m - tr_s, tr_m + tr_s, alpha=0.15, color=COLOURS[0])
    ax.fill_between(sizes, te_m - te_s, te_m + te_s, alpha=0.15, color=COLOURS[2])
    ax.plot(sizes, tr_m, "o-", color=COLOURS[0], label="Train RMSE")
    ax.plot(sizes, te_m, "s-", color=COLOURS[2], label="Validation RMSE")
    ax.set_xlabel("Training Set Size", fontsize=12)
    ax.set_ylabel("RMSE (min)", fontsize=12)
    ax.set_title(f"Learning Curve – {res['best_model']}", fontsize=14, weight="bold")
    ax.legend(fontsize=10)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "learning_curve.png", dpi=300)
    plt.close(fig)
    print("[graphs] learning_curve.png")


# ─── 7. Ablation Study Bar Chart ─────────────────────────────────────────────
def plot_ablation(res):
    abl = res.get("ablation")
    if not abl:
        return
    labels = list(abl.keys())
    rmses  = [abl[l]["RMSE"] for l in labels]
    r2s    = [abl[l]["R2"]   for l in labels]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    bars1 = ax1.barh(labels, rmses, color=COLOURS[2], edgecolor="white")
    ax1.set_xlabel("RMSE (min)", fontsize=12)
    ax1.set_title("Ablation – RMSE Impact", fontsize=13, weight="bold")
    for bar, v in zip(bars1, rmses):
        ax1.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                 f"{v:.3f}", va="center", fontsize=9)

    bars2 = ax2.barh(labels, r2s, color=COLOURS[0], edgecolor="white")
    ax2.set_xlabel("R²", fontsize=12)
    ax2.set_title("Ablation – R² Impact", fontsize=13, weight="bold")
    for bar, v in zip(bars2, r2s):
        ax2.text(bar.get_width() + 0.002, bar.get_y() + bar.get_height() / 2,
                 f"{v:.4f}", va="center", fontsize=9)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "ablation_study.png", dpi=300)
    plt.close(fig)
    print("[graphs] ablation_study.png")


# ─── 8. Q-Q Plot (residual normality) ────────────────────────────────────────
def plot_qq(preds, res):
    best = res["best_model"]
    if best not in preds.columns:
        return
    residuals = preds[best].values - preds["actual"].values
    fig, ax = plt.subplots(figsize=(6, 6))
    sp_stats.probplot(residuals, dist="norm", plot=ax)
    ax.set_title(f"Q-Q Plot of Residuals – {best}", fontsize=14, weight="bold")
    ax.get_lines()[0].set(marker="o", markersize=3, alpha=0.4, color=COLOURS[0])
    ax.get_lines()[1].set(color="red", linewidth=1.5)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "qq_plot.png", dpi=300)
    plt.close(fig)
    print("[graphs] qq_plot.png")


# ─── 9. Residuals vs Predicted (heteroscedasticity) ──────────────────────────
def plot_residuals_vs_predicted(preds, res):
    best = res["best_model"]
    if best not in preds.columns:
        return
    pred = preds[best].values
    residuals = pred - preds["actual"].values
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(pred, residuals, alpha=0.2, s=8, color=COLOURS[0])
    ax.axhline(0, color="black", ls="--", lw=1)
    ax.set_xlabel("Predicted (min)", fontsize=12)
    ax.set_ylabel("Residual (min)", fontsize=12)
    ax.set_title(f"Residuals vs Predicted – {best}", fontsize=14, weight="bold")
    plt.tight_layout()
    fig.savefig(FIG_DIR / "residuals_vs_predicted.png", dpi=300)
    plt.close(fig)
    print("[graphs] residuals_vs_predicted.png")


# ─── 10. Inference Latency ───────────────────────────────────────────────────
def plot_latency(res):
    lat = res.get("latency")
    if not lat:
        return
    models = [k for k in lat if k != "Mean Baseline"]
    means  = [lat[m]["mean_ms"] for m in models]
    p99s   = [lat[m]["p99_ms"]  for m in models]
    x = np.arange(len(models))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(x - width/2, means, width, label="Mean", color=COLOURS[0], edgecolor="white")
    ax.bar(x + width/2, p99s,  width, label="P99",  color=COLOURS[2], edgecolor="white")
    ax.set_xticks(x)
    ax.set_xticklabels(models, fontsize=9)
    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_title("Single-Sample Inference Latency", fontsize=14, weight="bold")
    ax.legend(fontsize=10)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "inference_latency.png", dpi=300)
    plt.close(fig)
    print("[graphs] inference_latency.png")


# -- Orchestrator --------------------------------------------------------------
def generate_all_graphs():
    res, preds, imps = load_artefacts()
    plot_feature_importance(imps, res)
    plot_error_distribution(preds)
    plot_model_comparison(res)
    plot_actual_vs_predicted(preds, res)
    plot_training_time(res)
    plot_learning_curves(res)
    plot_ablation(res)
    plot_qq(preds, res)
    plot_residuals_vs_predicted(preds, res)
    plot_latency(res)

    print(f"\n[graphs] All figures -> {FIG_DIR.resolve()}")


if __name__ == "__main__":
    generate_all_graphs()
