"""
Churn Prediction Service Router
================================
Wraps the Churn-Prediction project as a FastAPI APIRouter.

Endpoint:  POST /api/churn/predict
"""
import os
import json
import asyncio
import numpy as np
import pandas as pd
import joblib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import get_service_dir

router = APIRouter(prefix="/api/churn", tags=["Churn Prediction"])

SERVICE_DIR = get_service_dir("Churn-Prediction")
OUTPUT_DIR = os.path.join(SERVICE_DIR, "outputs")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_model = None
_transformer = None
_feature_names = None
_initialized = False
_error = None
_model_source = "unavailable"

# ---------------------------------------------------------------------------
# Feature definitions (from original app.py)
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
# Init
# ---------------------------------------------------------------------------
def init():
    global _model, _transformer, _feature_names, _initialized, _error, _model_source
    try:
        _model = joblib.load(os.path.join(OUTPUT_DIR, "best_model.joblib"))
        _transformer = joblib.load(os.path.join(OUTPUT_DIR, "transformer.joblib"))
        with open(os.path.join(OUTPUT_DIR, "feature_names.json")) as f:
            _feature_names = json.load(f)

        # Validate the loaded pipeline once so incompatible sklearn internals
        # do not fail during live requests.
        smoke_row = {"user_id": 0, "churn": 0}
        smoke_row.update({f: 0.0 for f in NUMERIC_RAW})
        smoke_row.update({f: 0.0 for f in ENGINEERED})
        smoke_df = pd.DataFrame([smoke_row])
        smoke_X = _transformer.transform(smoke_df)
        _ = _model.predict_proba(smoke_X)

        _initialized = True
        _model_source = "trained_model"
        _error = None
        print(f"  [churn] Loaded model ({len(_feature_names)} features)")
    except Exception as e:
        _error = str(e)
        _model = None
        _transformer = None
        _feature_names = ALL_FEATURES
        _initialized = True
        _model_source = "heuristic_fallback"
        print(f"  [churn] WARNING: using heuristic fallback ({e})")


# ---------------------------------------------------------------------------
# Helpers (from original app.py)
# ---------------------------------------------------------------------------
def _engineer(raw: dict) -> dict:
    feat = dict(raw)
    o30 = raw.get("orders_last_30d", 0)
    o90 = raw.get("orders_last_90d", 1)
    feat["engagement_decay"] = o30 / (o90 + 1e-6)
    aov = raw.get("avg_order_value", 0)
    freq = raw.get("order_frequency", 0)
    feat["order_value_frequency"] = aov * freq
    rating = raw.get("avg_user_rating", 3.0)
    delay = raw.get("avg_delivery_delay_min", 0)
    complaints = raw.get("num_complaints", 0)
    feat["experience_score"] = rating - 0.1 * delay - 0.3 * complaints
    recency = raw.get("days_since_last_order", 0)
    feat["recency_frequency"] = recency / (freq + 1e-6)
    tenure = raw.get("account_age_days", 1)
    feat["complaint_rate"] = complaints / (tenure + 1e-6) * 365
    return feat


def _classify_risk(prob: float) -> tuple:
    if prob < 0.30:
        return "low", "No action needed -- user is healthy."
    elif prob < 0.60:
        return "medium", "Send loyalty reward or push notification to re-engage."
    else:
        return "high", "Offer personalised discount and schedule direct outreach."


def _heuristic_probability(raw: dict) -> float:
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
# Pydantic Models
# ---------------------------------------------------------------------------
class ChurnRequest(BaseModel):
    orders_last_30d: float
    orders_last_90d: float
    avg_order_value: float
    days_since_last_order: float
    order_frequency: float
    cancellation_rate: float
    avg_delivery_delay_min: float
    avg_user_rating: float
    num_complaints: float
    discount_usage_rate: float
    app_sessions_per_week: float
    preferred_order_hour: float
    account_age_days: float


class ChurnResponse(BaseModel):
    churn_probability: float
    risk_level: str
    recommended_action: str
    features_used: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/predict", response_model=ChurnResponse)
async def predict_churn(req: ChurnRequest):
    """Predict churn probability for a user."""
    global _model, _transformer, _model_source, _error

    if not _initialized:
        await asyncio.to_thread(init)

    raw = req.model_dump()
    full = _engineer(raw)

    row = {"user_id": 0}
    row.update({f: full.get(f, 0.0) for f in NUMERIC_RAW})
    row["churn"] = 0
    row.update({f: full.get(f, 0.0) for f in ENGINEERED})
    df_input = pd.DataFrame([row])

    try:
        if _model is not None and _transformer is not None:
            X = _transformer.transform(df_input)
            prob = float(_model.predict_proba(X)[:, 1][0])
        else:
            prob = _heuristic_probability(raw)
    except Exception as e:
        _model = None
        _transformer = None
        _model_source = "heuristic_fallback"
        _error = f"model_runtime_incompatible: {e}"
        prob = _heuristic_probability(raw)

    risk_level, action = _classify_risk(prob)

    return ChurnResponse(
        churn_probability=round(prob, 4),
        risk_level=risk_level,
        recommended_action=action,
        features_used=len(ALL_FEATURES),
    )


@router.get("/health")
async def health():
    return {
        "status": "ok" if _initialized else "unavailable",
        "service": "churn-prediction",
        "error": _error,
        "model_source": _model_source,
    }
