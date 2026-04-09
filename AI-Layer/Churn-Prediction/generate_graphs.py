"""
generate_graphs.py  --  Churn Prediction Visualisations
========================================================
Creates publication-quality charts from the training results.

Charts
------
1. **ROC Curve** -- shows the trade-off between True-Positive Rate and
   False-Positive Rate across every possible probability threshold.
   The further the curve bows towards the top-left corner, the better
   the model separates churners from actives.

2. **Feature Importance** -- horizontal bar chart of the top-15 most
   influential features.  Helps the business understand *why* a user is
   predicted to churn (e.g., recency is the strongest driver).

3. **Confusion Matrix** -- heatmap of TP / FP / FN / TN counts at the
   default 0.5 threshold.  Gives a concrete production-level view:
   "How many churners do we catch, and how many false alarms do we raise?"
"""

import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend (server-friendly)
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

OUTPUT_DIR = "outputs"
GRAPH_DIR = os.path.join(OUTPUT_DIR, "graphs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_results() -> dict:
    """Load the results JSON produced by train_models.py."""
    path = os.path.join(OUTPUT_DIR, "results.json")
    with open(path, "r") as f:
        return json.load(f)


def _ensure_dir():
    os.makedirs(GRAPH_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# 1) ROC Curve
# ---------------------------------------------------------------------------

def plot_roc_curve(results: dict):
    """
    Plot Receiver Operating Characteristic curve.

    ML concept:
    * X-axis = FPR (false-alarm rate).
    * Y-axis = TPR (detection rate).
    * A random classifier lies on the diagonal.
    * AUC > 0.9 is considered excellent for churn prediction.
    """
    _ensure_dir()
    fig, ax = plt.subplots(figsize=(8, 6))

    plot_data = results["plot_data"]
    fpr = np.array(plot_data["fpr"])
    tpr = np.array(plot_data["tpr"])
    auc = plot_data["roc_auc"]
    best_name = results["best_model"]

    # Model curve
    ax.plot(fpr, tpr, linewidth=2.2, color="#2563eb",
            label=f"{best_name}  (AUC = {auc:.4f})")

    # Random baseline
    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1.2,
            color="#94a3b8", label="Random (AUC = 0.5)")

    ax.set_xlabel("False Positive Rate", fontsize=12)
    ax.set_ylabel("True Positive Rate", fontsize=12)
    ax.set_title("ROC Curve  --  Churn Prediction", fontsize=14, fontweight="bold")
    ax.legend(loc="lower right", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.02])

    path = os.path.join(GRAPH_DIR, "roc_curve.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"[graphs] ROC curve -> {path}")


# ---------------------------------------------------------------------------
# 2) Feature Importance
# ---------------------------------------------------------------------------

def plot_feature_importance(results: dict, top_n: int = 15):
    """
    Horizontal bar chart of the most influential features.

    ML concept:
    * For tree models, importance = mean decrease in impurity (Gini).
    * For logistic regression, we use |coefficient| (normalised).
    * Top features tell the retention team *what signals to act on*.
    """
    _ensure_dir()
    importance = results.get("feature_importance", {})
    if not importance:
        print("[graphs] No feature importance found -- skipping.")
        return

    # Take top-N, sorted ascending (so highest bar is at the top)
    items = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:top_n]
    items.reverse()
    names = [x[0] for x in items]
    values = [x[1] for x in items]

    fig, ax = plt.subplots(figsize=(9, 6))
    colours = plt.cm.viridis(np.linspace(0.25, 0.85, len(names)))
    bars = ax.barh(names, values, color=colours, edgecolor="white", height=0.65)

    # Annotate bars with percentage values
    for bar, v in zip(bars, values):
        ax.text(bar.get_width() + 0.003, bar.get_y() + bar.get_height() / 2,
                f"{v*100:.1f}%", va="center", fontsize=9)

    ax.set_xlabel("Normalised Importance", fontsize=12)
    ax.set_title("Top Feature Importances  --  Churn Prediction",
                 fontsize=14, fontweight="bold")
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax.grid(axis="x", alpha=0.3)

    path = os.path.join(GRAPH_DIR, "feature_importance.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"[graphs] Feature importance -> {path}")


# ---------------------------------------------------------------------------
# 3) Confusion Matrix
# ---------------------------------------------------------------------------

def plot_confusion_matrix(results: dict):
    """
    Annotated heatmap of the confusion matrix.

    ML concept:
    * TN (top-left):  active users correctly identified -- no wasted effort.
    * FP (top-right): active users flagged as churning -- unnecessary offers.
    * FN (bottom-left): churning users we *missed* -- lost customers.
    * TP (bottom-right): churning users we caught -- retention opportunity.

    Business insight: FN is the most costly quadrant because we lose
    revenue without trying.  FP is cheaper (a discount to a loyal user).
    """
    _ensure_dir()
    cm = np.array(results["plot_data"]["confusion_matrix"])
    best_name = results["best_model"]

    fig, ax = plt.subplots(figsize=(6, 5))
    cax = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    fig.colorbar(cax, ax=ax, shrink=0.8)

    labels = ["Active (0)", "Churn (1)"]
    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_yticklabels(labels, fontsize=11)

    # Annotate each cell
    thresh = cm.max() / 2.0
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{cm[i, j]:,}",
                    ha="center", va="center", fontsize=16, fontweight="bold",
                    color="white" if cm[i, j] > thresh else "black")

    ax.set_xlabel("Predicted", fontsize=12)
    ax.set_ylabel("Actual", fontsize=12)
    ax.set_title(f"Confusion Matrix  --  {best_name}",
                 fontsize=13, fontweight="bold")

    path = os.path.join(GRAPH_DIR, "confusion_matrix.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"[graphs] Confusion matrix -> {path}")


# ---------------------------------------------------------------------------
# 4) Model Comparison Bar Chart (bonus)
# ---------------------------------------------------------------------------

def plot_model_comparison(results: dict):
    """
    Grouped bar chart comparing all models across the five metrics.

    Useful for stakeholder presentations to justify the model choice.
    """
    _ensure_dir()
    models_data = results.get("models", {})
    if not models_data:
        return

    model_names = list(models_data.keys())
    metrics = ["accuracy", "precision", "recall", "f1", "roc_auc"]
    metric_labels = ["Accuracy", "Precision", "Recall", "F1-Score", "ROC-AUC"]

    x = np.arange(len(metrics))
    width = 0.25
    colours = ["#3b82f6", "#10b981", "#f59e0b"]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, name in enumerate(model_names):
        vals = [models_data[name][m] for m in metrics]
        errs = [models_data[name].get(f"{m}_std", 0) for m in metrics]
        offset = (i - len(model_names) / 2 + 0.5) * width
        bars = ax.bar(x + offset, vals, width, yerr=errs,
                      label=name, color=colours[i % len(colours)],
                      capsize=3, edgecolor="white")
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{v:.3f}", ha="center", va="bottom", fontsize=7.5)

    ax.set_ylabel("Score", fontsize=12)
    ax.set_title("Model Comparison  --  Churn Prediction",
                 fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels, fontsize=11)
    ax.set_ylim([0, 1.12])
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3)

    path = os.path.join(GRAPH_DIR, "model_comparison.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"[graphs] Model comparison -> {path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_all_graphs():
    """Load results and produce every visualisation."""
    results = _load_results()
    plot_roc_curve(results)
    plot_feature_importance(results)
    plot_confusion_matrix(results)
    plot_model_comparison(results)
    print("[graphs] All graphs generated successfully.")


if __name__ == "__main__":
    generate_all_graphs()
