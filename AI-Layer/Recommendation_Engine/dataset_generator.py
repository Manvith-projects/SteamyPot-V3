# dataset_generator.py
"""
Vectorised dataset generator for Trust-Aware Social Recommendation.

Scales to 300K+ users and millions of orders using numpy array operations.
No Python-level per-row loops — all random sampling is vectorised.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

NUM_USERS       = 20_000
NUM_RESTAURANTS = 500
NUM_ORDERS      = 500_000     # ~25 orders per user on avg

# Five realistic city zones with center coordinates (NYC-inspired)
ZONES = [
    ("Downtown",  40.7128, -74.0060),
    ("Midtown",   40.7549, -73.9840),
    ("Uptown",    40.7831, -73.9712),
    ("Brooklyn",  40.6782, -73.9442),
    ("Queens",    40.7282, -73.7949),
]

ZONE_NAMES = [z[0] for z in ZONES]
ZONE_LATS  = np.array([z[1] for z in ZONES])
ZONE_LONS  = np.array([z[2] for z in ZONES])


def generate_users(rng: np.random.Generator = None):
    """Generate users with zone assignments and jittered lat/lon (vectorised)."""
    if rng is None:
        rng = np.random.default_rng(42)

    zone_idx = rng.integers(0, len(ZONES), size=NUM_USERS)
    return pd.DataFrame({
        "user_id":   np.arange(NUM_USERS),
        "zone":      np.array(ZONE_NAMES)[zone_idx],
        "latitude":  ZONE_LATS[zone_idx] + rng.normal(0, 0.005, NUM_USERS),
        "longitude": ZONE_LONS[zone_idx] + rng.normal(0, 0.005, NUM_USERS),
    })


def generate_restaurants(rng: np.random.Generator = None):
    """Generate restaurants with zone assignments and jittered lat/lon (vectorised)."""
    if rng is None:
        rng = np.random.default_rng(123)

    zone_idx = rng.integers(0, len(ZONES), size=NUM_RESTAURANTS)
    return pd.DataFrame({
        "restaurant_id": np.arange(NUM_RESTAURANTS),
        "rating":    np.round(rng.uniform(3.0, 5.0, NUM_RESTAURANTS), 2),
        "zone":      np.array(ZONE_NAMES)[zone_idx],
        "latitude":  ZONE_LATS[zone_idx] + rng.normal(0, 0.003, NUM_RESTAURANTS),
        "longitude": ZONE_LONS[zone_idx] + rng.normal(0, 0.003, NUM_RESTAURANTS),
    })


def generate_orders(users_df, restaurants_df, rng: np.random.Generator = None):
    """
    Generate orders with location bias (fully vectorised).

    - 20% of users are cold-start (3-5 orders each).
    - 80% of users are warm (remaining orders distributed among them).
    - 70% of each user's orders are from their own zone, 30% global.
    """
    if rng is None:
        rng = np.random.default_rng(777)

    print("  Generating orders (vectorised) ...", flush=True)

    # --- Precompute zone → restaurant mapping + Zipf popularity ---
    zone_to_rids = {}
    zone_to_probs = {}
    for z in ZONE_NAMES:
        mask = restaurants_df["zone"].values == z
        rids = restaurants_df["restaurant_id"].values[mask]
        zone_to_rids[z] = rids
        # Zipf popularity within each zone (rank-based)
        probs = np.arange(1, len(rids) + 1, dtype=np.float64) ** (-1.15)
        rng.shuffle(probs)  # shuffle so ranking isn't correlated with ID
        probs /= probs.sum()
        zone_to_probs[z] = probs

    all_rids = restaurants_df["restaurant_id"].values
    # Global Zipf popularity
    global_probs = np.arange(1, len(all_rids) + 1, dtype=np.float64) ** (-1.15)
    rng.shuffle(global_probs)
    global_probs /= global_probs.sum()

    user_ids = users_df["user_id"].values
    user_zones = users_df["zone"].values

    # --- Phase 1: Cold-start users (20%) get 3-5 orders each ---
    n_cold = max(1, int(0.2 * NUM_USERS))
    cold_uids = user_ids[:n_cold]
    cold_zones = user_zones[:n_cold]
    cold_n_orders = rng.integers(3, 6, size=n_cold)  # 3-5 orders each
    total_cold = int(cold_n_orders.sum())

    # Repeat each cold user by their order count
    cold_user_repeated = np.repeat(cold_uids, cold_n_orders)
    cold_zone_repeated = np.repeat(cold_zones, cold_n_orders)

    # Decide local vs global for each cold order
    is_local = rng.random(total_cold) < 0.7
    cold_rids = np.empty(total_cold, dtype=np.int64)

    for z in ZONE_NAMES:
        zone_mask = cold_zone_repeated == z
        local_mask = zone_mask & is_local
        global_mask = zone_mask & ~is_local
        n_local = int(local_mask.sum())
        n_global = int(global_mask.sum())
        if n_local > 0:
            cold_rids[local_mask] = rng.choice(zone_to_rids[z], size=n_local, p=zone_to_probs[z])
        if n_global > 0:
            cold_rids[global_mask] = rng.choice(all_rids, size=n_global, p=global_probs)

    # --- Phase 2: Warm users get remaining orders ---
    remaining = NUM_ORDERS - total_cold
    warm_uids = user_ids[n_cold:]
    warm_zones_arr = user_zones[n_cold:]

    # Sample warm user indices uniformly
    warm_idx = rng.integers(0, len(warm_uids), size=remaining)
    warm_user_col = warm_uids[warm_idx]
    warm_zone_col = warm_zones_arr[warm_idx]

    is_local_w = rng.random(remaining) < 0.7
    warm_rids = np.empty(remaining, dtype=np.int64)

    for z in ZONE_NAMES:
        zone_mask = warm_zone_col == z
        local_mask = zone_mask & is_local_w
        global_mask = zone_mask & ~is_local_w
        n_local = int(local_mask.sum())
        n_global = int(global_mask.sum())
        if n_local > 0:
            warm_rids[local_mask] = rng.choice(zone_to_rids[z], size=n_local, p=zone_to_probs[z])
        if n_global > 0:
            warm_rids[global_mask] = rng.choice(all_rids, size=n_global, p=global_probs)

    # --- Combine cold + warm ---
    all_user_col = np.concatenate([cold_user_repeated, warm_user_col])
    all_rid_col  = np.concatenate([cold_rids, warm_rids])
    total = len(all_user_col)

    # Vectorised timestamps: random days ago in [0, 30]
    now = np.datetime64(datetime.now(), 's')
    days_ago = rng.integers(0, 31, size=total)
    timestamps = now - (days_ago * 86400).astype('timedelta64[s]')

    print(f"  Building DataFrame ({total:,} orders) ...", flush=True)

    orders_df = pd.DataFrame({
        "order_id":      np.arange(total),
        "user_id":       all_user_col,
        "restaurant_id": all_rid_col,
        "timestamp":     timestamps,
    })

    return orders_df


if __name__ == "__main__":
    import time
    t0 = time.time()
    rng = np.random.default_rng(42)

    print(f"Generating dataset: {NUM_USERS:,} users, "
          f"{NUM_RESTAURANTS:,} restaurants, {NUM_ORDERS:,} orders")

    users = generate_users(rng)
    restaurants = generate_restaurants(rng)
    orders = generate_orders(users, restaurants, rng)

    print("  Writing CSVs ...", flush=True)
    users.to_csv("users.csv", index=False)
    restaurants.to_csv("restaurants.csv", index=False)
    orders.to_csv("orders.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nGenerated: {len(users):,} users, {len(restaurants):,} restaurants, "
          f"{len(orders):,} orders  ({elapsed:.1f}s)")
    print(f"Zones: {ZONE_NAMES}")
    print(f"\nUsers per zone:")
    print(users["zone"].value_counts().to_string())
    print(f"\nCold-start users (3-5 orders): "
          f"{(orders.groupby('user_id').size() <= 5).sum():,}")
    print(f"CSV sizes: users={users.memory_usage(deep=True).sum()/1e6:.1f}MB, "
          f"orders={orders.memory_usage(deep=True).sum()/1e6:.1f}MB")