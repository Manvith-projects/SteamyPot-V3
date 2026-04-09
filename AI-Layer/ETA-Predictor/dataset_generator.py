"""
=============================================================================
Synthetic Dataset Generator for Delivery Time Prediction
=============================================================================

Generates realistic food-delivery data with 10,000+ samples.

Feature Rationale:
-------------------
- restaurant_lat/lon, customer_lat/lon, distance_km
    Geographic features directly determine travel time.  Longer distance →
    longer delivery.  We also store raw coordinates so haversine can be
    recomputed or compared against straight-line distance.

- order_hour, day_of_week
    Temporal features capture rush-hour peaks (lunch 11-14, dinner 18-21)
    and weekend effects (higher volume, different traffic patterns).

- weather  (Clear / Cloudy / Rainy / Stormy)
    Adverse weather slows riders and increases road hazards.

- traffic_level  (Low / Medium / High)
    Real-time congestion is the single strongest modifier of travel time
    after distance.

- prep_time_min
    Kitchen preparation time is order-dependent (fast food ≈ 5 min,
    gourmet ≈ 25 min) and adds directly to total delivery duration.

- rider_availability  (Low / Medium / High)
    When few riders are available the platform must dispatch from farther
    away, increasing pick-up time.

- order_size  (Small / Medium / Large)
    Larger orders may take longer to prepare and to hand-off.

- historical_avg_delivery_min
    Restaurant-specific historical average acts as a strong prior/baseline
    estimate.

Target:
-------
- delivery_time_min  –  the actual delivery duration in minutes.
"""

import numpy as np
import pandas as pd
from pathlib import Path

# ─── Reproducibility ─────────────────────────────────────────────────────────
SEED = 42
RNG  = np.random.default_rng(SEED)

# ─── Constants ────────────────────────────────────────────────────────────────
NUM_SAMPLES = 10_000

# Hyderabad-area bounding box (approx.)
LAT_MIN, LAT_MAX = 17.30, 17.50
LON_MIN, LON_MAX = 78.35, 78.55

WEATHER_OPTIONS       = ["Clear", "Cloudy", "Rainy", "Stormy"]
WEATHER_PROBS         = [0.40, 0.30, 0.20, 0.10]

TRAFFIC_OPTIONS       = ["Low", "Medium", "High"]
TRAFFIC_PROBS         = [0.30, 0.45, 0.25]

RIDER_AVAIL_OPTIONS   = ["Low", "Medium", "High"]
RIDER_AVAIL_PROBS     = [0.20, 0.50, 0.30]

ORDER_SIZE_OPTIONS    = ["Small", "Medium", "Large"]
ORDER_SIZE_PROBS      = [0.35, 0.45, 0.20]


# ─── Haversine (vectorised) ──────────────────────────────────────────────────
def haversine_km(lat1, lon1, lat2, lon2):
    """
    Compute great-circle distance in km between two sets of coordinates.
    Uses the Haversine formula — accurate for short to medium distances.
    """
    R = 6371.0  # Earth radius in km
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


# ─── Delivery-time formula (realistic noise model) ───────────────────────────
def compute_delivery_time(
    distance_km, hour, day, weather, traffic, prep_time, rider, order_size, hist_avg
):
    """
    Simulate realistic delivery time as a function of all input features.

    Base model:
        delivery = prep_time
                 + (distance / speed) * 60          # travel time
                 + weather_penalty + traffic_penalty
                 + rider_penalty + size_penalty
                 + historical_bias + noise

    The multipliers and penalties are calibrated so the final delivery
    times mostly fall in the 15-75 min range, which mirrors real-world
    food-delivery distributions.
    """
    n = len(distance_km)
    base = np.copy(prep_time).astype(float)

    # --- Travel time (distance / speed → minutes) ---
    #     Average city speed ~20 km/h → 3 min/km; varies by traffic.
    speed_kmph = np.full(n, 20.0)
    speed_kmph[traffic == "Low"]    = 28.0
    speed_kmph[traffic == "Medium"] = 20.0
    speed_kmph[traffic == "High"]   = 13.0
    base += (distance_km / speed_kmph) * 60.0

    # --- Weather penalty (minutes) ---
    wp = np.zeros(n)
    wp[weather == "Cloudy"]  = RNG.uniform(0, 2, size=(weather == "Cloudy").sum())
    wp[weather == "Rainy"]   = RNG.uniform(3, 8, size=(weather == "Rainy").sum())
    wp[weather == "Stormy"]  = RNG.uniform(8, 18, size=(weather == "Stormy").sum())
    base += wp

    # --- Rush-hour penalty ---
    is_rush = ((hour >= 11) & (hour <= 14)) | ((hour >= 18) & (hour <= 21))
    base[is_rush] += RNG.uniform(3, 8, size=is_rush.sum())

    # --- Weekend slight increase (more orders, longer queues) ---
    is_weekend = (day >= 5)
    base[is_weekend] += RNG.uniform(1, 4, size=is_weekend.sum())

    # --- Rider availability penalty ---
    rp = np.zeros(n)
    rp[rider == "Low"]    = RNG.uniform(4, 10, size=(rider == "Low").sum())
    rp[rider == "Medium"] = RNG.uniform(1, 3, size=(rider == "Medium").sum())
    base += rp

    # --- Order size penalty ---
    sp = np.zeros(n)
    sp[order_size == "Medium"] = RNG.uniform(1, 3, size=(order_size == "Medium").sum())
    sp[order_size == "Large"]  = RNG.uniform(3, 7, size=(order_size == "Large").sum())
    base += sp

    # --- Historical-average bias (anchor towards restaurant norm) ---
    base += 0.15 * (hist_avg - base)

    # --- Gaussian noise (± ~3 min) ---
    base += RNG.normal(0, 3.0, size=n)

    return np.clip(base, 10, 90).round(1)       # clamp to realistic range


# ─── Main generator ──────────────────────────────────────────────────────────
def generate_dataset(num_samples: int = NUM_SAMPLES, save: bool = True) -> pd.DataFrame:
    """Generate and optionally save the synthetic delivery-time dataset."""

    # Coordinates
    rest_lat = RNG.uniform(LAT_MIN, LAT_MAX, num_samples)
    rest_lon = RNG.uniform(LON_MIN, LON_MAX, num_samples)
    cust_lat = rest_lat + RNG.uniform(-0.06, 0.06, num_samples)
    cust_lon = rest_lon + RNG.uniform(-0.06, 0.06, num_samples)

    distance = haversine_km(rest_lat, rest_lon, cust_lat, cust_lon)

    # Temporal
    hour = RNG.integers(0, 24, num_samples)
    day  = RNG.integers(0, 7, num_samples)       # 0=Mon … 6=Sun

    # Categorical features
    weather    = RNG.choice(WEATHER_OPTIONS,     num_samples, p=WEATHER_PROBS)
    traffic    = RNG.choice(TRAFFIC_OPTIONS,      num_samples, p=TRAFFIC_PROBS)
    rider      = RNG.choice(RIDER_AVAIL_OPTIONS,  num_samples, p=RIDER_AVAIL_PROBS)
    order_size = RNG.choice(ORDER_SIZE_OPTIONS,    num_samples, p=ORDER_SIZE_PROBS)

    # Prep time: depends on order size (fast-food bias for small, gourmet for large)
    prep_time = np.where(
        order_size == "Small",
        RNG.uniform(5, 12, num_samples),
        np.where(order_size == "Medium",
                 RNG.uniform(10, 20, num_samples),
                 RNG.uniform(18, 30, num_samples)),
    ).round(1)

    # Historical average per restaurant (simulate restaurant-level mean)
    hist_avg = RNG.uniform(25, 55, num_samples).round(1)

    # Ground-truth delivery time
    delivery_time = compute_delivery_time(
        distance, hour, day, weather, traffic, prep_time, rider, order_size, hist_avg
    )

    df = pd.DataFrame({
        "restaurant_lat":              rest_lat.round(6),
        "restaurant_lon":              rest_lon.round(6),
        "customer_lat":                cust_lat.round(6),
        "customer_lon":                cust_lon.round(6),
        "distance_km":                 distance.round(3),
        "order_hour":                  hour,
        "day_of_week":                 day,
        "weather":                     weather,
        "traffic_level":               traffic,
        "prep_time_min":               prep_time,
        "rider_availability":          rider,
        "order_size":                  order_size,
        "historical_avg_delivery_min": hist_avg,
        "delivery_time_min":           delivery_time,
    })

    if save:
        out = Path(__file__).parent / "data" / "delivery_dataset.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        print(f"[dataset_generator] Saved {len(df):,} rows → {out}")

    return df


# ─── CLI entry point ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    df = generate_dataset()
    print(df.describe().round(2))
