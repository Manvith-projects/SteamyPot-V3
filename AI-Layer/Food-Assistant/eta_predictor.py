"""
eta_predictor.py  --  Delivery Time Estimation
================================================
Estimates delivery time for each recommended restaurant based on
distance, restaurant prep time, and current conditions.

AI Concept: ETA Prediction Model
----------------------------------
In a production system, this would call the trained ETA-Predictor
ML model (see ../ETA-Predictor/). Here we use a simplified formula
that captures the main factors:

  ETA = prep_time + travel_time + buffer

Where:
  * prep_time    = restaurant's average kitchen preparation time (min)
  * travel_time  = distance_km / avg_speed_kmph * 60
  * buffer       = random traffic / weather buffer (2-5 min)

The key insight from delivery-time research:
  * Distance is the #1 predictor (explains ~40% of ETA variance).
  * Prep time is #2 (explains ~25%).
  * Time-of-day, weather, order complexity are the rest.

We simulate time-of-day effects:
  * Peak hours (12-2 PM, 7-10 PM) → slower prep + more traffic.
  * Off-peak → faster delivery.
"""

import random
from datetime import datetime

SEED = 42
_rng = random.Random(SEED)

# Average delivery partner speed (km/h)
# Accounts for mixed city traffic in Hyderabad
AVG_SPEED_KMPH = 22.0

# Peak hour config
PEAK_LUNCH = (12, 14)   # 12 PM - 2 PM
PEAK_DINNER = (19, 22)  # 7 PM - 10 PM


def estimate_eta(
    distance_km: float,
    avg_prep_time_min: int,
    current_hour: int = None,
) -> dict:
    """
    Estimate delivery time in minutes.

    AI Concept: Feature-Based Prediction
    -------------------------------------
    This is a deterministic model (no ML training), but it follows
    the same pattern as an ML model:
      1. Input features: distance, prep_time, hour
      2. Feature transformation: speed adjustment based on hour
      3. Output: predicted ETA in minutes

    In production, this would be replaced by the trained MLP/Gradient
    Boosting model from ETA-Predictor which achieves RMSE ≈ 3.5 min.

    Parameters
    ----------
    distance_km       : Distance from restaurant to user.
    avg_prep_time_min : Restaurant's average food preparation time.
    current_hour      : Hour of day (0-23). Auto-detected if None.

    Returns
    -------
    dict : {eta_minutes, breakdown: {prep, travel, buffer}}
    """
    if current_hour is None:
        current_hour = datetime.now().hour

    # -----------------------------------------------------------------------
    # Speed adjustment based on time of day
    # -----------------------------------------------------------------------
    # AI Concept: Contextual Feature Engineering
    # Time-of-day is a "contextual feature" -- it doesn't change with the
    # user/restaurant but affects the prediction for all pairs.
    # Peak hours → slower speed (more traffic + longer prep queues).
    speed = AVG_SPEED_KMPH
    prep_multiplier = 1.0

    if PEAK_LUNCH[0] <= current_hour < PEAK_LUNCH[1]:
        speed *= 0.75      # 25% slower in lunch traffic
        prep_multiplier = 1.3  # 30% longer prep (kitchen backlog)
    elif PEAK_DINNER[0] <= current_hour < PEAK_DINNER[1]:
        speed *= 0.70      # 30% slower in dinner traffic
        prep_multiplier = 1.4  # 40% longer prep
    elif 23 <= current_hour or current_hour < 6:
        speed *= 1.1       # Late night = less traffic
        prep_multiplier = 0.9

    # -----------------------------------------------------------------------
    # ETA calculation
    # -----------------------------------------------------------------------
    prep_time = round(avg_prep_time_min * prep_multiplier)

    # Travel time = distance / speed * 60 (convert hours to minutes)
    travel_time = round((distance_km / speed) * 60) if distance_km else 5

    # Buffer for order assignment + pickup logistics
    buffer = _rng.randint(2, 5)

    eta_minutes = prep_time + travel_time + buffer

    return {
        "eta_minutes": eta_minutes,
        "breakdown": {
            "prep_time_min": prep_time,
            "travel_time_min": travel_time,
            "buffer_min": buffer,
        },
        "is_peak_hour": (
            PEAK_LUNCH[0] <= current_hour < PEAK_LUNCH[1] or
            PEAK_DINNER[0] <= current_hour < PEAK_DINNER[1]
        ),
    }
