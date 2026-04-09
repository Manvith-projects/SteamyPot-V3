"""
app.py — Flask Server for AI Driver Allocation
=================================================
Exposes the AI driver allocation engine as a REST API.

Endpoints
---------
  POST /allocate-driver   — Allocate the optimal driver for an order
  GET  /drivers           — List all drivers and their current status
  GET  /health            — Health check

Architecture
------------
  ┌─────────────┐     ┌──────────────┐     ┌────────────────────┐
  │ Client       │────▶│  Flask API   │────▶│  DriverAllocator   │
  │ POST order   │     │  /allocate   │     │  (scoring engine)  │
  └─────────────┘     └──────────────┘     └────────┬───────────┘
                                                     │
                           ┌─────────────────────────┼──────────────┐
                           ▼                         ▼              ▼
                   ┌──────────────┐         ┌──────────────┐ ┌───────────┐
                   │ Haversine    │         │ GBT ETA      │ │ Driver    │
                   │ Distance     │         │ Predictor    │ │ Fleet DB  │
                   └──────────────┘         └──────────────┘ └───────────┘

AI Concept: ML-Powered Microservice Pattern
---------------------------------------------
The allocation decision is made by composing three AI/ML components:
  1. **Haversine geo-distance** — spatial proximity feature.
  2. **Gradient-Boosted ETA model** — predicts delivery time from
     7 engineered features (distance, load, prep time, driver stats).
  3. **Weighted multi-criteria scorer** — balances distance, quality,
     reliability, and workload into a single optimisation score.

Each component can be independently tested, re-trained, and versioned.

CORS
-----
Enabled for React dev server at localhost:5173 and any localhost port.
"""

import time
from flask import Flask, request, jsonify
from flask_cors import CORS

from data_generator import save_drivers
from driver_allocator import DriverAllocator, OrderInfo

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ---------------------------------------------------------------------------
# Startup — initialise allocator (loads drivers + trains/loads ETA model)
# ---------------------------------------------------------------------------
print("=" * 60)
print("  AI Driver Allocation Agent — Starting up …")
print("=" * 60)

# Ensure driver data exists
save_drivers()

# Initialise the allocation engine
allocator = DriverAllocator()

print("=" * 60)
    print("  [OK] Ready to accept requests")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "ai-driver-allocation",
        "drivers_loaded": len(allocator.drivers),
    })


@app.route("/drivers", methods=["GET"])
def list_drivers():
    """Return the full driver fleet with current status."""
    fleet = []
    for d in allocator.drivers:
        fleet.append({
            "driver_id": d.driver_id,
            "driver_name": d.driver_name,
            "location": {"lat": d.lat, "lon": d.lon},
            "zone": d.zone,
            "driver_rating": d.driver_rating,
            "current_active_orders": d.current_active_orders,
            "average_delivery_time": d.average_delivery_time,
            "delivery_success_rate": d.delivery_success_rate,
        })
    return jsonify({"drivers": fleet, "count": len(fleet)})


@app.route("/allocate-driver", methods=["POST"])
def allocate_driver():
    """
    POST /allocate-driver
    ─────────────────────

    Allocate the optimal delivery driver for a new order.

    Request JSON
    ~~~~~~~~~~~~~
    {
        "restaurant_location": {"lat": 17.4486, "lon": 78.3908},
        "customer_location":   {"lat": 17.4375, "lon": 78.4483},
        "estimated_prep_time": 15,
        "order_size": 3
    }

    Response JSON
    ~~~~~~~~~~~~~~
    {
        "selected_driver": "DRV-007",
        "driver_name": "Harsha",
        "driver_zone": "Madhapur",
        "estimated_delivery_time": "22.4 minutes",
        "optimization_score": 0.8734,
        "allocation_reason": "... detailed breakdown ...",
        "runner_up": { ... },
        "top_5_drivers": [ ... ],
        "processing_time_ms": 12.3
    }

    Optimization Logic (detailed)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    The allocation uses a **Weighted Multi-Criteria Scoring** model:

        score = 0.4 × distance_score
              + 0.2 × driver_rating_score
              + 0.2 × success_rate_score
              + 0.2 × workload_score

    Where each sub-score is normalised to [0, 1]:

    1. **distance_score** — Haversine distance from driver to restaurant,
       inverse min-max normalised across the fleet. Closest driver → 1.0.

    2. **driver_rating_score** — Linear map of rating from [3.0, 5.0] to
       [0, 1]. A 5-star driver scores 1.0.

    3. **success_rate_score** — Linear map of delivery success rate from
       [0.75, 1.0] to [0, 1]. A 100% success rate scores 1.0.

    4. **workload_score** — Inverse proportion of active orders out of
       max (4). An idle driver (0 active orders) scores 1.0.

    The driver with the **highest composite score** is selected.
    Ties are broken by the lower **predicted ETA** (from the
    Gradient-Boosted regression model trained on 7 features).
    """
    data = request.get_json(force=True)
    start = time.time()

    # ── Validate input ──────────────────────────────────────────────
    errors = []
    if "restaurant_location" not in data:
        errors.append("Missing 'restaurant_location' (object with lat, lon)")
    else:
        rl = data["restaurant_location"]
        if "lat" not in rl or "lon" not in rl:
            errors.append("'restaurant_location' must have 'lat' and 'lon'")

    if "customer_location" not in data:
        errors.append("Missing 'customer_location' (object with lat, lon)")
    else:
        cl = data["customer_location"]
        if "lat" not in cl or "lon" not in cl:
            errors.append("'customer_location' must have 'lat' and 'lon'")

    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    # ── Build OrderInfo ─────────────────────────────────────────────
    rl = data["restaurant_location"]
    cl = data["customer_location"]
    order = OrderInfo(
        restaurant_lat=float(rl["lat"]),
        restaurant_lon=float(rl["lon"]),
        customer_lat=float(cl["lat"]),
        customer_lon=float(cl["lon"]),
        estimated_prep_time=float(data.get("estimated_prep_time", 15)),
        order_size=int(data.get("order_size", 2)),
    )

    # ── Allocate ────────────────────────────────────────────────────
    result = allocator.allocate(order)
    elapsed = (time.time() - start) * 1000
    result["processing_time_ms"] = round(elapsed, 2)

    return jsonify(result)


# ---------------------------------------------------------------------------
# Optimization explainer (standalone GET)
# ---------------------------------------------------------------------------
@app.route("/optimization-logic", methods=["GET"])
def optimization_logic():
    """Return a detailed explanation of the scoring algorithm."""
    return jsonify({
        "algorithm": "Weighted Multi-Criteria Scoring",
        "formula": "score = 0.4×distance_score + 0.2×rating_score + 0.2×success_rate_score + 0.2×workload_score",
        "weights": {
            "distance_score":     {"weight": 0.40, "description": "Inverse-normalised Haversine distance from driver to restaurant. Closest driver → 1.0."},
            "driver_rating_score": {"weight": 0.20, "description": "Linear normalisation of driver rating [3.0–5.0] → [0–1]. Higher rated → higher score."},
            "success_rate_score":  {"weight": 0.20, "description": "Linear normalisation of delivery success rate [0.75–1.0] → [0–1]. More reliable → higher score."},
            "workload_score":      {"weight": 0.20, "description": "Inverse proportion of active orders / max(4). Fewer active orders → higher score."},
        },
        "tie_breaker": "Lower predicted ETA (from Gradient-Boosted regression model)",
        "eta_model": {
            "type": "GradientBoostingRegressor (scikit-learn)",
            "features": [
                "distance_km",
                "current_active_orders",
                "average_delivery_time",
                "estimated_prep_time",
                "order_size",
                "driver_rating",
                "delivery_success_rate",
            ],
            "training_samples": 5000,
            "description": "Predicts delivery time in minutes using physics-informed synthetic training data with realistic noise.",
        },
        "selection_rule": "Driver with highest composite score is selected. Full ranking is returned for transparency.",
    })


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
