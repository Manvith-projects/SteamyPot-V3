"""
delivery_predictor.py — ML-Based Delivery Time Prediction
===========================================================
Builds a lightweight Gradient-Boosted regression model that predicts
the estimated delivery time (minutes) for a given (driver, order) pair.

AI Concept: Feature-Engineered Regression for ETA
---------------------------------------------------
Instead of a simple distance/speed heuristic, we train a GBT regressor
on composite features:

  ┌──────────────────────────────────────────────────────────────────┐
  │ Feature              │ Why it matters                           │
  ├──────────────────────┼──────────────────────────────────────────┤
  │ distance_km          │ Dominant factor in travel time           │
  │ driver active orders │ More orders → slower fulfilment          │
  │ avg_delivery_time    │ Historical driver speed baseline         │
  │ estimated_prep_time  │ Food must be ready before pickup         │
  │ order_size           │ Large orders take longer to hand off     │
  │ driver_rating        │ Proxy for professionalism / efficiency   │
  │ success_rate         │ High success → fewer detours / failures  │
  └──────────────────────┴──────────────────────────────────────────┘

The model is trained on synthetically generated trips (see
`_generate_training_data`) whose labels follow a physics-informed
formula with realistic noise, so the learned model can generalise
to unseen driver-order combinations.

Training happens once at startup if no saved model is found.
"""

import os
import math
import random
import pickle
import numpy as np

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

SEED = 42
MODEL_PATH = os.path.join("outputs", "delivery_time_model.pkl")


# -----------------------------------------------------------------------
# Haversine distance (km)
# -----------------------------------------------------------------------
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two GPS points in kilometres."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# -----------------------------------------------------------------------
# Synthetic training data
# -----------------------------------------------------------------------
def _generate_training_data(n: int = 5000) -> tuple[np.ndarray, np.ndarray]:
    """
    Produce synthetic training samples.

    Label formula (physics-informed + noise):
      ETA = prep_time
            + (distance_km / avg_speed_kmh) * 60     ← travel
            + active_orders * 4                       ← queue penalty
            + order_size * 1.2                        ← handoff time
            + noise

    avg_speed_kmh is sampled 18-30 km/h (city driving).
    """
    rng = np.random.RandomState(SEED)

    distance_km       = rng.uniform(0.5, 15.0, n)
    active_orders     = rng.randint(0, 5, n).astype(float)
    avg_del_time      = rng.uniform(15, 50, n)
    prep_time         = rng.uniform(5, 30, n)
    order_size        = rng.randint(1, 8, n).astype(float)
    driver_rating     = rng.uniform(3.0, 5.0, n)
    success_rate      = rng.uniform(0.75, 1.0, n)

    # Label
    avg_speed = rng.uniform(18, 30, n)
    travel_min = (distance_km / avg_speed) * 60
    eta = (
        prep_time
        + travel_min
        + active_orders * 4.0
        + order_size * 1.2
        - (driver_rating - 3.0) * 2.0   # better drivers shave time
        - (success_rate - 0.75) * 8.0    # reliable drivers are faster
        + rng.normal(0, 2.5, n)          # noise
    )
    eta = np.clip(eta, 8, 90)

    X = np.column_stack(
        [distance_km, active_orders, avg_del_time,
         prep_time, order_size, driver_rating, success_rate]
    )
    return X, eta


# -----------------------------------------------------------------------
# Train / load model
# -----------------------------------------------------------------------
def train_model(force: bool = False) -> GradientBoostingRegressor:
    """Train (or load cached) GBT regressor for delivery ETA."""
    if not force and os.path.exists(MODEL_PATH):
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)
        print(f"[delivery_predictor] [OK] Loaded model from {MODEL_PATH}")
        return model

    print("[delivery_predictor] Training delivery-time model …")
    X, y = _generate_training_data()
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=SEED
    )

    model = GradientBoostingRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.8,
        random_state=SEED,
    )
    model.fit(X_tr, y_tr)

    preds = model.predict(X_te)
    mae = mean_absolute_error(y_te, preds)
    r2 = r2_score(y_te, preds)
    print(f"[delivery_predictor] [OK] MAE={mae:.2f} min  R2={r2:.4f}")

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    print(f"[delivery_predictor] [OK] Saved to {MODEL_PATH}")
    return model


# -----------------------------------------------------------------------
# Prediction helper
# -----------------------------------------------------------------------
def predict_eta(
    model: GradientBoostingRegressor,
    distance_km: float,
    active_orders: int,
    avg_delivery_time: float,
    prep_time: float,
    order_size: int,
    driver_rating: float,
    success_rate: float,
) -> float:
    """Predict delivery ETA (minutes) for one driver-order pair."""
    X = np.array(
        [[distance_km, active_orders, avg_delivery_time,
          prep_time, order_size, driver_rating, success_rate]]
    )
    eta = model.predict(X)[0]
    return round(max(8.0, eta), 1)


# -----------------------------------------------------------------------
# CLI test
# -----------------------------------------------------------------------
if __name__ == "__main__":
    m = train_model(force=True)
    sample_eta = predict_eta(m, 5.0, 1, 25.0, 15.0, 3, 4.2, 0.92)
    print(f"Sample prediction: {sample_eta} min")
