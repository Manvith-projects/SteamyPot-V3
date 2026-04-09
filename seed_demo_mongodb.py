import os
import random
from datetime import datetime, timezone, timedelta

import bcrypt
import certifi
from pymongo import MongoClient, InsertOne


def _load_uri() -> str:
    def _normalize(uri: str) -> str:
        uri = uri.strip().strip('"').strip("'")
        if uri.endswith("/"):
            uri = uri[:-1]
        return uri

    env_uri = os.getenv("MONGODB_URL")
    if env_uri:
        return _normalize(env_uri)

    backend_env = os.path.join(os.path.dirname(__file__), "backend", ".env")
    backend_env = os.path.abspath(backend_env)
    if os.path.exists(backend_env):
        with open(backend_env, "r", encoding="utf-8") as file:
            for line in file:
                if "MONGODB_URL" in line and "=" in line:
                    return _normalize(line.split("=", 1)[1])

    raise RuntimeError("MONGODB_URL not found in environment or backend/.env")


def _bulk_insert(collection, docs, chunk_size: int = 1000):
    for i in range(0, len(docs), chunk_size):
        chunk = docs[i:i + chunk_size]
        ops = [InsertOne(d) for d in chunk]
        collection.bulk_write(ops, ordered=False)


def _random_location_for_zone(zone: str) -> tuple[float, float]:
    zone_centers = {
        "Downtown": (17.3850, 78.4867),
        "Midtown": (17.4300, 78.4500),
        "Uptown": (17.4700, 78.3900),
        "Brooklyn": (17.4100, 78.5200),
        "Queens": (17.3600, 78.5600),
    }
    lat0, lon0 = zone_centers.get(zone, (17.3850, 78.4867))
    lat = lat0 + random.uniform(-0.02, 0.02)
    lon = lon0 + random.uniform(-0.02, 0.02)
    return round(lat, 6), round(lon, 6)


def seed_demo_data(
    users_count: int = 10_000,
    restaurants_count: int = 10_000,
    orders_count: int = 10_000,
    replace_existing: bool = True,
):
    mongo_uri = _load_uri()
    client = MongoClient(mongo_uri, tls=True, tlsAllowInvalidCertificates=True)

    try:
        db = client["steamer"]
        users_col = db["users"]
        restaurants_col = db["restaurants"]
        orders_col = db["orders"]

        tag = f"demo_seed_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        now = datetime.now(timezone.utc)

        if replace_existing:
            users_col.drop()
            restaurants_col.drop()
            orders_col.drop()

        roles = ["user", "owner", "rider", "admin"]
        weather_types = ["Clear", "Cloudy", "Fog", "Rain", "Storm"]
        rider_availability_types = ["high", "medium", "low"]
        order_size_types = ["small", "medium", "large"]
        zones = ["Downtown", "Midtown", "Uptown", "Brooklyn", "Queens"]

        # ---------- Fixed demo accounts (known credentials) ----------
        hashed_pw = bcrypt.hashpw(b"Demo@1234", bcrypt.gensalt()).decode()

        demo_accounts = [
            # ── User accounts ──
            {
                "user_id": 100001,
                "fullName": "Demo User",
                "email": "user@steamer.demo",
                "password": hashed_pw,
                "mobile": "9000000001",
                "role": "user",
                "zone": "Downtown",
                "lat": 17.3850, "lon": 78.4867,
                "orders_last_30d": 12.0, "orders_last_90d": 30.0,
                "avg_order_value": 450.00, "days_since_last_order": 2.0,
                "order_frequency": 2.5, "cancellation_rate": 0.03,
                "avg_delivery_delay_min": 8.5, "avg_user_rating": 4.6,
                "num_complaints": 0.0, "discount_usage_rate": 0.25,
                "app_sessions_per_week": 18.0, "preferred_order_hour": 19.0,
                "account_age_days": 365.0,
            },
            {
                "user_id": 100002,
                "fullName": "Rahul Sharma",
                "email": "user2@steamer.demo",
                "password": hashed_pw,
                "mobile": "9000000002",
                "role": "user",
                "zone": "Midtown",
                "lat": 17.4300, "lon": 78.4500,
                "orders_last_30d": 1.0, "orders_last_90d": 4.0,
                "avg_order_value": 220.00, "days_since_last_order": 45.0,
                "order_frequency": 0.33, "cancellation_rate": 0.20,
                "avg_delivery_delay_min": 22.0, "avg_user_rating": 3.1,
                "num_complaints": 5.0, "discount_usage_rate": 0.80,
                "app_sessions_per_week": 2.0, "preferred_order_hour": 13.0,
                "account_age_days": 90.0,
            },
            # ── Owner (restaurant) accounts ──
            {
                "user_id": 100003,
                "fullName": "Demo Owner",
                "email": "owner@steamer.demo",
                "password": hashed_pw,
                "mobile": "9000000003",
                "role": "owner",
                "zone": "Downtown",
                "lat": 17.3870, "lon": 78.4890,
                "orders_last_30d": 0.0, "orders_last_90d": 0.0,
                "avg_order_value": 0.0, "days_since_last_order": 0.0,
                "order_frequency": 0.0, "cancellation_rate": 0.0,
                "avg_delivery_delay_min": 0.0, "avg_user_rating": 0.0,
                "num_complaints": 0.0, "discount_usage_rate": 0.0,
                "app_sessions_per_week": 12.0, "preferred_order_hour": 10.0,
                "account_age_days": 730.0,
            },
            {
                "user_id": 100004,
                "fullName": "Priya Kitchen",
                "email": "owner2@steamer.demo",
                "password": hashed_pw,
                "mobile": "9000000004",
                "role": "owner",
                "zone": "Uptown",
                "lat": 17.4700, "lon": 78.3900,
                "orders_last_30d": 0.0, "orders_last_90d": 0.0,
                "avg_order_value": 0.0, "days_since_last_order": 0.0,
                "order_frequency": 0.0, "cancellation_rate": 0.0,
                "avg_delivery_delay_min": 0.0, "avg_user_rating": 0.0,
                "num_complaints": 0.0, "discount_usage_rate": 0.0,
                "app_sessions_per_week": 15.0, "preferred_order_hour": 9.0,
                "account_age_days": 540.0,
            },
            # ── Rider (delivery) accounts ──
            {
                "user_id": 100005,
                "fullName": "Demo Rider",
                "email": "rider@steamer.demo",
                "password": hashed_pw,
                "mobile": "9000000005",
                "role": "rider",
                "zone": "Midtown",
                "lat": 17.4350, "lon": 78.4550,
                "orders_last_30d": 0.0, "orders_last_90d": 0.0,
                "avg_order_value": 0.0, "days_since_last_order": 0.0,
                "order_frequency": 0.0, "cancellation_rate": 0.0,
                "avg_delivery_delay_min": 0.0, "avg_user_rating": 0.0,
                "num_complaints": 0.0, "discount_usage_rate": 0.0,
                "app_sessions_per_week": 20.0, "preferred_order_hour": 11.0,
                "account_age_days": 200.0,
            },
            {
                "user_id": 100006,
                "fullName": "Vikram Rider",
                "email": "rider2@steamer.demo",
                "password": hashed_pw,
                "mobile": "9000000006",
                "role": "rider",
                "zone": "Brooklyn",
                "lat": 17.4100, "lon": 78.5200,
                "orders_last_30d": 0.0, "orders_last_90d": 0.0,
                "avg_order_value": 0.0, "days_since_last_order": 0.0,
                "order_frequency": 0.0, "cancellation_rate": 0.0,
                "avg_delivery_delay_min": 0.0, "avg_user_rating": 0.0,
                "num_complaints": 0.0, "discount_usage_rate": 0.0,
                "app_sessions_per_week": 22.0, "preferred_order_hour": 12.0,
                "account_age_days": 150.0,
            },
            # ── Admin accounts ──
            {
                "user_id": 100007,
                "fullName": "Demo Admin",
                "email": "admin@steamer.demo",
                "password": hashed_pw,
                "mobile": "9000000007",
                "role": "admin",
                "zone": "Downtown",
                "lat": 17.3850, "lon": 78.4867,
                "orders_last_30d": 0.0, "orders_last_90d": 0.0,
                "avg_order_value": 0.0, "days_since_last_order": 0.0,
                "order_frequency": 0.0, "cancellation_rate": 0.0,
                "avg_delivery_delay_min": 0.0, "avg_user_rating": 0.0,
                "num_complaints": 0.0, "discount_usage_rate": 0.0,
                "app_sessions_per_week": 25.0, "preferred_order_hour": 9.0,
                "account_age_days": 1000.0,
            },
            {
                "user_id": 100008,
                "fullName": "Super Admin",
                "email": "admin2@steamer.demo",
                "password": hashed_pw,
                "mobile": "9000000008",
                "role": "admin",
                "zone": "Queens",
                "lat": 17.3600, "lon": 78.5600,
                "orders_last_30d": 0.0, "orders_last_90d": 0.0,
                "avg_order_value": 0.0, "days_since_last_order": 0.0,
                "order_frequency": 0.0, "cancellation_rate": 0.0,
                "avg_delivery_delay_min": 0.0, "avg_user_rating": 0.0,
                "num_complaints": 0.0, "discount_usage_rate": 0.0,
                "app_sessions_per_week": 25.0, "preferred_order_hour": 8.0,
                "account_age_days": 1200.0,
            },
        ]

        for acc in demo_accounts:
            acc.update({"source": "demo_seed", "seed_tag": tag, "createdAt": now, "updatedAt": now})

        # ---------- Bulk random users ----------
        user_docs = list(demo_accounts)
        tag_digits = "".join(ch for ch in tag if ch.isdigit())
        mobile_prefix = tag_digits[-3:] if len(tag_digits) >= 3 else "777"
        for i in range(users_count):
            idx = i + 1
            zone = random.choice(zones)
            user_lat, user_lon = _random_location_for_zone(zone)
            account_age_days = random.randint(30, 1825)
            orders_last_90d = random.randint(0, 45)
            orders_last_30d = random.randint(0, min(orders_last_90d, 20))
            order_frequency = round(orders_last_90d / 12.0, 2)

            user_docs.append(
                {
                    "user_id": idx,
                    "fullName": f"Demo User {idx}",
                    "email": f"demo_user_{tag}_{idx}@example.com",
                    "password": "demo123",
                    "mobile": f"9{mobile_prefix}{idx:06d}"[-10:],
                    "role": random.choices(roles, weights=[0.70, 0.15, 0.10, 0.05], k=1)[0],
                    "zone": zone,
                    "lat": user_lat,
                    "lon": user_lon,

                    # Churn model raw features
                    "orders_last_30d": float(orders_last_30d),
                    "orders_last_90d": float(orders_last_90d),
                    "avg_order_value": round(random.uniform(120, 850), 2),
                    "days_since_last_order": float(random.randint(0, 120)),
                    "order_frequency": float(order_frequency),
                    "cancellation_rate": round(random.uniform(0.0, 0.45), 3),
                    "avg_delivery_delay_min": round(random.uniform(5, 35), 2),
                    "avg_user_rating": round(random.uniform(2.5, 5.0), 2),
                    "num_complaints": float(random.randint(0, 8)),
                    "discount_usage_rate": round(random.uniform(0.0, 0.9), 3),
                    "app_sessions_per_week": round(random.uniform(0.5, 25), 2),
                    "preferred_order_hour": float(random.randint(0, 23)),
                    "account_age_days": float(account_age_days),

                    "source": "demo_seed",
                    "seed_tag": tag,
                    "createdAt": now,
                    "updatedAt": now,
                }
            )

        cuisines = ["Indian", "Chinese", "Italian", "Mexican", "American", "Japanese"]

        # ---------- Fixed demo restaurants (linked to owner accounts) ----------
        demo_restaurants = [
            {
                "restaurant_id": "demo_rest_owner_1",
                "name": "Demo Owner's Kitchen",
                "owner_user_id": 100003,
                "zone": "Downtown",
                "zone_id": 1,
                "lat": 17.3870, "lon": 78.4890,
                "cuisine": "Indian",
                "rating": 4.5,
                "avg_prep_time_min": 18.0,
                "source": "demo_seed", "seed_tag": tag,
                "createdAt": now, "updatedAt": now,
            },
            {
                "restaurant_id": "demo_rest_owner_2",
                "name": "Priya's Flavours",
                "owner_user_id": 100004,
                "zone": "Uptown",
                "zone_id": 3,
                "lat": 17.4710, "lon": 78.3920,
                "cuisine": "Chinese",
                "rating": 4.2,
                "avg_prep_time_min": 22.0,
                "source": "demo_seed", "seed_tag": tag,
                "createdAt": now, "updatedAt": now,
            },
        ]

        restaurant_docs = list(demo_restaurants)
        for i in range(restaurants_count):
            idx = i + 1
            zone = random.choice(zones)
            rest_lat, rest_lon = _random_location_for_zone(zone)
            restaurant_docs.append(
                {
                    "restaurant_id": f"demo_rest_{tag}_{idx}",
                    "name": f"Demo Restaurant {idx}",
                    "zone": zone,
                    "zone_id": zones.index(zone) + 1,
                    "lat": rest_lat,
                    "lon": rest_lon,
                    "cuisine": random.choice(cuisines),
                    "rating": round(random.uniform(3.0, 5.0), 1),
                    "avg_prep_time_min": round(random.uniform(10, 35), 2),
                    "source": "demo_seed",
                    "seed_tag": tag,
                    "createdAt": now,
                    "updatedAt": now,
                }
            )

        user_lookup = {d["user_id"]: d for d in user_docs}
        restaurant_lookup = {d["restaurant_id"]: d for d in restaurant_docs}
        user_ids = list(user_lookup.keys())
        restaurant_ids = list(restaurant_lookup.keys())

        order_statuses = ["placed", "accepted", "preparing", "on_the_way", "delivered"]

        # ---------- Fixed demo orders for demo accounts ----------
        demo_order_scenarios = [
            # User 100001 — delivered order (happy path, for ETA / pricing / recommendation)
            {"user_id": 100001, "restaurant_id": "demo_rest_owner_1", "status": "delivered",
             "weather": "Clear", "traffic_level_int": 3, "recovery_type": None},
            # User 100001 — delayed order (triggers recovery agent)
            {"user_id": 100001, "restaurant_id": "demo_rest_owner_2", "status": "on_the_way",
             "weather": "Rain", "traffic_level_int": 8, "recovery_type": "delivery_delay"},
            # User 100002 — cancelled (high churn risk scenario)
            {"user_id": 100002, "restaurant_id": "demo_rest_owner_1", "status": "delivered",
             "weather": "Cloudy", "traffic_level_int": 5, "recovery_type": "negative_review"},
            # User 100002 — order cancelled
            {"user_id": 100002, "restaurant_id": "demo_rest_owner_2", "status": "accepted",
             "weather": "Storm", "traffic_level_int": 9, "recovery_type": "order_cancelled"},
        ]

        order_docs = []
        demo_order_idx = 0
        for sc in demo_order_scenarios:
            demo_order_idx += 1
            u_doc = user_lookup[sc["user_id"]]
            r_doc = restaurant_lookup[sc["restaurant_id"]]
            ts = now - timedelta(hours=random.randint(1, 48))
            dist_km = round(random.uniform(2.0, 10.0), 2)
            prep = r_doc["avg_prep_time_min"]
            tl_text = "low" if sc["traffic_level_int"] <= 3 else ("medium" if sc["traffic_level_int"] <= 7 else "high")
            rec_event = None
            if sc["recovery_type"]:
                rec_event = {
                    "event_type": sc["recovery_type"],
                    "order_id": f"demo_ord_fixed_{demo_order_idx}",
                    "details": {"delay_min": random.randint(15, 45), "reason": random.choice(["traffic", "weather", "driver_issue", "restaurant_delay"])},
                }
            order_docs.append({
                "order_id": f"demo_ord_fixed_{demo_order_idx}",
                "user_id": sc["user_id"],
                "user_ref": u_doc["email"],
                "restaurant_id": sc["restaurant_id"],
                "amount": round(random.uniform(200, 800), 2),
                "items_count": random.randint(1, 5),
                "status": sc["status"],
                "restaurant_lat": r_doc["lat"], "restaurant_lon": r_doc["lon"],
                "customer_lat": u_doc["lat"], "customer_lon": u_doc["lon"],
                "order_hour": ts.hour, "day_of_week": ts.weekday(),
                "weather": sc["weather"],
                "traffic_level": tl_text,
                "prep_time_min": prep,
                "rider_availability": random.choice(rider_availability_types),
                "order_size": random.choice(order_size_types),
                "historical_avg_delivery_min": round(prep + dist_km * random.uniform(2.0, 4.0), 2),
                "is_holiday": 0,
                "traffic_level_int": sc["traffic_level_int"],
                "active_orders": random.randint(30, 120),
                "available_riders": random.randint(10, 60),
                "avg_prep_time_min": prep,
                "zone_id": r_doc["zone_id"],
                "distance_km": dist_km,
                "hist_demand_trend": round(random.uniform(0.8, 1.5), 3),
                "hist_cancel_rate": round(random.uniform(0.02, 0.15), 3),
                "base_delivery_fee": round(25.0 + 1.5 * r_doc["zone_id"] + 2.0 * dist_km, 2),
                "restaurant_location": {"lat": r_doc["lat"], "lon": r_doc["lon"]},
                "customer_location": {"lat": u_doc["lat"], "lon": u_doc["lon"]},
                "estimated_prep_time": prep,
                "order_size_count": random.randint(1, 5),
                "recovery_event": rec_event or {
                    "event_type": "none", "order_id": f"demo_ord_fixed_{demo_order_idx}", "details": {}
                },
                "timestamp": ts, "source": "demo_seed", "seed_tag": tag,
                "createdAt": ts, "updatedAt": ts,
            })

        # ---------- Bulk random orders ----------
        for i in range(orders_count):
            idx = i + 1
            ts = now - timedelta(minutes=random.randint(0, 60 * 24 * 90))
            user_id = random.choice(user_ids)
            restaurant_id = random.choice(restaurant_ids)
            user_doc = user_lookup[user_id]
            restaurant_doc = restaurant_lookup[restaurant_id]

            order_hour = ts.hour
            day_of_week = ts.weekday()
            weather = random.choice(weather_types)
            traffic_level_int = random.randint(1, 10)
            traffic_level_text = (
                "low" if traffic_level_int <= 3 else
                "medium" if traffic_level_int <= 7 else
                "high"
            )
            rider_availability = random.choice(rider_availability_types)
            order_size_text = random.choice(order_size_types)
            items_count = random.randint(1, 8)
            distance_km = round(random.uniform(0.8, 18.0), 2)
            prep_time_min = restaurant_doc["avg_prep_time_min"]
            historical_avg_delivery_min = round(max(10.0, prep_time_min + distance_km * random.uniform(2.0, 4.5)), 2)
            active_orders = random.randint(10, 250)
            available_riders = random.randint(5, 150)
            hist_cancel_rate = round(random.uniform(0.01, 0.25), 3)
            hist_demand_trend = round(random.uniform(0.7, 1.8), 3)
            base_delivery_fee = round(25.0 + 1.5 * restaurant_doc["zone_id"] + 2.0 * distance_km, 2)

            restaurant_location = {
                "lat": restaurant_doc["lat"],
                "lon": restaurant_doc["lon"],
            }
            customer_location = {
                "lat": user_doc["lat"],
                "lon": user_doc["lon"],
            }

            order_docs.append(
                {
                    "order_id": f"demo_ord_{tag}_{idx}",
                    "user_id": user_id,
                    "user_ref": user_doc["email"],
                    "restaurant_id": restaurant_id,
                    "amount": round(random.uniform(120, 1500), 2),
                    "items_count": items_count,
                    "status": random.choice(order_statuses),

                    # ETA parameters
                    "restaurant_lat": restaurant_doc["lat"],
                    "restaurant_lon": restaurant_doc["lon"],
                    "customer_lat": user_doc["lat"],
                    "customer_lon": user_doc["lon"],
                    "order_hour": order_hour,
                    "day_of_week": day_of_week,
                    "weather": weather,
                    "traffic_level": traffic_level_text,
                    "prep_time_min": prep_time_min,
                    "rider_availability": rider_availability,
                    "order_size": order_size_text,
                    "historical_avg_delivery_min": historical_avg_delivery_min,

                    # Pricing parameters
                    "is_holiday": 1 if day_of_week in (5, 6) and random.random() < 0.2 else 0,
                    "traffic_level_int": traffic_level_int,
                    "active_orders": active_orders,
                    "available_riders": available_riders,
                    "avg_prep_time_min": prep_time_min,
                    "zone_id": restaurant_doc["zone_id"],
                    "distance_km": distance_km,
                    "hist_demand_trend": hist_demand_trend,
                    "hist_cancel_rate": hist_cancel_rate,
                    "base_delivery_fee": base_delivery_fee,

                    # Driver allocation request-ready payload
                    "restaurant_location": restaurant_location,
                    "customer_location": customer_location,
                    "estimated_prep_time": prep_time_min,
                    "order_size_count": items_count,

                    # Recovery agent event skeleton
                    "recovery_event": {
                        "event_type": random.choice(["delivery_delay", "driver_cancelled", "order_cancelled", "negative_review"]),
                        "order_id": f"demo_ord_{tag}_{idx}",
                        "details": {
                            "delay_min": random.randint(10, 90),
                            "reason": random.choice(["traffic", "weather", "driver_issue", "restaurant_delay"]),
                        },
                    },

                    "timestamp": ts,
                    "source": "demo_seed",
                    "seed_tag": tag,
                    "createdAt": ts,
                    "updatedAt": ts,
                }
            )

        print(
            f"[seed] inserting users={users_count}, restaurants={restaurants_count}, "
            f"orders={orders_count} (tag={tag}, replace_existing={replace_existing})"
        )
        _bulk_insert(users_col, user_docs)
        _bulk_insert(restaurants_col, restaurant_docs)
        _bulk_insert(orders_col, order_docs)

        users_col.create_index("seed_tag")
        users_col.create_index("user_id", unique=True)
        users_col.create_index("email", unique=True)
        users_col.create_index("mobile", unique=True)
        users_col.create_index([("zone", 1), ("role", 1)])
        restaurants_col.create_index("seed_tag")
        restaurants_col.create_index("restaurant_id", unique=True)
        restaurants_col.create_index([("zone_id", 1), ("rating", -1)])
        orders_col.create_index("seed_tag")
        orders_col.create_index("order_id", unique=True)
        orders_col.create_index([("user_id", 1), ("timestamp", -1)])
        orders_col.create_index([("restaurant_id", 1), ("timestamp", -1)])
        orders_col.create_index([("status", 1), ("timestamp", -1)])

        summary = {
            "seed_tag": tag,
            "inserted": {
                "users": users_count,
                "restaurants": restaurants_count,
                "orders": orders_count,
            },
            "counts_for_tag": {
                "users": users_col.count_documents({"seed_tag": tag}),
                "restaurants": restaurants_col.count_documents({"seed_tag": tag}),
                "orders": orders_col.count_documents({"seed_tag": tag}),
            },
            "total_counts": {
                "users": users_col.estimated_document_count(),
                "restaurants": restaurants_col.estimated_document_count(),
                "orders": orders_col.estimated_document_count(),
            },
        }

        print("[seed] completed")
        print(summary)
        return summary
    finally:
        client.close()


if __name__ == "__main__":
    seed_demo_data()
