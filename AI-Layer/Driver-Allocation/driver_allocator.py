"""
driver_allocator.py — AI Driver Allocation Engine
====================================================
Implements the multi-criteria optimisation logic that selects the
best delivery driver for a new incoming order.

═══════════════════════════════════════════════════════════════════
  OPTIMIZATION ALGORITHM — Weighted Multi-Criteria Scoring
═══════════════════════════════════════════════════════════════════

Overview
--------
When a new order arrives, the system must instantly choose ONE driver
from the available fleet. This is a **multi-criteria decision problem**
because several competing objectives must be balanced:

  1. Proximity  — closer drivers can pick up faster.
  2. Quality    — higher-rated, more reliable drivers give better
                  customer experience.
  3. Workload   — overloaded drivers degrade delivery speed.

We solve this with a **normalised weighted scoring model**:

    score_i = w₁·S_distance + w₂·S_rating + w₃·S_success + w₄·S_workload

where each sub-score S ∈ [0, 1] and the weights sum to 1.

Step-by-step
-------------

1. **Distance score  (weight = 0.40)**
   ─────────────────────────────────────
   Compute Haversine distance (km) from each driver's GPS position
   to the restaurant.

       d_i = haversine(driver_i.location, restaurant_location)

   Normalise via **inverse min-max**:

       S_distance_i = 1 − (d_i − d_min) / (d_max − d_min + ε)

   The closest driver scores 1.0 ; the farthest scores ≈ 0.0.
   ε = 1e-6 prevents division by zero when all drivers are equidistant.

   *Rationale*: distance is the single strongest predictor of pickup
   time, so it receives the highest weight.

2. **Driver rating score  (weight = 0.20)**
   ─────────────────────────────────────────
   Ratings live on [3.0, 5.0].  Normalise linearly:

       S_rating_i = (rating_i − 3.0) / 2.0

   A 5-star driver gets 1.0 ; a 3-star driver gets 0.0.

   *Rationale*: rating is a strong signal of professionalism, care
   with food handling, and customer satisfaction.

3. **Delivery success rate score  (weight = 0.20)**
   ──────────────────────────────────────────────────
   Success rates live on [0.75, 1.0].  Normalise:

       S_success_i = (success_rate_i − 0.75) / 0.25

   A 100 % success driver scores 1.0 ; 75 % scores 0.0.

   *Rationale*: a driver who consistently completes deliveries without
   cancellation or error is critical for platform reliability.

4. **Workload score  (weight = 0.20)**
   ────────────────────────────────────
   `current_active_orders` ∈ {0, 1, 2, 3, 4}.  Normalise inversely:

       S_workload_i = 1 − (active_orders_i / MAX_ACTIVE_ORDERS)

   An idle driver (0 orders) scores 1.0 ; a fully loaded driver (4)
   scores 0.0.

   *Rationale*: an overloaded driver will be delayed finishing
   existing deliveries before picking up the new order.

Final selection
───────────────
   selected_driver = argmax_i ( score_i )

In case of a tie, the driver with the lower predicted ETA wins.

═══════════════════════════════════════════════════════════════════
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

from delivery_predictor import haversine, predict_eta, train_model

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_ACTIVE_ORDERS = 4
WEIGHTS = {
    "distance":     0.40,
    "rating":       0.20,
    "success_rate": 0.20,
    "workload":     0.20,
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DriverInfo:
    driver_id: str
    driver_name: str
    lat: float
    lon: float
    zone: str
    driver_rating: float
    current_active_orders: int
    average_delivery_time: float
    delivery_success_rate: float


@dataclass
class OrderInfo:
    restaurant_lat: float
    restaurant_lon: float
    customer_lat: float
    customer_lon: float
    estimated_prep_time: float   # minutes
    order_size: int              # number of items


@dataclass
class ScoredDriver:
    """An evaluated driver with all sub-scores and final rank."""
    driver: DriverInfo
    distance_km: float           = 0.0
    predicted_eta: float         = 0.0
    distance_score: float        = 0.0
    rating_score: float          = 0.0
    success_score: float         = 0.0
    workload_score: float        = 0.0
    total_score: float           = 0.0
    allocation_reason: str       = ""


# ---------------------------------------------------------------------------
# Core allocation engine
# ---------------------------------------------------------------------------
class DriverAllocator:
    """
    AI-optimised driver allocation engine.

    Lifecycle
    ---------
    1. ``__init__``  — loads the ETA prediction model and driver fleet.
    2. ``allocate``  — accepts an OrderInfo, scores every driver, and
       returns the optimal assignment plus a human-readable explanation.
    """

    def __init__(self, drivers_path: str = "data/drivers.json"):
        # Load / train delivery-time model
        self.eta_model = train_model()

        # Load driver fleet
        if not os.path.exists(drivers_path):
            from data_generator import save_drivers
            save_drivers()
        with open(drivers_path, encoding="utf-8") as f:
            raw = json.load(f)

        self.drivers: list[DriverInfo] = [
            DriverInfo(
                driver_id=d["driver_id"],
                driver_name=d["driver_name"],
                lat=d["location"]["lat"],
                lon=d["location"]["lon"],
                zone=d["zone"],
                driver_rating=d["driver_rating"],
                current_active_orders=d["current_active_orders"],
                average_delivery_time=d["average_delivery_time"],
                delivery_success_rate=d["delivery_success_rate"],
            )
            for d in raw
        ]
        print(f"[allocator] [OK] Loaded {len(self.drivers)} drivers")

    # -----------------------------------------------------------------
    def _score_drivers(self, order: OrderInfo) -> list[ScoredDriver]:
        """Score every driver for the given order."""
        scored: list[ScoredDriver] = []

        # --- Step 1: compute raw distances --------------------------
        for drv in self.drivers:
            dist = haversine(drv.lat, drv.lon,
                             order.restaurant_lat, order.restaurant_lon)
            eta = predict_eta(
                self.eta_model,
                distance_km=dist,
                active_orders=drv.current_active_orders,
                avg_delivery_time=drv.average_delivery_time,
                prep_time=order.estimated_prep_time,
                order_size=order.order_size,
                driver_rating=drv.driver_rating,
                success_rate=drv.delivery_success_rate,
            )
            scored.append(ScoredDriver(driver=drv, distance_km=round(dist, 2),
                                       predicted_eta=eta))

        if not scored:
            return scored

        # --- Step 2: normalise distance (inverse) ------------------
        dists = [s.distance_km for s in scored]
        d_min, d_max = min(dists), max(dists)
        d_range = d_max - d_min + 1e-6

        for s in scored:
            s.distance_score = round(1.0 - (s.distance_km - d_min) / d_range, 4)

        # --- Step 3: normalise rating [3, 5] → [0, 1] -------------
        for s in scored:
            s.rating_score = round(
                (s.driver.driver_rating - 3.0) / 2.0, 4
            )

        # --- Step 4: normalise success rate [0.75, 1.0] → [0, 1] --
        for s in scored:
            s.success_score = round(
                (s.driver.delivery_success_rate - 0.75) / 0.25, 4
            )

        # --- Step 5: normalise workload (inverse) ------------------
        for s in scored:
            s.workload_score = round(
                1.0 - (s.driver.current_active_orders / MAX_ACTIVE_ORDERS), 4
            )

        # --- Step 6: weighted composite ----------------------------
        for s in scored:
            s.total_score = round(
                WEIGHTS["distance"]     * s.distance_score
                + WEIGHTS["rating"]     * s.rating_score
                + WEIGHTS["success_rate"] * s.success_score
                + WEIGHTS["workload"]   * s.workload_score,
                4,
            )

        # --- Sort: highest score first; tie-break by lower ETA -----
        scored.sort(key=lambda s: (-s.total_score, s.predicted_eta))
        return scored

    # -----------------------------------------------------------------
    @staticmethod
    def _build_reason(best: ScoredDriver, order: OrderInfo) -> str:
        """Construct a human-readable allocation explanation."""
        drv = best.driver
        parts = [
            f"Driver {drv.driver_name} ({drv.driver_id}) was selected "
            f"with an optimization score of {best.total_score:.4f}.",
            "",
            "Breakdown:",
            f"  • Distance to restaurant : {best.distance_km:.2f} km  "
            f"→ distance_score = {best.distance_score:.4f}  (weight 0.40)",
            f"  • Driver rating          : {drv.driver_rating}/5.0    "
            f"→ rating_score   = {best.rating_score:.4f}  (weight 0.20)",
            f"  • Delivery success rate   : {drv.delivery_success_rate:.2%}  "
            f"→ success_score  = {best.success_score:.4f}  (weight 0.20)",
            f"  • Active orders          : {drv.current_active_orders}/{MAX_ACTIVE_ORDERS}     "
            f"→ workload_score = {best.workload_score:.4f}  (weight 0.20)",
            "",
            f"  TOTAL = 0.40×{best.distance_score:.4f} + 0.20×{best.rating_score:.4f} "
            f"+ 0.20×{best.success_score:.4f} + 0.20×{best.workload_score:.4f} "
            f"= {best.total_score:.4f}",
            "",
            f"Predicted delivery ETA: {best.predicted_eta:.1f} minutes "
            f"(ML model, factors: distance, prep time, driver load & history).",
        ]
        return "\n".join(parts)

    # -----------------------------------------------------------------
    def allocate(self, order: OrderInfo) -> dict:
        """
        Main entry point.

        Parameters
        ----------
        order : OrderInfo
            Incoming order details.

        Returns
        -------
        dict with keys:
            selected_driver          — driver id
            driver_name              — human-readable name
            estimated_delivery_time  — predicted ETA in minutes
            optimization_score       — composite score
            allocation_reason        — detailed explanation
            runner_up                — second-best driver (for transparency)
            all_scores               — full ranked list (top 5)
        """
        scored = self._score_drivers(order)
        if not scored:
            return {"error": "No drivers available"}

        best = scored[0]
        reason = self._build_reason(best, order)

        result = {
            "selected_driver": best.driver.driver_id,
            "driver_name": best.driver.driver_name,
            "driver_zone": best.driver.zone,
            "estimated_delivery_time": f"{best.predicted_eta:.1f} minutes",
            "optimization_score": best.total_score,
            "allocation_reason": reason,
        }

        # Runner-up for transparency
        if len(scored) > 1:
            ru = scored[1]
            result["runner_up"] = {
                "driver_id": ru.driver.driver_id,
                "driver_name": ru.driver.driver_name,
                "score": ru.total_score,
                "predicted_eta": f"{ru.predicted_eta:.1f} minutes",
            }

        # Top-5 leaderboard
        result["top_5_drivers"] = [
            {
                "rank": i + 1,
                "driver_id": s.driver.driver_id,
                "driver_name": s.driver.driver_name,
                "score": s.total_score,
                "distance_km": s.distance_km,
                "predicted_eta": s.predicted_eta,
            }
            for i, s in enumerate(scored[:5])
        ]

        return result


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    allocator = DriverAllocator()
    test_order = OrderInfo(
        restaurant_lat=17.4486,
        restaurant_lon=78.3908,
        customer_lat=17.4375,
        customer_lon=78.4483,
        estimated_prep_time=15.0,
        order_size=3,
    )
    result = allocator.allocate(test_order)
    print(json.dumps(result, indent=2))
