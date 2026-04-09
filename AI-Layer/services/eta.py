"""
ETA Predictor Service Router
==============================
Wraps the ETA-Predictor project as a FastAPI APIRouter.

Endpoints:
  POST /api/eta/predict
  POST /api/eta/optimise-route
"""
import os
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

from services import get_service_dir, safe_import

router = APIRouter(prefix="/api/eta", tags=["ETA Predictor"])

SERVICE_DIR = get_service_dir("ETA-Predictor")
OUTPUT_DIR = os.path.join(SERVICE_DIR, "outputs")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_model = None
_transformer = None
_best_model_name = None
_target_min = None
_target_max = None
_target_range = None
_rl_policy = None
_osm_graph = None
_fe_module = None        # feature_engineering
_rl_module = None        # rl_optimizer
_osm_module = None       # osm_traffic
_initialized = False
_error = None


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
def init():
    global _model, _transformer, _best_model_name, _target_min, _target_max
    global _target_range, _rl_policy, _osm_graph, _fe_module, _rl_module
    global _osm_module, _initialized, _error

    try:
        _cwd = os.getcwd()
        os.chdir(SERVICE_DIR)

        _model = joblib.load(os.path.join(OUTPUT_DIR, "best_model.joblib"))
        _transformer = joblib.load(os.path.join(OUTPUT_DIR, "transformer.joblib"))

        with open(os.path.join(OUTPUT_DIR, "results.json")) as f:
            results = json.load(f)
            _best_model_name = results["best_model"]

        data_path = os.path.join(SERVICE_DIR, "data", "delivery_dataset.csv")
        train_df = pd.read_csv(data_path)
        _target_min = train_df["delivery_time_min"].min()
        _target_max = train_df["delivery_time_min"].max()
        _target_range = _target_max - _target_min

        _fe_module = safe_import(SERVICE_DIR, "feature_engineering")

        # Optional: RL policy
        try:
            rl_path = os.path.join(OUTPUT_DIR, "rl_policy.pkl")
            if os.path.exists(rl_path):
                with open(rl_path, "rb") as fp:
                    _rl_policy = pickle.load(fp)
            _rl_module = safe_import(SERVICE_DIR, "rl_optimizer")
        except Exception:
            pass

        # Optional: OSM graph
        try:
            _osm_module = safe_import(SERVICE_DIR, "osm_traffic")
            _osm_graph = _osm_module.load_or_download_graph()
        except Exception:
            pass

        _initialized = True
        os.chdir(_cwd)
        print(f"  [eta] Loaded model: {_best_model_name}, "
              f"RL={'yes' if _rl_policy else 'no'}, "
              f"OSM={'yes' if _osm_graph else 'no'}")
    except Exception as e:
        _error = str(e)
        try:
            os.chdir(_cwd)
        except Exception:
            pass
        print(f"  [eta] FAILED: {e}")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class ETARequest(BaseModel):
    restaurant_lat: float
    restaurant_lon: float
    customer_lat: float
    customer_lon: float
    order_hour: int
    day_of_week: int
    weather: str
    traffic_level: str
    prep_time_min: float
    rider_availability: str
    order_size: str
    historical_avg_delivery_min: float


class ETAResponse(BaseModel):
    predicted_time: float
    confidence_score: float
    unit: str = "minutes"
    model_used: str


class DeliveryPoint(BaseModel):
    lat: float
    lon: float


class RouteRequest(BaseModel):
    rider_lat: float
    rider_lon: float
    deliveries: List[DeliveryPoint]


class RouteResponse(BaseModel):
    optimised_order: List[int]
    total_distance_km: float
    baseline_distance_km: float
    savings_pct: float
    method: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/predict", response_model=ETAResponse)
async def predict_delivery_time(req: ETARequest):
    """Predict delivery time for a single order."""
    if not _initialized:
        raise HTTPException(503, f"ETA service unavailable: {_error}")

    row_dict = {
        "restaurant_lat": req.restaurant_lat,
        "restaurant_lon": req.restaurant_lon,
        "customer_lat": req.customer_lat,
        "customer_lon": req.customer_lon,
        "distance_km": 0.0,
        "order_hour": req.order_hour,
        "day_of_week": req.day_of_week,
        "weather": req.weather,
        "traffic_level": req.traffic_level,
        "prep_time_min": req.prep_time_min,
        "rider_availability": req.rider_availability,
        "order_size": req.order_size,
        "historical_avg_delivery_min": req.historical_avg_delivery_min,
    }

    # Enrich with OSM data if available
    if _osm_graph is not None and _osm_module is not None:
        try:
            rd = _osm_module.road_distance_km(
                _osm_graph, req.restaurant_lat, req.restaurant_lon,
                req.customer_lat, req.customer_lon,
            )
            tt = _osm_module.travel_time_min(
                _osm_graph, req.restaurant_lat, req.restaurant_lon,
                req.customer_lat, req.customer_lon,
                hour=req.order_hour, day_of_week=req.day_of_week,
            )
            row_dict["road_distance_km"] = rd
            row_dict["osm_travel_time_min"] = tt
        except Exception:
            pass

    row = pd.DataFrame([row_dict])
    X = _fe_module.transform_new(row, _transformer)
    pred = float(_model.predict(X)[0])
    pred = round(max(10.0, min(90.0, pred)), 1)

    train_mean = (_target_min + _target_max) / 2
    deviation = abs(pred - train_mean) / (_target_range / 2)
    confidence = round(max(0.0, min(1.0, 1.0 - 0.5 * deviation)), 2)

    return ETAResponse(
        predicted_time=pred,
        confidence_score=confidence,
        model_used=_best_model_name,
    )


@router.post("/optimise-route", response_model=RouteResponse)
async def optimise_route(req: RouteRequest):
    """RL-optimised multi-stop delivery route."""
    if not _initialized:
        raise HTTPException(503, f"ETA service unavailable: {_error}")
    if _rl_module is None:
        raise HTTPException(503, "Route optimisation module not available")
    if len(req.deliveries) < 2:
        raise HTTPException(400, "At least 2 deliveries required")

    lats = np.array([req.rider_lat] + [d.lat for d in req.deliveries])
    lons = np.array([req.rider_lon] + [d.lon for d in req.deliveries])

    n = len(lats)
    dist_mat = np.zeros((n, n))
    haversine_fn = _fe_module.haversine_km
    for i in range(n):
        for j in range(n):
            if i != j:
                dist_mat[i, j] = haversine_fn(
                    np.array([lats[i]]), np.array([lons[i]]),
                    np.array([lats[j]]), np.array([lons[j]]),
                )[0]

    method = "nearest-neighbour"
    try:
        if _rl_policy is not None:
            rl_order, rl_dist = _rl_module.optimise_route(_rl_policy, dist_mat)
            method = "Q-learning"
        else:
            raise RuntimeError("No policy")
    except Exception:
        rl_order, rl_dist = _rl_module.nearest_neighbour_route(dist_mat)

    nn_order, nn_dist = _rl_module.nearest_neighbour_route(dist_mat)
    savings = round((1 - rl_dist / max(nn_dist, 1e-9)) * 100, 1) if method == "Q-learning" else 0.0

    return RouteResponse(
        optimised_order=[int(x) for x in rl_order[1:]],
        total_distance_km=round(rl_dist, 2),
        baseline_distance_km=round(nn_dist, 2),
        savings_pct=savings,
        method=method,
    )


@router.get("/health")
async def health():
    return {
        "status": "ok" if _initialized else "unavailable",
        "service": "eta-predictor",
        "model": _best_model_name,
        "osm_available": _osm_graph is not None,
        "rl_available": _rl_policy is not None,
        "error": _error,
    }
