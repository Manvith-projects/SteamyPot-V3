"""
feature_engineering.py
======================
Transforms the raw synthetic dataset into ML-ready feature matrices.

Business reasoning behind every transformation:
  * Cyclical encoding (sin/cos) for hour & day -- ML models cannot learn
    that hour 23 is close to hour 0 from raw integers.
  * Demand/Supply ratio -- the single most important driver of surge.
  * Distance -- longer deliveries incur higher base fees and riders are
    less willing to accept them during peaks, amplifying the surge.
  * Moving-average demand (simulated 1-hour window) -- captures momentum;
    a zone with rising demand should start surging *before* it peaks.
  * One-hot encoding for weather -- distinct effect per category (rain != fog).
  * Zone-level aggregates -- some zones are structurally busier.
"""

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
import joblib
import os

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED = 42
OUTPUT_DIR = "outputs"

# Columns coming from the dataset
NUMERIC_RAW = [
    "hour", "day_of_week", "is_holiday", "traffic_level",
    "active_orders", "available_riders", "avg_prep_time_min",
    "zone_id", "distance_km", "hist_demand_trend", "hist_cancel_rate",
]
CATEGORICAL = ["weather"]

# Engineered numeric columns (added during feature engineering)
ENGINEERED = [
    "hour_sin", "hour_cos",
    "day_sin", "day_cos",
    "demand_supply_ratio",
    "moving_avg_demand",
    "demand_supply_interaction",   # orders * (1 / riders)
    "distance_surge_interaction",  # distance * demand_supply_ratio
    "traffic_weather_score",       # composite external-difficulty score
]

# All numeric columns after engineering
ALL_NUMERIC = NUMERIC_RAW + ENGINEERED

# Regression target & classification target
TARGET_REG = "surge_multiplier"
TARGET_CLF = "is_peak_hour"


# ---------------------------------------------------------------------------
# Core engineering function
# ---------------------------------------------------------------------------

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived columns to a copy of *df*.

    Steps (with business motivation):
    1. **Cyclical encoding** -- hour & day_of_week mapped to sin/cos so
       the model knows that 23:00 is close to 00:00 and Sunday is close
       to Monday.
    2. **Demand / Supply ratio** -- the primary economic signal. When
       ratio > 1 the zone is under-supplied and prices should rise.
    3. **Moving-average demand (1-hr window)** -- simulated via a rolling
       mean grouped by zone, sorted by hour. Captures short-term trend.
    4. **Demand-supply interaction** -- non-linear cross-term that lets
       tree models split more precisely.
    5. **Distance-surge interaction** -- captures the business reality that
       long-distance orders are even harder to fulfil during demand spikes;
       riders prefer short trips when they can choose.
    6. **Traffic-weather composite** -- a single score that summarises
       external delivery difficulty (bad weather + heavy traffic).
    """
    df = df.copy()

    # 1. Cyclical encoding for hour (period = 24)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24.0)

    # 2. Cyclical encoding for day of week (period = 7)
    df["day_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7.0)
    df["day_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7.0)

    # 3. Demand / Supply ratio  (core surge driver)
    #    Epsilon avoids division-by-zero if available_riders == 0.
    df["demand_supply_ratio"] = (
        df["active_orders"] / (df["available_riders"] + 1e-3)
    ).round(4)

    # 4. Moving-average demand (simulate a 1-hour rolling window)
    #    Group by zone + sort by hour, then rolling mean with window = 3
    #    (3 consecutive hours ~ 1 hour neighbourhood).
    df = df.sort_values(["zone_id", "hour"]).reset_index(drop=True)
    df["moving_avg_demand"] = (
        df.groupby("zone_id")["active_orders"]
        .transform(lambda s: s.rolling(window=3, min_periods=1).mean())
    ).round(2)

    # 5. Demand-supply interaction term
    df["demand_supply_interaction"] = (
        df["active_orders"] * (1.0 / (df["available_riders"] + 1e-3))
    ).round(4)

    # 6. Distance-surge interaction
    #    Business: a 15 km delivery during a 3x demand/supply ratio is
    #    much harder to fulfil than a 2 km one -- this cross-term helps
    #    the model learn that non-linear relationship.
    df["distance_surge_interaction"] = (
        df["distance_km"] * df["demand_supply_ratio"]
    ).round(4)

    # 7. Traffic-weather composite score
    #    Weather severity: Clear=0, Cloudy=1, Fog=2, Rain=3, Storm=4
    weather_map = {"Clear": 0, "Cloudy": 1, "Fog": 2, "Rain": 3, "Storm": 4}
    df["traffic_weather_score"] = (
        df["traffic_level"] + df["weather"].map(weather_map)
    ).round(2)

    return df


# ---------------------------------------------------------------------------
# Sklearn column transformer builder
# ---------------------------------------------------------------------------

def build_preprocessor() -> ColumnTransformer:
    """
    Build a scikit-learn ColumnTransformer that:
      * Scales all numeric features to zero-mean / unit-variance.
      * One-hot encodes categorical features (weather).

    Returns a *fitted-ready* transformer (call .fit / .fit_transform).
    """
    numeric_pipe = Pipeline([
        ("scaler", StandardScaler()),
    ])
    cat_pipe = Pipeline([
        ("ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, ALL_NUMERIC),
            ("cat", cat_pipe, CATEGORICAL),
        ],
        remainder="drop",
    )
    return preprocessor


# ---------------------------------------------------------------------------
# Prepare X / y splits
# ---------------------------------------------------------------------------

def prepare_data(df: pd.DataFrame, fit_transformer: bool = True,
                 transformer=None):
    """
    End-to-end data preparation:
      1. Run feature engineering.
      2. Build (or reuse) the preprocessor.
      3. Transform features into a NumPy matrix.
      4. Extract regression & classification targets.

    Parameters
    ----------
    df : raw DataFrame from dataset_generator.
    fit_transformer : if True, fit a *new* preprocessor (training).
                      if False, reuse *transformer* (inference).
    transformer : pre-fitted ColumnTransformer (inference mode).

    Returns
    -------
    X         : np.ndarray  transformed feature matrix
    y_reg     : np.ndarray  surge_multiplier
    y_clf     : np.ndarray  is_peak_hour
    transformer : fitted ColumnTransformer
    feature_names : list[str]
    df_eng    : engineered DataFrame (for later analysis / plots)
    """
    # 1. Engineer features
    df_eng = engineer_features(df)

    # 2. Build / reuse transformer
    if fit_transformer:
        transformer = build_preprocessor()
        X = transformer.fit_transform(df_eng)
    else:
        assert transformer is not None, "Must provide transformer in inference mode"
        X = transformer.transform(df_eng)

    # 3. Targets
    y_reg = df_eng[TARGET_REG].values
    y_clf = df_eng[TARGET_CLF].values

    # 4. Feature names (for interpretability)
    try:
        feature_names = list(transformer.get_feature_names_out())
    except Exception:
        feature_names = [f"f{i}" for i in range(X.shape[1])]

    return X, y_reg, y_clf, transformer, feature_names, df_eng


# ---------------------------------------------------------------------------
# Save / load transformer
# ---------------------------------------------------------------------------

def save_transformer(transformer, path=None):
    path = path or os.path.join(OUTPUT_DIR, "transformer.joblib")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(transformer, path)
    print(f"[feature_engineering] Transformer saved -> {path}")


def load_transformer(path=None):
    path = path or os.path.join(OUTPUT_DIR, "transformer.joblib")
    return joblib.load(path)
