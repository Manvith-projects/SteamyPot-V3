"""
data_generator.py — Synthetic Driver & Order Data Generator
=============================================================
Generates a realistic fleet of delivery drivers across Hyderabad
with correlated features that mirror real-world distributions.

AI Concept: Synthetic Data Generation with Correlated Features
---------------------------------------------------------------
Real driver fleets exhibit statistical correlations:
  * Experienced drivers (high success rate) tend to have higher ratings.
  * Drivers with more active orders tend to have longer avg delivery times.
  * Driver locations cluster around restaurant-dense neighbourhoods.

We encode these correlations so the allocation model learns meaningful
patterns rather than noise.

Generated Tables:
  drivers.json  — Fleet of 40 drivers with stats
"""

import json
import os
import random
import math

SEED = 42
random.seed(SEED)

# ---------------------------------------------------------------------------
# Hyderabad neighbourhoods (delivery driver home zones)
# ---------------------------------------------------------------------------
LOCATIONS = [
    {"name": "Kukatpally",     "lat": 17.4947, "lon": 78.3996},
    {"name": "Madhapur",       "lat": 17.4486, "lon": 78.3908},
    {"name": "Gachibowli",     "lat": 17.4401, "lon": 78.3489},
    {"name": "Hitech City",    "lat": 17.4435, "lon": 78.3772},
    {"name": "Banjara Hills",  "lat": 17.4156, "lon": 78.4347},
    {"name": "Jubilee Hills",  "lat": 17.4325, "lon": 78.4073},
    {"name": "Kondapur",       "lat": 17.4600, "lon": 78.3548},
    {"name": "Ameerpet",       "lat": 17.4375, "lon": 78.4483},
    {"name": "Begumpet",       "lat": 17.4440, "lon": 78.4674},
    {"name": "Secunderabad",   "lat": 17.4399, "lon": 78.4983},
    {"name": "Dilsukhnagar",   "lat": 17.3688, "lon": 78.5247},
    {"name": "LB Nagar",       "lat": 17.3457, "lon": 78.5522},
    {"name": "Miyapur",        "lat": 17.4969, "lon": 78.3548},
    {"name": "Tolichowki",     "lat": 17.3950, "lon": 78.4139},
    {"name": "Mehdipatnam",    "lat": 17.3950, "lon": 78.4400},
]

# ---------------------------------------------------------------------------
# Driver name pool
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Ravi", "Suresh", "Venkat", "Anil", "Kiran", "Ramesh", "Mahesh",
    "Praveen", "Naveen", "Srinivas", "Harsha", "Vikram", "Arjun",
    "Deepak", "Sandeep", "Rajesh", "Mohan", "Ganesh", "Satish",
    "Prasad", "Ajay", "Vijay", "Sagar", "Rohit", "Amit", "Nikhil",
    "Sunil", "Manoj", "Chandra", "Kalyan", "Phani", "Naresh",
    "Balaji", "Krishna", "Shiva", "Hari", "Raj", "Tarun", "Varun",
    "Srikanth",
]


def _jitter(lat: float, lon: float, radius_km: float = 1.5):
    """Add random GPS jitter within *radius_km* of a centre point."""
    # 1 degree latitude  ≈ 111 km
    # 1 degree longitude ≈ 111 * cos(lat) km
    delta_lat = (random.uniform(-radius_km, radius_km)) / 111.0
    delta_lon = (random.uniform(-radius_km, radius_km)) / (
        111.0 * math.cos(math.radians(lat))
    )
    return round(lat + delta_lat, 6), round(lon + delta_lon, 6)


def generate_drivers(n: int = 40) -> list[dict]:
    """
    Generate *n* synthetic delivery drivers.

    Correlations encoded:
      • base_quality  ∈ [0, 1] drives both rating AND success_rate
        so they are positively correlated (r ≈ 0.7).
      • current_active_orders sampled 0-4; avg_delivery_time increases
        with active load (simulating slower when busy).
    """
    drivers = []
    used_names = set()

    for i in range(n):
        # Unique name
        name = random.choice(FIRST_NAMES)
        while name in used_names:
            name = random.choice(FIRST_NAMES)
        used_names.add(name)

        # Random location near a Hyderabad neighbourhood
        zone = random.choice(LOCATIONS)
        lat, lon = _jitter(zone["lat"], zone["lon"])

        # Hidden quality factor — drives correlated metrics
        base_quality = random.betavariate(5, 2)  # skewed towards high quality

        # Driver rating: 3.0 – 5.0, correlated with quality
        rating = round(3.0 + 2.0 * base_quality + random.gauss(0, 0.15), 2)
        rating = round(max(3.0, min(5.0, rating)), 2)

        # Delivery success rate: 0.75 – 1.0
        success_rate = round(
            0.75 + 0.25 * base_quality + random.gauss(0, 0.03), 4
        )
        success_rate = round(max(0.75, min(1.0, success_rate)), 4)

        # Active orders (0-4): higher for busier drivers
        active_orders = random.choices(
            [0, 1, 2, 3, 4], weights=[25, 35, 25, 10, 5]
        )[0]

        # Average delivery time (minutes): 15-45, increases with load
        base_time = 15 + (1.0 - base_quality) * 15  # better drivers = faster
        load_penalty = active_orders * random.uniform(3, 6)
        avg_delivery_time = round(base_time + load_penalty + random.gauss(0, 2), 1)
        avg_delivery_time = max(12.0, min(55.0, avg_delivery_time))

        drivers.append(
            {
                "driver_id": f"DRV-{i + 1:03d}",
                "driver_name": name,
                "location": {"lat": lat, "lon": lon},
                "zone": zone["name"],
                "driver_rating": rating,
                "current_active_orders": active_orders,
                "average_delivery_time": avg_delivery_time,
                "delivery_success_rate": success_rate,
            }
        )

    return drivers


def save_drivers(out_dir: str = "data") -> str:
    """Generate and persist drivers to data/drivers.json."""
    os.makedirs(out_dir, exist_ok=True)
    drivers = generate_drivers()
    path = os.path.join(out_dir, "drivers.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(drivers, f, indent=2, ensure_ascii=False)
    print(f"[data_generator] [OK] Saved {len(drivers)} drivers to {path}")
    return path


# ---------------------------------------------------------------------------
# Quick CLI test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    save_drivers()
    # Print a sample
    with open("data/drivers.json", encoding="utf-8") as f:
        sample = json.load(f)[:3]
    print(json.dumps(sample, indent=2))
