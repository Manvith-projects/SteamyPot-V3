"""
generate_graphs.py
==================
Produces publication-quality visualizations for the Dynamic Pricing
research project.

Graphs generated
----------------
1. surge_vs_demand.png        -- Scatter: active_orders vs surge_multiplier
2. demand_supply_heatmap.png  -- 2-D heatmap of demand/supply across hours & zones
3. feature_importance_reg.png -- Bar chart: regression model feature importances
4. feature_importance_clf.png -- Bar chart: classification model feature importances
5. model_comparison_reg.png   -- Grouped bar: MAE / RMSE / R2 across regression models
6. model_comparison_clf.png   -- Grouped bar: Accuracy / F1 across classification models
7. surge_distribution.png     -- Histogram of surge_multiplier values
8. hourly_surge_profile.png   -- Line chart: mean surge by hour of day
9. weather_impact.png         -- Box plot: surge by weather condition
10. safety_layer_demo.png     -- Before/after scatter showing safety-layer clamping

Each plot includes:
  * Descriptive title & axis labels
  * Business-oriented annotations where appropriate
  * Tight layout for direct inclusion in a research paper or slide deck
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUTPUT_DIR = os.path.join("outputs", "figures")
DPI = 180
STYLE = "seaborn-v0_8-whitegrid"

def _setup():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    try:
        plt.style.use(STYLE)
    except OSError:
        plt.style.use("ggplot")


def _save(fig, name):
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [graph] {name}")


# ===================================================================
# 1. Surge vs Demand scatter
# ===================================================================

def plot_surge_vs_demand(df):
    """
    Business insight: visualises the core economic relationship --
    as active orders rise, surge multiplier increases.
    Color encodes weather to show external-factor impact.
    """
    _setup()
    fig, ax = plt.subplots(figsize=(9, 6))

    weather_colors = {
        "Clear": "#2ecc71", "Cloudy": "#95a5a6", "Rain": "#3498db",
        "Storm": "#e74c3c", "Fog": "#f39c12",
    }
    for w, color in weather_colors.items():
        mask = df["weather"] == w
        ax.scatter(df.loc[mask, "active_orders"],
                   df.loc[mask, "surge_multiplier"],
                   c=color, label=w, alpha=0.35, s=12, edgecolors="none")

    ax.set_xlabel("Active Orders (Demand)", fontsize=12)
    ax.set_ylabel("Surge Multiplier", fontsize=12)
    ax.set_title("Surge Multiplier vs Real-Time Demand", fontsize=14, weight="bold")
    ax.legend(title="Weather", fontsize=9)
    ax.axhline(y=1.0, color="grey", ls="--", lw=0.8, label="No surge")
    ax.axhline(y=2.5, color="red", ls="--", lw=0.8, label="Surge cap")
    _save(fig, "surge_vs_demand.png")


# ===================================================================
# 2. Demand / Supply heatmap (hour x zone)
# ===================================================================

def plot_demand_supply_heatmap(df):
    """
    Business insight: reveals which zones and hours are chronically
    under-supplied, guiding rider allocation strategies.
    """
    _setup()
    pivot = df.pivot_table(
        values="demand_supply_ratio", index="zone_id", columns="hour",
        aggfunc="mean",
    )
    fig, ax = plt.subplots(figsize=(14, 6))
    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd",
                   interpolation="nearest")
    ax.set_xticks(range(24))
    ax.set_xticklabels(range(24), fontsize=8)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=8)
    ax.set_xlabel("Hour of Day", fontsize=12)
    ax.set_ylabel("Zone ID", fontsize=12)
    ax.set_title("Demand / Supply Ratio Heatmap (Hour x Zone)", fontsize=14, weight="bold")
    fig.colorbar(im, ax=ax, label="Demand / Supply Ratio")
    _save(fig, "demand_supply_heatmap.png")


# ===================================================================
# 3 & 4. Feature importance (regression + classification)
# ===================================================================

def _plot_feature_importance(importance_dict, title, filename, color):
    """Generic horizontal bar chart for feature importances."""
    _setup()
    if not importance_dict:
        print(f"  [graph] SKIP {filename} (no importances)")
        return
    # Top 15
    items = sorted(importance_dict.items(), key=lambda x: -x[1])[:15]
    names = [n.replace("num__", "").replace("cat__weather_", "weather=") for n, _ in items]
    vals = [v for _, v in items]

    fig, ax = plt.subplots(figsize=(8, 6))
    y_pos = np.arange(len(names))
    ax.barh(y_pos, vals, color=color, edgecolor="white")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Relative Importance", fontsize=11)
    ax.set_title(title, fontsize=13, weight="bold")
    for i, v in enumerate(vals):
        ax.text(v + 0.002, i, f"{v:.3f}", va="center", fontsize=8)
    _save(fig, filename)


def plot_feature_importance_reg(importance):
    _plot_feature_importance(importance,
        "Feature Importance -- Surge Multiplier (Regression)",
        "feature_importance_reg.png", "#3498db")


def plot_feature_importance_clf(importance):
    _plot_feature_importance(importance,
        "Feature Importance -- Peak-Hour Detection (Classification)",
        "feature_importance_clf.png", "#e67e22")


# ===================================================================
# 5. Model comparison -- Regression
# ===================================================================

def plot_model_comparison_reg(results):
    """
    Business insight: side-by-side comparison lets stakeholders see
    the accuracy-cost trade-off across model families.
    """
    _setup()
    names = list(results.keys())
    mae  = [results[n]["mae"] for n in names]
    rmse = [results[n]["rmse"] for n in names]
    r2   = [results[n]["r2"] for n in names]

    x = np.arange(len(names))
    w = 0.25
    fig, ax1 = plt.subplots(figsize=(10, 6))

    ax1.bar(x - w, mae, w, label="MAE", color="#3498db")
    ax1.bar(x, rmse, w, label="RMSE", color="#e74c3c")
    ax1.set_ylabel("Error (lower is better)", fontsize=11)
    ax1.set_xlabel("Model", fontsize=11)
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, fontsize=9)

    # R2 on secondary axis
    ax2 = ax1.twinx()
    ax2.bar(x + w, r2, w, label="R2", color="#2ecc71", alpha=0.7)
    ax2.set_ylabel("R-squared (higher is better)", fontsize=11)
    ax2.set_ylim(0, 1.1)

    # Legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)

    ax1.set_title("Regression Model Comparison -- Surge Multiplier",
                   fontsize=13, weight="bold")
    _save(fig, "model_comparison_reg.png")


# ===================================================================
# 6. Model comparison -- Classification
# ===================================================================

def plot_model_comparison_clf(results):
    _setup()
    names = list(results.keys())
    acc = [results[n]["accuracy"] for n in names]
    f1  = [results[n]["f1"] for n in names]

    x = np.arange(len(names))
    w = 0.30
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.bar(x - w/2, acc, w, label="Accuracy", color="#3498db")
    ax.bar(x + w/2, f1, w, label="F1-Score", color="#e67e22")
    ax.set_ylabel("Score (higher is better)", fontsize=11)
    ax.set_xlabel("Model", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylim(0.5, 1.05)
    ax.legend(fontsize=10)
    ax.set_title("Classification Model Comparison -- Peak-Hour Detection",
                  fontsize=13, weight="bold")

    # Annotate bars
    for i, (a, f) in enumerate(zip(acc, f1)):
        ax.text(i - w/2, a + 0.01, f"{a:.3f}", ha="center", fontsize=8)
        ax.text(i + w/2, f + 0.01, f"{f:.3f}", ha="center", fontsize=8)
    _save(fig, "model_comparison_clf.png")


# ===================================================================
# 7. Surge distribution histogram
# ===================================================================

def plot_surge_distribution(df):
    """
    Business insight: shows the frequency of different surge levels.
    Helps the pricing team understand how often customers see elevated fees.
    """
    _setup()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(df["surge_multiplier"], bins=50, color="#8e44ad",
            edgecolor="white", alpha=0.85)
    ax.axvline(df["surge_multiplier"].mean(), color="red", ls="--",
               label=f'Mean = {df["surge_multiplier"].mean():.2f}')
    ax.axvline(df["surge_multiplier"].median(), color="blue", ls="--",
               label=f'Median = {df["surge_multiplier"].median():.2f}')
    ax.set_xlabel("Surge Multiplier", fontsize=12)
    ax.set_ylabel("Frequency", fontsize=12)
    ax.set_title("Distribution of Surge Multiplier", fontsize=14, weight="bold")
    ax.legend(fontsize=10)
    _save(fig, "surge_distribution.png")


# ===================================================================
# 8. Hourly surge profile
# ===================================================================

def plot_hourly_surge_profile(df):
    """
    Business insight: pinpoints peak-hour windows, useful for pre-
    positioning riders and setting marketing push schedules.
    """
    _setup()
    hourly = df.groupby("hour")["surge_multiplier"].agg(["mean", "std"]).reset_index()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(hourly["hour"], hourly["mean"], marker="o", color="#e74c3c",
            linewidth=2, label="Mean Surge")
    ax.fill_between(hourly["hour"],
                    hourly["mean"] - hourly["std"],
                    hourly["mean"] + hourly["std"],
                    alpha=0.2, color="#e74c3c", label="+/- 1 SD")
    ax.set_xlabel("Hour of Day", fontsize=12)
    ax.set_ylabel("Surge Multiplier", fontsize=12)
    ax.set_title("Average Surge by Hour of Day", fontsize=14, weight="bold")
    ax.set_xticks(range(24))
    ax.legend(fontsize=10)
    _save(fig, "hourly_surge_profile.png")


# ===================================================================
# 9. Weather impact box plot
# ===================================================================

def plot_weather_impact(df):
    """
    Business insight: quantifies how weather conditions affect surge,
    informing weather-aware pricing policy and rider incentives.
    """
    _setup()
    order = ["Clear", "Cloudy", "Fog", "Rain", "Storm"]
    data = [df.loc[df["weather"] == w, "surge_multiplier"].values for w in order]

    fig, ax = plt.subplots(figsize=(8, 5))
    bp = ax.boxplot(data, labels=order, patch_artist=True, notch=True)
    colors = ["#2ecc71", "#95a5a6", "#f39c12", "#3498db", "#e74c3c"]
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.6)
    ax.set_xlabel("Weather Condition", fontsize=12)
    ax.set_ylabel("Surge Multiplier", fontsize=12)
    ax.set_title("Impact of Weather on Surge Pricing", fontsize=14, weight="bold")
    _save(fig, "weather_impact.png")


# ===================================================================
# 10. Safety layer before / after scatter
# ===================================================================

def plot_safety_layer_demo(raw_surges, safe_surges):
    """
    Business insight: demonstrates that the safety layer effectively
    clamps extreme predictions while leaving moderate surges intact.
    """
    _setup()
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(raw_surges, safe_surges, alpha=0.3, s=10, c="#3498db",
               edgecolors="none")
    ax.plot([0.5, 3.0], [0.5, 3.0], "k--", lw=1, label="y = x (no change)")
    ax.axhline(2.5, color="red", ls=":", lw=1, label="Surge cap = 2.5x")
    ax.axhline(1.0, color="green", ls=":", lw=1, label="Surge floor = 1.0x")
    ax.set_xlabel("Raw Model Prediction", fontsize=12)
    ax.set_ylabel("After Safety Layer", fontsize=12)
    ax.set_title("Safety Layer: Before vs After Clamping", fontsize=14, weight="bold")
    ax.legend(fontsize=9)
    ax.set_xlim(0.5, 3.0)
    ax.set_ylim(0.5, 3.0)
    ax.set_aspect("equal")
    _save(fig, "safety_layer_demo.png")


# ===================================================================
# Orchestrator
# ===================================================================

def generate_all_graphs(df_eng, results, raw_surges=None, safe_surges=None):
    """
    Generate all 10 research-ready visualizations.

    Parameters
    ----------
    df_eng : engineered DataFrame (with demand_supply_ratio etc.)
    results : dict loaded from results.json
    raw_surges, safe_surges : arrays for safety-layer demo
    """
    _setup()
    print("\n[generate_graphs] Generating visualizations ...")

    reg_results = results["regression"]["models"]
    clf_results = results["classification"]["models"]
    fi_reg = results["regression"].get("feature_importance", {})
    fi_clf = results["classification"].get("feature_importance", {})

    plot_surge_vs_demand(df_eng)
    plot_demand_supply_heatmap(df_eng)
    plot_feature_importance_reg(fi_reg)
    plot_feature_importance_clf(fi_clf)
    plot_model_comparison_reg(reg_results)
    plot_model_comparison_clf(clf_results)
    plot_surge_distribution(df_eng)
    plot_hourly_surge_profile(df_eng)
    plot_weather_impact(df_eng)

    if raw_surges is not None and safe_surges is not None:
        plot_safety_layer_demo(raw_surges, safe_surges)

    print("[generate_graphs] Done -- 10 figures saved.\n")
