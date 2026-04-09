"""
=============================================================================
Feature Engineering Pipeline for Delivery Time Prediction
=============================================================================

Transforms raw delivery data into ML-ready feature matrices.

Engineering steps:
1. Haversine distance  – recomputed from raw lat/lon as a validation /
   alternative to the straight-line distance already stored.
2. Cyclical time encoding – sin/cos transform for hour-of-day so that
   23:00 and 00:00 are numerically close (standard trick for periodic
   features).
3. One-hot encoding – for categorical columns (weather, traffic_level,
   rider_availability, order_size).
4. Standard scaling – for continuous features so gradient-based models
   (MLP) converge faster.  Tree models are scale-invariant but it
   doesn't hurt them.
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from pathlib import Path


# ─── Haversine (same vectorised version as in generator) ─────────────────────
def haversine_km(lat1, lon1, lat2, lon2):
    """
    Great-circle distance between two coordinate arrays (km).

    Why Haversine?
        It gives the shortest distance over the Earth's surface, which
        is more accurate than Euclidean distance on lat/lon pairs.  For
        city-scale distances (< 50 km) the error vs. Vincenty is < 0.1 %.
    """
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


# ─── Cyclical time encoding ──────────────────────────────────────────────────
def cyclical_encode(values: np.ndarray, period: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Map a periodic feature to sin/cos pair.

    Why cyclical?
        Raw integers (e.g. hour = 0, 1, …, 23) imply a false ordinal
        relationship where 23 → 0 is a huge jump.  Sin/cos encoding
        places them on a circle so the distance is smooth and continuous.
    """
    angle = 2 * np.pi * values / period
    return np.sin(angle), np.cos(angle)


# ─── Feature columns ─────────────────────────────────────────────────────────
CATEGORICAL_COLS = ["weather", "traffic_level", "rider_availability", "order_size"]
NUMERIC_COLS     = [
    "distance_km",
    "haversine_km",           # engineered
    "hour_sin", "hour_cos",   # engineered
    "day_sin",  "day_cos",    # engineered
    "prep_time_min",
    "historical_avg_delivery_min",
]
TARGET = "delivery_time_min"


# ─── Main pipeline builder ───────────────────────────────────────────────────
def engineer_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, object, list[str]]:
    """
    Accept raw DataFrame, return (X, y, fitted_transformer, feature_names).

    Automatically detects and includes OSM road-distance columns and
    GNN embedding columns if present in the dataframe.

    Returns
    -------
    X : np.ndarray  – feature matrix (num_samples × num_features)
    y : np.ndarray  – target vector
    transformer : ColumnTransformer  – fitted, reusable for inference
    feature_names : list[str]  – ordered column names after transform
    """
    df = df.copy()

    # --- 1.  Haversine distance (validation feature) -------------------------
    df["haversine_km"] = haversine_km(
        df["restaurant_lat"].values,
        df["restaurant_lon"].values,
        df["customer_lat"].values,
        df["customer_lon"].values,
    )

    # --- 2.  Cyclical encoding for hour and day-of-week ----------------------
    df["hour_sin"], df["hour_cos"] = cyclical_encode(df["order_hour"].values, 24.0)
    df["day_sin"],  df["day_cos"]  = cyclical_encode(df["day_of_week"].values, 7.0)

    num_cols = list(NUMERIC_COLS)

    # --- 3.  Build sklearn ColumnTransformer ---------------------------------
    #     Numeric → StandardScaler
    #     Categorical → OneHotEncoder (drop first to avoid multicollinearity)
    numeric_transformer = Pipeline([
        ("scaler", StandardScaler()),
    ])

    categorical_transformer = Pipeline([
        ("onehot", OneHotEncoder(drop="first", sparse_output=False, handle_unknown="ignore")),
    ])

    transformer = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, num_cols),
            ("cat", categorical_transformer, CATEGORICAL_COLS),
        ],
        remainder="drop",  # drop raw lat/lon, raw hour/day
    )

    X_raw = df[num_cols + CATEGORICAL_COLS]
    y     = df[TARGET].values

    X = transformer.fit_transform(X_raw)

    # --- 4.  Collect final feature names (for interpretability) ---------------
    cat_feature_names = (
        transformer.named_transformers_["cat"]
        .named_steps["onehot"]
        .get_feature_names_out(CATEGORICAL_COLS)
        .tolist()
    )
    feature_names = list(num_cols) + cat_feature_names

    print(f"[feature_engineering] X shape: {X.shape}  |  y shape: {y.shape}")
    print(f"[feature_engineering] Features ({len(feature_names)}): {feature_names}")

    return X, y, transformer, feature_names


# ─── Convenience: transform new data with an already-fitted transformer ──────
def transform_new(df: pd.DataFrame, transformer) -> np.ndarray:
    """Apply same feature engineering to new/unseen data (no target needed).

    Automatically infers which columns the fitted transformer expects.
    """
    df = df.copy()
    df["haversine_km"] = haversine_km(
        df["restaurant_lat"].values,
        df["restaurant_lon"].values,
        df["customer_lat"].values,
        df["customer_lon"].values,
    )
    df["hour_sin"], df["hour_cos"] = cyclical_encode(df["order_hour"].values, 24.0)
    df["day_sin"],  df["day_cos"]  = cyclical_encode(df["day_of_week"].values, 7.0)

    # Infer the columns the fitted transformer expects
    expected_cols = []
    for name, _, cols in transformer.transformers_:
        expected_cols.extend(cols)
    return transformer.transform(df[expected_cols])


# ─── Ablation variant (for controlled experiments) ───────────────────────────
def engineer_features_ablation(
    df: pd.DataFrame,
    drop_haversine: bool = False,
    drop_cyclical: bool = False,
    drop_categories: bool = False,
    skip_scaling: bool = False,
) -> tuple[np.ndarray, np.ndarray, object, list[str]]:
    """
    Same as engineer_features but with toggles to disable individual
    engineering steps for the ablation study.
    """
    df = df.copy()

    # Haversine
    if not drop_haversine:
        df["haversine_km"] = haversine_km(
            df["restaurant_lat"].values, df["restaurant_lon"].values,
            df["customer_lat"].values,   df["customer_lon"].values,
        )

    # Cyclical encoding
    if not drop_cyclical:
        df["hour_sin"], df["hour_cos"] = cyclical_encode(df["order_hour"].values, 24.0)
        df["day_sin"],  df["day_cos"]  = cyclical_encode(df["day_of_week"].values, 7.0)

    # Build column lists for this ablation config
    num_cols = list(NUMERIC_COLS)
    if drop_haversine:
        num_cols = [c for c in num_cols if c != "haversine_km"]
    if drop_cyclical:
        num_cols = [c for c in num_cols
                    if c not in ("hour_sin", "hour_cos", "day_sin", "day_cos")]
        # Add raw integer columns instead
        num_cols.extend(["order_hour", "day_of_week"])

    cat_cols = [] if drop_categories else list(CATEGORICAL_COLS)

    # Transformers
    from sklearn.preprocessing import StandardScaler, OneHotEncoder, FunctionTransformer
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline

    if skip_scaling:
        num_tfm = Pipeline([("passthrough", FunctionTransformer())])
    else:
        num_tfm = Pipeline([("scaler", StandardScaler())])

    transformers = [("num", num_tfm, num_cols)]
    if cat_cols:
        cat_tfm = Pipeline([("onehot", OneHotEncoder(
            drop="first", sparse_output=False, handle_unknown="ignore"))])
        transformers.append(("cat", cat_tfm, cat_cols))

    transformer = ColumnTransformer(transformers=transformers, remainder="drop")

    all_cols = num_cols + cat_cols
    X = transformer.fit_transform(df[all_cols])
    y = df[TARGET].values

    # Feature names
    feature_names = list(num_cols)
    if cat_cols and "cat" in transformer.named_transformers_:
        cat_names = (transformer.named_transformers_["cat"]
                     .named_steps["onehot"]
                     .get_feature_names_out(cat_cols).tolist())
        feature_names += cat_names

    return X, y, transformer, feature_names


# ─── CLI test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    csv = Path(__file__).parent / "data" / "delivery_dataset.csv"
    if not csv.exists():
        from dataset_generator import generate_dataset
        generate_dataset()
    df = pd.read_csv(csv)
    X, y, tfm, names = engineer_features(df)
    print(f"\nFirst row (transformed): {X[0].round(3)}")
