"""
feature_engineering.py  --  Churn Prediction Feature Pipeline
=============================================================
Transforms the raw user-level dataset into an ML-ready feature matrix.

Business reasoning behind every transformation
-----------------------------------------------
  * **RFM features** (Recency / Frequency / Monetary):
      The gold-standard customer segmentation framework.  Recency alone
      predicts ~60 % of churn variance in most platforms.
  * **Engagement decay** -- ratio of 30-day orders to 90-day orders.
      A ratio < 0.33 means the user is ordering less than before -> churn risk.
  * **Experience score** -- composite of delay + complaints + rating.
      Captures overall satisfaction in a single number.
  * **Missing-value imputation** -- median fill for numeric NaNs.
      Preserves distribution shape without extreme sensitivity.
  * **Standard scaling** -- necessary for Logistic Regression convergence
      and helpful for tree models' speed.

ML concept: Feature engineering
-------------------------------
Raw data rarely maps cleanly to the patterns a model needs.  Feature
engineering creates *derived* features that encode domain knowledge
(e.g., "a user whose order rate dropped 50 % is at risk") so the model
starts with a head-start instead of learning everything from scratch.
"""

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
import joblib
import os

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED = 42
OUTPUT_DIR = "outputs"

# Raw numeric columns from the dataset (used by the preprocessor)
NUMERIC_RAW = [
    "orders_last_30d", "orders_last_90d", "avg_order_value",
    "days_since_last_order", "order_frequency", "cancellation_rate",
    "avg_delivery_delay_min", "avg_user_rating", "num_complaints",
    "discount_usage_rate", "app_sessions_per_week",
    "preferred_order_hour", "account_age_days",
]

# Engineered columns added by engineer_features()
ENGINEERED = [
    "engagement_decay",       # 30d / 90d order ratio
    "order_value_frequency",  # avg_order_value * order_frequency (monetary power)
    "experience_score",       # composite satisfaction score
    "recency_frequency",      # days_since * (1 / frequency) -- RFM cross-term
    "complaint_rate",         # complaints per 90 days of account age
]

# All numeric features fed into the model
ALL_NUMERIC = NUMERIC_RAW + ENGINEERED

# Target column
TARGET = "churn"


# ---------------------------------------------------------------------------
# Core feature engineering
# ---------------------------------------------------------------------------

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived features to a copy of *df*.

    ML concept: each derived feature encodes a specific business hypothesis
    about what drives churn, letting the model learn faster and more
    accurately than from raw columns alone.

    Steps
    -----
    1. **Engagement decay** = orders_last_30d / (orders_last_90d / 3)
       Measures recent engagement vs historical baseline.
       Value < 1 means the user is slowing down -> churn signal.

    2. **Order-value * frequency** (monetary power)
       High spenders who order often are sticky; this interaction term
       captures that joint effect.

    3. **Experience score** = rating - 0.1*delay - 0.3*complaints
       A single "satisfaction proxy" -- lower score = worse experience.

    4. **Recency-frequency cross-term** = days_since / (frequency + 0.1)
       High values mean "long gap relative to normal cadence" -- strong
       churn predictor that neither feature alone captures.

    5. **Complaint rate** = complaints / (account_age_days / 90)
       Normalises complaints by tenure so a 2-year user with 3 complaints
       is treated differently from a 2-month user with 3 complaints.
    """
    df = df.copy()

    # 1. Engagement decay (safe division)
    avg_monthly_90d = df["orders_last_90d"] / 3.0
    df["engagement_decay"] = np.where(
        avg_monthly_90d > 0,
        df["orders_last_30d"] / avg_monthly_90d,
        0.0
    ).round(4)

    # 2. Monetary power (order value x frequency interaction)
    df["order_value_frequency"] = (
        df["avg_order_value"].fillna(df["avg_order_value"].median())
        * df["order_frequency"]
    ).round(2)

    # 3. Experience score (composite satisfaction)
    delay = df["avg_delivery_delay_min"].fillna(df["avg_delivery_delay_min"].median())
    rating = df["avg_user_rating"].fillna(df["avg_user_rating"].median())
    df["experience_score"] = (
        rating - 0.1 * delay - 0.3 * df["num_complaints"]
    ).round(3)

    # 4. Recency-frequency cross-term
    df["recency_frequency"] = (
        df["days_since_last_order"] / (df["order_frequency"] + 0.1)
    ).round(3)

    # 5. Complaint rate (normalised by tenure in 90-day blocks)
    tenure_blocks = df["account_age_days"] / 90.0
    df["complaint_rate"] = np.where(
        tenure_blocks > 0,
        df["num_complaints"] / tenure_blocks,
        0.0
    ).round(4)

    return df


# ---------------------------------------------------------------------------
# Preprocessor (imputation + scaling)
# ---------------------------------------------------------------------------

def build_preprocessor() -> ColumnTransformer:
    """
    Build a scikit-learn pipeline that:
      1. Imputes missing numeric values with the column median.
         (ML concept: median is robust to outliers, unlike mean.)
      2. Scales all features to zero-mean, unit-variance.
         (ML concept: Logistic Regression uses gradient descent, which
          converges much faster when features are on the same scale.
          Tree models don't *need* scaling but aren't hurt by it.)

    Returns a ColumnTransformer ready to be .fit() on training data.
    """
    numeric_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, ALL_NUMERIC),
        ],
        remainder="drop",
    )
    return preprocessor


# ---------------------------------------------------------------------------
# Prepare X / y
# ---------------------------------------------------------------------------

def prepare_data(df: pd.DataFrame, fit_transformer: bool = True,
                 transformer=None):
    """
    End-to-end data preparation.

    ML concept: the same preprocessing (imputation thresholds, scaler
    mean/std) fitted on the training set must be reused at inference to
    avoid data leakage.

    Parameters
    ----------
    df : raw DataFrame from dataset_generator.
    fit_transformer : True -> fit new preprocessor (training).
                      False -> reuse *transformer* (inference).
    transformer     : pre-fitted ColumnTransformer.

    Returns
    -------
    X              : np.ndarray  feature matrix
    y              : np.ndarray  churn labels (0 / 1)
    transformer    : fitted ColumnTransformer
    feature_names  : list[str]
    df_eng         : engineered DataFrame
    """
    # 1. Feature engineering
    df_eng = engineer_features(df)

    # 2. Preprocessing
    if fit_transformer:
        transformer = build_preprocessor()
        X = transformer.fit_transform(df_eng)
    else:
        assert transformer is not None, "Provide a fitted transformer for inference"
        X = transformer.transform(df_eng)

    # 3. Target
    y = df_eng[TARGET].values

    # 4. Feature names
    try:
        feature_names = list(transformer.get_feature_names_out())
    except Exception:
        feature_names = [f"f{i}" for i in range(X.shape[1])]

    return X, y, transformer, feature_names, df_eng


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------

def save_transformer(transformer, path=None):
    path = path or os.path.join(OUTPUT_DIR, "transformer.joblib")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(transformer, path)
    print(f"[feature_engineering] Transformer saved -> {path}")


def load_transformer(path=None):
    path = path or os.path.join(OUTPUT_DIR, "transformer.joblib")
    return joblib.load(path)
