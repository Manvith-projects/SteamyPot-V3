"""
app.py  --  Churn Prediction Flask API
========================================
Serves a REST endpoint for real-time churn predictions.

Endpoints
---------
  POST /predict-churn
      Accept JSON payload with user features; return churn probability,
      risk level, and recommended retention action.

  GET /health
      Simple liveness check.

Response schema
---------------
  {
    "churn_probability": 0.72,
    "risk_level":        "high",            // low | medium | high
    "recommended_action": "send discount",  // retention strategy
    "features_used":     18
  }

Risk tiers
----------
  * **Low**   (p < 0.30) -- user is healthy.   Action: no action needed.
  * **Medium** (0.30 <= p < 0.60) -- early warning.  Action: loyalty reward / push notification.
  * **High**  (p >= 0.60) -- likely to churn.  Action: personalised discount / direct outreach.

ML concept: translating a raw probability into an actionable "risk tier"
lets non-technical stakeholders (marketing, ops) act without understanding
the model internals.
"""

import os
import json
import numpy as np
import pandas as pd
import joblib
from flask import Flask, request, jsonify

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
OUTPUT_DIR = "outputs"
MODEL_PATH = os.path.join(OUTPUT_DIR, "best_model.joblib")
TRANSFORMER_PATH = os.path.join(OUTPUT_DIR, "transformer.joblib")
FEATURE_NAMES_PATH = os.path.join(OUTPUT_DIR, "feature_names.json")

# ---------------------------------------------------------------------------
# Feature list (must match feature_engineering.py)
# ---------------------------------------------------------------------------
NUMERIC_RAW = [
    "orders_last_30d", "orders_last_90d", "avg_order_value",
    "days_since_last_order", "order_frequency", "cancellation_rate",
    "avg_delivery_delay_min", "avg_user_rating", "num_complaints",
    "discount_usage_rate", "app_sessions_per_week",
    "preferred_order_hour", "account_age_days",
]

ENGINEERED = [
    "engagement_decay", "order_value_frequency",
    "experience_score", "recency_frequency", "complaint_rate",
]

ALL_FEATURES = NUMERIC_RAW + ENGINEERED

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

_model = None
_transformer = None
_feature_names = None
_model_load_error = None


def _load_artefacts():
    """Lazy-load model and transformer on first request."""
    global _model, _transformer, _feature_names, _model_load_error
    if _model is not None and _transformer is not None:
        return
    try:
        _model = joblib.load(MODEL_PATH)
        _transformer = joblib.load(TRANSFORMER_PATH)
        with open(FEATURE_NAMES_PATH, "r") as f:
            _feature_names = json.load(f)
        _model_load_error = None
        print(f"[app] Model loaded from {MODEL_PATH}")
        print(f"[app] Transformer loaded from {TRANSFORMER_PATH}")
        print(f"[app] Feature names loaded ({len(_feature_names)} features)")
    except Exception as e:
        _model = None
        _transformer = None
        _feature_names = ALL_FEATURES
        _model_load_error = str(e)
        print(f"[app] WARNING: Using heuristic fallback (model load failed: {_model_load_error})")


def _heuristic_probability(raw: dict) -> float:
    """Fallback churn probability when trained artifacts are unavailable."""
    days = float(raw.get("days_since_last_order", 0.0))
    cancel = float(raw.get("cancellation_rate", 0.0))
    delay = float(raw.get("avg_delivery_delay_min", 0.0))
    complaints = float(raw.get("num_complaints", 0.0))
    sessions = float(raw.get("app_sessions_per_week", 0.0))
    orders30 = float(raw.get("orders_last_30d", 0.0))
    rating = float(raw.get("avg_user_rating", 4.0))

    score = 0.05
    score += min(days / 60.0, 1.0) * 0.30
    score += min(cancel / 0.40, 1.0) * 0.20
    score += min(delay / 40.0, 1.0) * 0.15
    score += min(complaints / 8.0, 1.0) * 0.10
    score += (1.0 - min(sessions / 14.0, 1.0)) * 0.10
    score += (1.0 - min(orders30 / 12.0, 1.0)) * 0.10
    score += (1.0 - min(max(rating - 2.5, 0.0) / 2.5, 1.0)) * 0.05

    return float(max(0.01, min(0.99, score)))


# ---------------------------------------------------------------------------
# Helper: engineer features from raw input
# ---------------------------------------------------------------------------

def _engineer(raw: dict) -> dict:
    """
    Compute engineered features from raw user metrics.

    ML concept: the API must replicate the *exact same* feature
    engineering that was applied during training.  Any mismatch
    (different formula, missing feature) leads to data leakage
    or prediction errors in production.
    """
    feat = dict(raw)

    # engagement_decay: recent activity / longer-term activity
    o30 = raw.get("orders_last_30d", 0)
    o90 = raw.get("orders_last_90d", 1)
    feat["engagement_decay"] = o30 / (o90 + 1e-6)

    # order_value_frequency: monetary × frequency interaction
    aov = raw.get("avg_order_value", 0)
    freq = raw.get("order_frequency", 0)
    feat["order_value_frequency"] = aov * freq

    # experience_score: satisfaction composite
    rating = raw.get("avg_user_rating", 3.0)
    delay = raw.get("avg_delivery_delay_min", 0)
    complaints = raw.get("num_complaints", 0)
    feat["experience_score"] = rating - 0.1 * delay - 0.3 * complaints

    # recency_frequency: cross-term
    recency = raw.get("days_since_last_order", 0)
    feat["recency_frequency"] = recency / (freq + 1e-6)

    # complaint_rate: normalised by tenure
    tenure = raw.get("account_age_days", 1)
    feat["complaint_rate"] = complaints / (tenure + 1e-6) * 365

    return feat


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

def _classify_risk(prob: float) -> tuple:
    """
    Map churn probability to risk tier and recommended action.

    Thresholds derived from business requirements:
    * < 30 %  -> low risk   : no intervention needed.
    * 30-60 % -> medium risk: gentle nudge (loyalty reward, notification).
    * >= 60 % -> high risk  : aggressive retention (discount, outreach).
    """
    if prob < 0.30:
        return "low", "No action needed -- user is healthy."
    elif prob < 0.60:
        return "medium", "Send loyalty reward or push notification to re-engage."
    else:
        return "high", "Offer personalised discount and schedule direct outreach."


# ---------------------------------------------------------------------------
# POST /predict-churn
# ---------------------------------------------------------------------------

@app.route("/predict-churn", methods=["POST"])
def predict_churn():
    """
    Predict churn for a single user.

    Expected JSON payload (all numeric, raw user metrics):
    {
      "orders_last_30d": 2,
      "orders_last_90d": 12,
      "avg_order_value": 320.0,
      "days_since_last_order": 18,
      "order_frequency": 3.0,
      "cancellation_rate": 0.12,
      "avg_delivery_delay_min": 8.5,
      "avg_user_rating": 3.8,
      "num_complaints": 1,
      "discount_usage_rate": 0.45,
      "app_sessions_per_week": 4.2,
      "preferred_order_hour": 19,
      "account_age_days": 280
    }
    """
    _load_artefacts()

    payload = request.get_json(force=True)

    # Validate required fields
    missing = [f for f in NUMERIC_RAW if f not in payload]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    # Build raw feature dict
    raw = {f: float(payload[f]) for f in NUMERIC_RAW}

    # Engineer features
    full = _engineer(raw)

    # Build a DataFrame matching the training schema (user_id + features + churn)
    # The ColumnTransformer was fit on the full df, so it expects all columns.
    row = {"user_id": 0}                          # dummy
    row.update({f: full.get(f, 0.0) for f in NUMERIC_RAW})
    row["churn"] = 0                               # dummy target
    row.update({f: full.get(f, 0.0) for f in ENGINEERED})
    df_input = pd.DataFrame([row])

    if _model is not None and _transformer is not None:
        X = _transformer.transform(df_input)
        prob = float(_model.predict_proba(X)[:, 1][0])
        model_source = "trained_model"
    else:
        prob = _heuristic_probability(raw)
        model_source = "heuristic_fallback"

    risk_level, action = _classify_risk(prob)

    return jsonify({
        "churn_probability":  round(prob, 4),
        "risk_level":         risk_level,
        "recommended_action": action,
        "features_used":      len(ALL_FEATURES),
        "model_source":       model_source,
        "model_warning":      _model_load_error,
    })


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "churn-prediction"})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _load_artefacts()
    print("[app] Starting Churn Prediction API on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
