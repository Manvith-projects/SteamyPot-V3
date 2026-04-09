"""
dataset_generator.py
====================
Generates a synthetic dataset (20,000+ rows) that simulates realistic food
delivery platform telemetry for training a Dynamic / Surge Pricing model.

Business context
----------------
Surge pricing adjusts delivery fees in real-time based on:
  * Demand pressure   -- number of active orders in a zone
  * Supply scarcity   -- available riders in a zone
  * External factors  -- weather, traffic, holidays / festivals
  * Temporal patterns -- lunch / dinner rushes, weekends

The generator encodes these dynamics into a deterministic formula with
controlled noise so that ML models can learn meaningful patterns while
the dataset stays reproducible (SEED = 42).

Distance is a critical pricing input: longer deliveries cost more at
baseline AND riders are less willing to accept long trips during peaks,
creating a distance-surge interaction effect.
"""

import os
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED = 42
N_ROWS = 25_000                       # slightly above the 20 000 minimum
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "surge_pricing_dataset.csv")

# Zone IDs -- represent distinct delivery areas in a city
ZONE_IDS = list(range(1, 16))           # 15 zones

# Weather categories
WEATHER_CATS = ["Clear", "Cloudy", "Rain", "Storm", "Fog"]

# Traffic levels (ordinal 1-5 but stored as int for easier modelling)
TRAFFIC_LEVELS = [1, 2, 3, 4, 5]       # 1=free-flow ... 5=gridlock

# ---------------------------------------------------------------------------
# Helper: base surge from demand / supply ratio
# ---------------------------------------------------------------------------

def _base_surge(demand: np.ndarray, supply: np.ndarray) -> np.ndarray:
    """
    Core economic logic:
      surge = clamp( demand / supply , 1.0 , 2.5 )

    When demand >> supply  -> surge approaches cap (2.5x).
    When supply >> demand  -> surge stays at floor (1.0x).
    A small epsilon avoids division-by-zero when supply == 0.
    """
    ratio = demand / (supply + 1e-3)
    # Soft-clip with a sigmoid-like curve so the transition is smooth
    surge = 1.0 + 1.5 * (1.0 / (1.0 + np.exp(-1.8 * (ratio - 1.5))))
    return np.clip(surge, 1.0, 2.5)


# ---------------------------------------------------------------------------
# Helper: time-of-day demand profile
# ---------------------------------------------------------------------------

def _hourly_demand_weight(hour: np.ndarray) -> np.ndarray:
    """
    Mimics real-world meal-time demand peaks:
      * Breakfast rush  ~08:00-09:00
      * Lunch rush      ~12:00-13:00
      * Snack bump      ~16:00-17:00
      * Dinner rush     ~19:00-21:00
    Returns a multiplier in [0.3, 1.0] applied to raw demand.
    """
    w = np.full_like(hour, 0.3, dtype=float)
    w += 0.25 * np.exp(-0.5 * ((hour - 8.5) / 1.0) ** 2)   # breakfast
    w += 0.40 * np.exp(-0.5 * ((hour - 12.5) / 1.2) ** 2)  # lunch
    w += 0.20 * np.exp(-0.5 * ((hour - 16.5) / 1.0) ** 2)  # snack
    w += 0.50 * np.exp(-0.5 * ((hour - 20.0) / 1.5) ** 2)  # dinner
    return np.clip(w, 0.3, 1.0)


# ---------------------------------------------------------------------------
# Main generation routine
# ---------------------------------------------------------------------------

def generate_dataset(n_rows: int = N_ROWS,
                     seed: int = SEED,
                     save: bool = True) -> pd.DataFrame:
    """
    Produce a synthetic surge-pricing dataset.

    Columns generated
    -----------------
    hour               : int   [0-23]
    day_of_week        : int   [0=Mon .. 6=Sun]
    is_holiday         : int   0/1  (~12 % of rows are holidays)
    weather            : str   one of WEATHER_CATS
    traffic_level      : int   1-5
    active_orders      : int   demand proxy, zone-level
    available_riders   : int   supply proxy, zone-level
    avg_prep_time_min  : float average restaurant preparation time
    zone_id            : int   1-15
    distance_km        : float delivery distance in kilometres [1, 25]
    hist_demand_trend  : float rolling z-score of demand (simulated)
    hist_cancel_rate   : float historical cancellation fraction [0,1]
    surge_multiplier   : float target variable (regression)
    base_delivery_fee  : float distance-adjusted per-zone base fee
    final_delivery_fee : float base_fee * surge_multiplier
    is_peak_hour       : int   0/1 label (classification target)

    Returns
    -------
    pd.DataFrame with ``n_rows`` rows.
    """
    rng = np.random.default_rng(seed)

    # -- Temporal features --------------------------------------------------
    hour = rng.integers(0, 24, size=n_rows)
    day_of_week = rng.integers(0, 7, size=n_rows)
    is_holiday = rng.binomial(1, 0.12, size=n_rows)

    # -- External features --------------------------------------------------
    weather = rng.choice(WEATHER_CATS, size=n_rows, p=[0.40, 0.25, 0.20, 0.08, 0.07])
    traffic_level = rng.choice(TRAFFIC_LEVELS, size=n_rows, p=[0.15, 0.25, 0.30, 0.20, 0.10])

    # -- Zone ---------------------------------------------------------------
    zone_id = rng.choice(ZONE_IDS, size=n_rows)

    # -- Demand / Supply (zone-level proxies) -------------------------------
    hourly_weight = _hourly_demand_weight(hour.astype(float))
    # Base demand depends on zone population density (larger zone_id = denser)
    zone_density = 0.5 + zone_id / 15.0          # 0.57 - 1.5
    base_demand = rng.poisson(lam=40 * zone_density * hourly_weight)
    # Holidays and bad weather boost demand
    demand_boost = 1.0 + 0.15 * is_holiday + 0.10 * (weather == "Rain") + 0.20 * (weather == "Storm")
    active_orders = (base_demand * demand_boost).astype(int)
    active_orders = np.clip(active_orders, 1, 200)

    # Supply (riders) -- inversely affected by bad weather & traffic
    supply_base = rng.poisson(lam=25 * zone_density)
    supply_penalty = 1.0 - 0.08 * traffic_level - 0.12 * (weather == "Rain").astype(float) \
                     - 0.25 * (weather == "Storm").astype(float)
    available_riders = (supply_base * np.clip(supply_penalty, 0.3, 1.0)).astype(int)
    available_riders = np.clip(available_riders, 1, 120)

    # -- Delivery distance (km) ---------------------------------------------
    #   Realistic distribution: most deliveries are short (2-8 km) with a
    #   long tail out to 25 km.  Log-normal gives the right skew.
    distance_km = np.round(rng.lognormal(mean=1.6, sigma=0.55, size=n_rows), 1)
    distance_km = np.clip(distance_km, 1.0, 25.0)

    # -- Restaurant prep time -----------------------------------------------
    avg_prep_time_min = rng.normal(loc=18.0, scale=5.0, size=n_rows).clip(5, 45)

    # -- Historical features ------------------------------------------------
    #   hist_demand_trend : positive = demand rising; negative = falling
    hist_demand_trend = rng.normal(0, 1.0, size=n_rows).round(3)
    #   hist_cancel_rate : fraction of orders cancelled [0, 0.35]
    hist_cancel_rate = rng.beta(2, 12, size=n_rows).round(4)

    # -----------------------------------------------------------------------
    # TARGET: surge_multiplier
    # -----------------------------------------------------------------------
    # Core formula  (demand / supply ratio)
    surge = _base_surge(active_orders.astype(float), available_riders.astype(float))
    # Weather uplift
    weather_bump = np.where(weather == "Storm", 0.20,
                  np.where(weather == "Rain", 0.10,
                  np.where(weather == "Fog", 0.05, 0.0)))
    surge += weather_bump
    # Traffic uplift
    surge += 0.04 * (traffic_level - 3)
    # Holiday uplift
    surge += 0.10 * is_holiday
    # Rising-demand trend lifts surge
    surge += 0.05 * np.clip(hist_demand_trend, 0, 3)
    # Distance effect: riders are reluctant to accept long trips during
    # high-demand periods, pushing surge higher for distant orders.
    # Normalised distance contribution: 0 at 1 km, ~0.12 at 25 km.
    surge += 0.005 * (distance_km - 1.0)
    # Add controlled noise
    surge += rng.normal(0, 0.04, size=n_rows)
    # Hard clamp to [1.0, 2.5]
    surge = np.round(np.clip(surge, 1.0, 2.5), 3)

    # -----------------------------------------------------------------------
    # Derived columns
    # -----------------------------------------------------------------------
    # Base delivery fee: zone base  +  per-km charge  +  noise
    #   Business logic: a 1 km delivery should cost ~30-35 INR while a
    #   15 km delivery costs ~55-65 INR.  Formula: zone_base + 2*km.
    base_delivery_fee = np.round(
        25.0 + 1.5 * zone_id + 2.0 * distance_km + rng.normal(0, 1.5, n_rows), 2
    )
    base_delivery_fee = np.clip(base_delivery_fee, 20, 90)
    final_delivery_fee = np.round(base_delivery_fee * surge, 2)

    # Peak-hour label: 1 if surge >= 1.4
    is_peak_hour = (surge >= 1.4).astype(int)

    # -----------------------------------------------------------------------
    # Assemble DataFrame
    # -----------------------------------------------------------------------
    df = pd.DataFrame({
        "hour":              hour,
        "day_of_week":       day_of_week,
        "is_holiday":        is_holiday,
        "weather":           weather,
        "traffic_level":     traffic_level,
        "active_orders":     active_orders,
        "available_riders":  available_riders,
        "avg_prep_time_min": np.round(avg_prep_time_min, 1),
        "zone_id":           zone_id,
        "distance_km":       distance_km,
        "hist_demand_trend": hist_demand_trend,
        "hist_cancel_rate":  hist_cancel_rate,
        "surge_multiplier":  surge,
        "base_delivery_fee": base_delivery_fee,
        "final_delivery_fee": final_delivery_fee,
        "is_peak_hour":      is_peak_hour,
    })

    if save:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"[dataset_generator] Saved {len(df)} rows -> {OUTPUT_FILE}")

    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    df = generate_dataset()
    print(df.describe().round(3))
    print(f"\nPeak-hour distribution:\n{df['is_peak_hour'].value_counts()}")
