"""
Dynamic Pricing Service Router
================================
Wraps the Dynamic-Pricing project as a FastAPI APIRouter.

Endpoint:  POST /api/pricing/calculate
"""
import os
import traceback
import numpy as np
import pandas as pd
import joblib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from services import get_service_dir, safe_import

router = APIRouter(prefix="/api/pricing", tags=["Dynamic Pricing"])

SERVICE_DIR = get_service_dir("Dynamic-Pricing")
OUTPUT_DIR = os.path.join(SERVICE_DIR, "outputs")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_reg_model = None
_clf_model = None
_transformer = None
_fe_module = None       # feature_engineering
_safety_module = None   # safety_layer
_initialized = False
_error = None
_model_source = "unavailable"


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
def init():
    global _reg_model, _clf_model, _transformer, _fe_module, _safety_module
    global _initialized, _error, _model_source
    try:
        _cwd = os.getcwd()
        os.chdir(SERVICE_DIR)

        _fe_module = safe_import(SERVICE_DIR, "feature_engineering")
        _safety_module = safe_import(SERVICE_DIR, "safety_layer")

        try:
            _reg_model = joblib.load(os.path.join(OUTPUT_DIR, "best_regression_model.joblib"))
            _clf_model = joblib.load(os.path.join(OUTPUT_DIR, "best_classification_model.joblib"))
            _transformer = joblib.load(os.path.join(OUTPUT_DIR, "transformer.joblib"))
            _model_source = "trained_model"
            _error = None
            print("  [pricing] Models loaded")
        except Exception as model_err:
            _reg_model = None
            _clf_model = None
            _transformer = None
            _model_source = "heuristic_fallback"
            _error = str(model_err)
            print(f"  [pricing] WARNING: using heuristic fallback ({model_err})")

        _initialized = True
        os.chdir(_cwd)
    except Exception as e:
        _error = str(e)
        try:
            os.chdir(_cwd)
        except Exception:
            pass
        print(f"  [pricing] FAILED: {e}")


def _heuristic_surge(data: dict) -> tuple[float, int]:
    hour = int(data["hour"])
    weather = str(data["weather"]).lower()
    traffic = float(data["traffic_level"])
    active_orders = float(data["active_orders"])
    available_riders = float(max(1.0, data["available_riders"]))
    hist_demand_trend = float(data["hist_demand_trend"])
    hist_cancel_rate = float(data["hist_cancel_rate"])
    is_holiday = int(data["is_holiday"])

    is_peak = 1 if hour in {12, 13, 14, 19, 20, 21} else 0
    demand_supply = active_orders / available_riders

    surge = 1.0
    surge += max(0.0, demand_supply - 1.0) * 0.35
    surge += max(0.0, hist_demand_trend - 1.0) * 0.40
    surge += min(max(traffic - 2.0, 0.0), 3.0) * 0.06
    surge += min(max(hist_cancel_rate - 0.05, 0.0), 0.20) * 1.2
    if is_peak:
        surge += 0.12
    if is_holiday:
        surge += 0.08
    if "rain" in weather or "storm" in weather:
        surge += 0.10

    return float(np.clip(surge, 0.8, 2.8)), is_peak


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class PricingRequest(BaseModel):
    hour: int
    day_of_week: int
    is_holiday: int
    weather: str
    traffic_level: int
    active_orders: int
    available_riders: int
    avg_prep_time_min: float
    zone_id: int
    distance_km: float
    hist_demand_trend: float
    hist_cancel_rate: float
    base_delivery_fee: Optional[float] = None


class PricingResponse(BaseModel):
    surge_multiplier: float
    final_delivery_fee: float
    recommended_discount: float
    pricing_reason: str
    is_peak_hour: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/calculate", response_model=PricingResponse)
async def calculate_price(req: PricingRequest):
    """Calculate dynamic surge pricing for a delivery."""
    if not _initialized:
        raise HTTPException(503, f"Pricing service unavailable: {_error}")

    try:
        data = req.model_dump()
        # Normalise weather to title-case so the OneHotEncoder always matches
        if "weather" in data and isinstance(data["weather"], str):
            data["weather"] = data["weather"].capitalize()
        BASE_FEE_DEFAULT = getattr(_safety_module, "BASE_FEE_DEFAULT", 45.0)
        base_fee = data.get("base_delivery_fee") or BASE_FEE_DEFAULT

        if data.get("base_delivery_fee") is None:
            zone = float(data.get("zone_id", 7))
            dist = float(data.get("distance_km", 5))
            base_fee = round(25.0 + 1.5 * zone + 2.0 * dist, 2)
            base_fee = max(20, min(90, base_fee))

        required = [
            "hour", "day_of_week", "is_holiday", "weather",
            "traffic_level", "active_orders", "available_riders",
            "avg_prep_time_min", "zone_id", "distance_km",
            "hist_demand_trend", "hist_cancel_rate",
        ]
        row = {k: [data[k]] for k in required}
        df = pd.DataFrame(row)

        df_eng = _fe_module.engineer_features(df)

        if _reg_model is not None and _clf_model is not None and _transformer is not None:
            X = _transformer.transform(df_eng)
            raw_surge = float(_reg_model.predict(X)[0])
            is_peak = int(_clf_model.predict(X)[0])
        else:
            raw_surge, is_peak = _heuristic_surge(data)

        ds_ratio = float(df_eng["demand_supply_ratio"].iloc[0])
        dist_km = float(data["distance_km"])

        decision = _safety_module.apply_safety_rules(
            raw_surge=raw_surge,
            is_peak=is_peak,
            base_fee=base_fee,
            demand_supply_ratio=ds_ratio,
            distance_km=dist_km,
        )

        return PricingResponse(
            surge_multiplier=decision.surge_multiplier,
            final_delivery_fee=decision.final_delivery_fee,
            recommended_discount=decision.recommended_discount,
            pricing_reason=decision.pricing_reason,
            is_peak_hour=decision.is_peak_hour,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))


@router.get("/health")
async def health():
    return {
        "status": "ok" if _initialized else "unavailable",
        "service": "dynamic-pricing",
        "error": _error,
        "model_source": _model_source,
    }
