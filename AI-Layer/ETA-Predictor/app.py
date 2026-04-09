"""
=============================================================================
Flask API – Delivery Time Prediction & Route Optimisation Service
=============================================================================

Endpoints:

    POST /predict-delivery-time   – predict ETA for a single delivery
    POST /optimise-route           – RL-optimised multi-stop delivery route
    GET  /health                   – health-check

Input JSON  (predict-delivery-time)
-----------------------------------
{
    "restaurant_lat": 17.385,
    "restaurant_lon": 78.486,
    "customer_lat":   17.420,
    "customer_lon":   78.510,
    "order_hour":     19,
    "day_of_week":    5,
    "weather":        "Rainy",
    "traffic_level":  "High",
    "prep_time_min":  15.0,
    "rider_availability": "Medium",
    "order_size":     "Large",
    "historical_avg_delivery_min": 40.0
}

Output JSON  (predict-delivery-time)
------------------------------------
{
    "predicted_time": 52.3,
    "confidence_score": 0.87,
    "unit": "minutes",
    "model_used": "XGBoost"
}

Input JSON  (optimise-route)
----------------------------
{
    "rider_lat": 17.385,
    "rider_lon": 78.486,
    "deliveries": [
        {"lat": 17.40, "lon": 78.50},
        {"lat": 17.42, "lon": 78.48},
        {"lat": 17.39, "lon": 78.51}
    ]
}

Output JSON  (optimise-route)
-----------------------------
{
    "optimised_order": [2, 0, 1],
    "total_distance_km": 8.3,
    "baseline_distance_km": 11.7,
    "savings_pct": 29.1,
    "method": "Q-learning"
}
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify

from feature_engineering import transform_new

# ─── Load artefacts ──────────────────────────────────────────────────────────
OUT = Path(__file__).parent / "outputs"

model       = joblib.load(OUT / "best_model.joblib")
transformer = joblib.load(OUT / "transformer.joblib")

with open(OUT / "results.json") as f:
    results = json.load(f)
    BEST_MODEL_NAME = results["best_model"]

# Derive training-set target range for confidence heuristic
DATA = Path(__file__).parent / "data" / "delivery_dataset.csv"
_train_df     = pd.read_csv(DATA)
_TARGET_MIN   = _train_df["delivery_time_min"].min()
_TARGET_MAX   = _train_df["delivery_time_min"].max()
_TARGET_RANGE = _TARGET_MAX - _TARGET_MIN

print(f"[API] Loaded model: {BEST_MODEL_NAME}")
print(f"[API] Target range: {_TARGET_MIN:.1f} – {_TARGET_MAX:.1f} min")

# ─── Try loading RL policy ───────────────────────────────────────────────────
RL_POLICY = None
try:
    _rl_path = OUT / "rl_policy.pkl"
    if _rl_path.exists():
        import pickle
        with open(_rl_path, "rb") as fp:
            RL_POLICY = pickle.load(fp)
        print("[API] RL policy loaded ✓")
except Exception as exc:
    print(f"[API] RL policy not available: {exc}")

# ─── Try loading OSM graph for enrichment ────────────────────────────────────
_OSM_GRAPH = None
try:
    from osm_traffic import load_or_download_graph, road_distance_km, travel_time_min
    _OSM_GRAPH = load_or_download_graph()
    print("[API] OSM road graph loaded ✓")
except Exception as exc:
    print(f"[API] OSM graph not available (using haversine): {exc}")

# ─── Flask app ───────────────────────────────────────────────────────────────
app = Flask(__name__)

# Required input fields
REQUIRED_FIELDS = [
    "restaurant_lat", "restaurant_lon",
    "customer_lat",   "customer_lon",
    "order_hour",     "day_of_week",
    "weather",        "traffic_level",
    "prep_time_min",  "rider_availability",
    "order_size",     "historical_avg_delivery_min",
]


@app.route("/predict-delivery-time", methods=["POST"])
def predict():
    """
    Accept order details as JSON, return predicted delivery time
    and a confidence score.
    """
    data = request.get_json(force=True)

    # --- Validate input ──────────────────────────────────────────────────
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    # --- Build a one-row DataFrame (same schema as training data) ────────
    row_dict = {
        "restaurant_lat":              float(data["restaurant_lat"]),
        "restaurant_lon":              float(data["restaurant_lon"]),
        "customer_lat":                float(data["customer_lat"]),
        "customer_lon":                float(data["customer_lon"]),
        "distance_km":                 0.0,  # recomputed inside transform_new
        "order_hour":                  int(data["order_hour"]),
        "day_of_week":                 int(data["day_of_week"]),
        "weather":                     str(data["weather"]),
        "traffic_level":               str(data["traffic_level"]),
        "prep_time_min":               float(data["prep_time_min"]),
        "rider_availability":          str(data["rider_availability"]),
        "order_size":                  str(data["order_size"]),
        "historical_avg_delivery_min": float(data["historical_avg_delivery_min"]),
    }

    # If OSM graph available, enrich with road distance / travel time
    if _OSM_GRAPH is not None:
        try:
            rd = road_distance_km(
                _OSM_GRAPH,
                row_dict["restaurant_lat"], row_dict["restaurant_lon"],
                row_dict["customer_lat"],   row_dict["customer_lon"],
            )
            tt = travel_time_min(
                _OSM_GRAPH,
                row_dict["restaurant_lat"], row_dict["restaurant_lon"],
                row_dict["customer_lat"],   row_dict["customer_lon"],
                hour=row_dict["order_hour"],
                day_of_week=row_dict["day_of_week"],
            )
            row_dict["road_distance_km"]    = rd
            row_dict["osm_travel_time_min"] = tt
        except Exception:
            pass  # graceful degradation

    row = pd.DataFrame([row_dict])

    # --- Transform & predict ─────────────────────────────────────────────
    X = transform_new(row, transformer)
    pred = float(model.predict(X)[0])
    pred = round(max(10.0, min(90.0, pred)), 1)  # clamp to realistic range

    # --- Confidence heuristic ────────────────────────────────────────────
    train_mean = (_TARGET_MIN + _TARGET_MAX) / 2
    deviation  = abs(pred - train_mean) / (_TARGET_RANGE / 2)
    confidence = round(max(0.0, min(1.0, 1.0 - 0.5 * deviation)), 2)

    return jsonify({
        "predicted_time":   pred,
        "confidence_score": confidence,
        "unit":             "minutes",
        "model_used":       BEST_MODEL_NAME,
    })


@app.route("/optimise-route", methods=["POST"])
def optimise_route():
    """
    Accept rider location & delivery destinations, return RL-optimised
    delivery order with distance savings over nearest-neighbour baseline.
    """
    data = request.get_json(force=True)

    rider_lat = float(data.get("rider_lat", 0))
    rider_lon = float(data.get("rider_lon", 0))
    deliveries = data.get("deliveries", [])

    if len(deliveries) < 2:
        return jsonify({"error": "At least 2 deliveries required"}), 400

    lats = np.array([rider_lat] + [d["lat"] for d in deliveries])
    lons = np.array([rider_lon] + [d["lon"] for d in deliveries])

    # Build pairwise distance matrix (haversine)
    n = len(lats)
    dist_mat = np.zeros((n, n))
    from feature_engineering import haversine_km
    for i in range(n):
        for j in range(n):
            if i != j:
                dist_mat[i, j] = haversine_km(
                    np.array([lats[i]]), np.array([lons[i]]),
                    np.array([lats[j]]), np.array([lons[j]]),
                )[0]

    # Try RL optimisation
    method = "nearest-neighbour"
    try:
        if RL_POLICY is not None:
            from rl_optimizer import optimise_route as rl_opt
            rl_order, rl_dist = rl_opt(RL_POLICY, dist_mat)
            method = "Q-learning"
        else:
            raise RuntimeError("No policy")
    except Exception:
        # Fallback: nearest-neighbour
        from rl_optimizer import nearest_neighbour_route
        rl_order, rl_dist = nearest_neighbour_route(dist_mat)

    # Baseline: nearest-neighbour for comparison
    from rl_optimizer import nearest_neighbour_route
    nn_order, nn_dist = nearest_neighbour_route(dist_mat)

    savings = round((1 - rl_dist / max(nn_dist, 1e-9)) * 100, 1) if method == "Q-learning" else 0.0

    return jsonify({
        "optimised_order":      [int(x) for x in rl_order[1:]],
        "total_distance_km":    round(rl_dist, 2),
        "baseline_distance_km": round(nn_dist, 2),
        "savings_pct":          savings,
        "method":               method,
    })


@app.route("/health", methods=["GET"])
def health():
    """Simple health-check endpoint."""
    return jsonify({
        "status": "ok",
        "model": BEST_MODEL_NAME,
        "osm_available": _OSM_GRAPH is not None,
        "rl_available":  RL_POLICY is not None,
    })


# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
