"""
data_generator.py  --  Synthetic Order & Event Data Generator
==============================================================
Creates a realistic food-delivery event stream with:

  * 200 customers across Hyderabad
  * 50 drivers with availability states
  * 500 historical orders with delivery events
  * Problem events: delays, cancellations, negative reviews

AI Concept: Synthetic Event Stream Generation
----------------------------------------------
Autonomous agents operate on real-time event streams.  When building
an agent before production data exists, we synthesise event logs that
mirror real-world probability distributions:

  * **Delay times** follow a log-normal distribution (most deliveries
    are on time, with a long tail of extreme delays).
  * **Cancellation probability** correlates with driver distance and
    time of day (dinner rush → higher cancellation).
  * **Negative review probability** increases with delivery delay
    (correlated features make the agent's rules meaningful).

The generator produces *labelled* events so the autonomous agent can
be tested deterministically before connecting to real Kafka/RabbitMQ
streams.
"""

import json
import os
import random
import math
import uuid
from datetime import datetime, timedelta

SEED = 42
random.seed(SEED)

# ---------------------------------------------------------------------------
# Hyderabad delivery zones
# ---------------------------------------------------------------------------
ZONES = [
    {"name": "Kukatpally",    "lat": 17.4947, "lon": 78.3996},
    {"name": "Madhapur",      "lat": 17.4486, "lon": 78.3908},
    {"name": "Gachibowli",    "lat": 17.4401, "lon": 78.3489},
    {"name": "Hitech City",   "lat": 17.4435, "lon": 78.3772},
    {"name": "Banjara Hills", "lat": 17.4156, "lon": 78.4347},
    {"name": "Kondapur",      "lat": 17.4600, "lon": 78.3548},
    {"name": "Ameerpet",      "lat": 17.4375, "lon": 78.4483},
    {"name": "Begumpet",      "lat": 17.4440, "lon": 78.4674},
    {"name": "Miyapur",       "lat": 17.4969, "lon": 78.3548},
    {"name": "Dilsukhnagar",  "lat": 17.3688, "lon": 78.5247},
]

# ---------------------------------------------------------------------------
# Restaurant names
# ---------------------------------------------------------------------------
RESTAURANTS = [
    "Paradise Biryani", "Bawarchi", "Shah Ghouse", "Cream Stone",
    "Mehfil", "Pista House", "Chutneys", "Minerva Coffee Shop",
    "Ohri's", "Barbeque Nation", "AB's", "Rayalaseema Ruchulu",
    "Kritunga", "Ulavacharu", "Spicy Venue", "Domino's",
    "Pizza Hut", "McDonald's", "KFC", "Subway",
]

# ---------------------------------------------------------------------------
# Customer names (synthetic)
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Sai", "Arjun", "Reyansh", "Ayaan",
    "Krishna", "Ishaan", "Dhruv", "Ananya", "Diya", "Myra", "Saanvi",
    "Aanya", "Aadhya", "Isha", "Kiara", "Riya", "Nisha",
]
LAST_NAMES = [
    "Reddy", "Sharma", "Patel", "Kumar", "Rao", "Singh", "Gupta",
    "Verma", "Iyer", "Nair", "Joshi", "Mehta", "Shah", "Das",
]

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _uid(prefix: str = "ord") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Distance in km between two lat/lon points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def generate_customers(n: int = 200) -> list:
    """Generate synthetic customer profiles."""
    customers = []
    for i in range(n):
        zone = random.choice(ZONES)
        customers.append({
            "customer_id": f"cust_{i:04d}",
            "name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            "zone": zone["name"],
            "lat": zone["lat"] + random.uniform(-0.01, 0.01),
            "lon": zone["lon"] + random.uniform(-0.01, 0.01),
            "total_orders": random.randint(1, 120),
            "avg_rating_given": round(random.uniform(2.5, 5.0), 1),
        })
    return customers


def generate_drivers(n: int = 50) -> list:
    """
    Generate synthetic driver profiles with availability.

    AI Concept: State-based Agent Modelling
    -----------------------------------------
    Each driver is modelled as an entity with a mutable state
    (available / on_delivery / offline).  The recovery agent
    queries this state when it needs to reassign a driver after
    a cancellation — mimicking how real dispatch systems work.
    """
    drivers = []
    for i in range(n):
        zone = random.choice(ZONES)
        drivers.append({
            "driver_id": f"drv_{i:03d}",
            "name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)[0]}.",
            "zone": zone["name"],
            "lat": zone["lat"] + random.uniform(-0.005, 0.005),
            "lon": zone["lon"] + random.uniform(-0.005, 0.005),
            "status": random.choices(
                ["available", "on_delivery", "offline"],
                weights=[0.5, 0.35, 0.15],
            )[0],
            "rating": round(random.uniform(3.5, 5.0), 2),
            "deliveries_today": random.randint(0, 12),
        })
    return drivers


def generate_orders_and_events(
    customers: list,
    drivers: list,
    n_orders: int = 500,
) -> tuple:
    """
    Generate orders and their associated delivery events.

    AI Concept: Event-Driven Architecture for Autonomous Agents
    -----------------------------------------------------------
    Autonomous agents react to *events* rather than polling.
    Each order produces a timeline of events:

        order_placed → driver_assigned → picked_up → delivered
                        ↘ (or) driver_cancelled
                                        ↘ (or) delivery_delay
                                        ↘ (or) order_cancelled

    The agent subscribes to problem events and triggers recovery
    actions.  This generator creates a realistic mix:
      * ~15% of orders experience delays > 15 min
      * ~5% have driver cancellations
      * ~3% are order cancellations
      * ~10% receive negative reviews (rating ≤ 2)
    """
    orders = []
    events = []
    base_time = datetime(2026, 3, 1, 10, 0, 0)

    for i in range(n_orders):
        cust = random.choice(customers)
        driver = random.choice([d for d in drivers if d["status"] != "offline"] or drivers)
        restaurant = random.choice(RESTAURANTS)
        rzone = random.choice(ZONES)

        order_time = base_time + timedelta(
            hours=random.randint(0, 72),
            minutes=random.randint(0, 59),
        )
        order_id = _uid("ord")
        estimated_delivery_min = random.randint(20, 50)

        dist_km = _haversine(
            rzone["lat"], rzone["lon"],
            cust["lat"], cust["lon"],
        )

        order = {
            "order_id": order_id,
            "customer_id": cust["customer_id"],
            "customer_name": cust["name"],
            "driver_id": driver["driver_id"],
            "driver_name": driver["name"],
            "restaurant": restaurant,
            "restaurant_zone": rzone["name"],
            "customer_zone": cust["zone"],
            "distance_km": round(dist_km, 2),
            "order_value": round(random.uniform(150, 900), 2),
            "estimated_delivery_min": estimated_delivery_min,
            "order_time": order_time.isoformat(),
        }
        orders.append(order)

        # Always emit order_placed
        events.append({
            "event_id": _uid("evt"),
            "order_id": order_id,
            "event_type": "order_placed",
            "timestamp": order_time.isoformat(),
            "details": {},
        })

        # Probability-weighted problem events
        roll = random.random()

        if roll < 0.03:
            # ── Order cancelled ──
            cancel_time = order_time + timedelta(minutes=random.randint(5, 20))
            reason = random.choice([
                "customer_requested", "restaurant_closed",
                "payment_failed", "item_unavailable",
            ])
            events.append({
                "event_id": _uid("evt"),
                "order_id": order_id,
                "event_type": "order_cancelled",
                "timestamp": cancel_time.isoformat(),
                "details": {"reason": reason},
            })

        elif roll < 0.08:
            # ── Driver cancelled ──
            cancel_time = order_time + timedelta(minutes=random.randint(3, 15))
            events.append({
                "event_id": _uid("evt"),
                "order_id": order_id,
                "event_type": "driver_cancelled",
                "timestamp": cancel_time.isoformat(),
                "details": {
                    "cancelled_driver_id": driver["driver_id"],
                    "cancelled_driver_name": driver["name"],
                    "reason": random.choice([
                        "vehicle_breakdown", "personal_emergency",
                        "too_far", "shift_ended",
                    ]),
                },
            })

        elif roll < 0.23:
            # ── Delivery delay ──
            delay_min = random.choices(
                [random.randint(16, 29), random.randint(30, 60)],
                weights=[0.6, 0.4],
            )[0]
            delay_time = order_time + timedelta(
                minutes=estimated_delivery_min + delay_min,
            )
            events.append({
                "event_id": _uid("evt"),
                "order_id": order_id,
                "event_type": "delivery_delay",
                "timestamp": delay_time.isoformat(),
                "details": {
                    "estimated_delivery_min": estimated_delivery_min,
                    "actual_delivery_min": estimated_delivery_min + delay_min,
                    "delay_min": delay_min,
                },
            })

        else:
            # ── Normal delivery ──
            deliver_time = order_time + timedelta(minutes=estimated_delivery_min + random.randint(-5, 5))
            events.append({
                "event_id": _uid("evt"),
                "order_id": order_id,
                "event_type": "delivered",
                "timestamp": deliver_time.isoformat(),
                "details": {},
            })

        # ── Negative review (can happen on top of delay or normal) ──
        if random.random() < 0.10:
            review_time = order_time + timedelta(
                minutes=estimated_delivery_min + random.randint(10, 120),
            )
            rating = random.choice([1, 1, 1, 2, 2])
            comment = random.choice([
                "Food was cold and arrived very late.",
                "Terrible experience. Never ordering again.",
                "Wrong items delivered. Very disappointed.",
                "Driver was rude and food was spilled.",
                "Waited forever. Worst delivery service.",
                "Order was incomplete, missing items.",
                "Packaging was damaged, food leaked everywhere.",
                "Extremely slow delivery during non-peak hours.",
            ])
            events.append({
                "event_id": _uid("evt"),
                "order_id": order_id,
                "event_type": "negative_review",
                "timestamp": review_time.isoformat(),
                "details": {
                    "rating": rating,
                    "comment": comment,
                },
            })

    return orders, events


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_data(data_dir: str = "data") -> dict:
    """
    Generate all synthetic data and save to JSON files.

    Returns a summary dict with counts.
    """
    os.makedirs(data_dir, exist_ok=True)

    customers = generate_customers(200)
    drivers = generate_drivers(50)
    orders, events = generate_orders_and_events(customers, drivers, 500)

    for name, payload in [
        ("customers.json", customers),
        ("drivers.json", drivers),
        ("orders.json", orders),
        ("events.json", events),
    ]:
        path = os.path.join(data_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    summary = {
        "customers": len(customers),
        "drivers": len(drivers),
        "orders": len(orders),
        "events": len(events),
        "problem_events": sum(
            1 for e in events
            if e["event_type"] in {
                "delivery_delay", "driver_cancelled",
                "order_cancelled", "negative_review",
            }
        ),
    }
    print(f"[data_generator] Saved {summary}")
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    save_data()
