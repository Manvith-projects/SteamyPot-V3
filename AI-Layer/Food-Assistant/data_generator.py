"""
data_generator.py  --  Synthetic Restaurant & Menu Database Generator
=====================================================================
Creates a realistic food-delivery dataset with:

  * 50 restaurants across Hyderabad (varied cuisines, locations)
  * 300+ menu items with prices, tags, diet types
  * Trust-aware recommendation scores per restaurant

AI Concept: Synthetic Data Generation
--------------------------------------
Real-world ML systems need data to function. When actual data is
unavailable (privacy, cold-start), we generate synthetic datasets
that mirror production distributions. Key properties:

  * **Realistic distributions** -- prices follow log-normal (clustered
    around ₹150-350 with a long tail for premium items).
  * **Correlated features** -- higher-rated restaurants tend to have
    slightly higher prices (quality-price correlation).
  * **Location clustering** -- restaurants cluster in known Hyderabad
    neighbourhoods, mimicking real delivery-zone density.
"""

import json
import os
import random
import math

SEED = 42
random.seed(SEED)

# ---------------------------------------------------------------------------
# Hyderabad neighbourhoods with approximate lat/lon
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
# Cuisine & diet taxonomy
# ---------------------------------------------------------------------------
CUISINES = [
    "North Indian", "South Indian", "Chinese", "Biryani",
    "Italian", "Continental", "Street Food", "Mughlai",
    "Desserts", "Healthy Bowls", "Fast Food", "Seafood",
]

DIET_TYPES = ["veg", "non-veg", "vegan", "egg"]

TAGS = [
    "spicy", "mild", "healthy", "comfort", "light",
    "heavy", "protein-rich", "low-calorie", "gluten-free",
    "keto", "high-fibre", "traditional", "fusion",
]

MEAL_TIMES = ["breakfast", "lunch", "dinner", "snack", "all-day"]

# ---------------------------------------------------------------------------
# Offer / discount templates
# ---------------------------------------------------------------------------
OFFER_TEMPLATES = [
    {"type": "percent_off", "label": "{pct}% OFF",        "values": [10, 15, 20, 25, 30, 40, 50]},
    {"type": "flat_off",    "label": "₹{amt} OFF",        "values": [30, 50, 75, 100, 125, 150]},
    {"type": "bogo",        "label": "Buy 1 Get 1 Free",  "values": []},
    {"type": "free_delivery","label": "FREE Delivery",    "values": []},
    {"type": "combo",       "label": "Combo: {desc}",     "values": [
        "2 items @ ₹199", "Meal + Drink @ ₹249", "Family Pack @ ₹499",
    ]},
]

# ---------------------------------------------------------------------------
# Menu item templates per cuisine
# ---------------------------------------------------------------------------
MENU_TEMPLATES = {
    "North Indian": [
        ("Butter Chicken", "non-veg", ["spicy", "comfort", "heavy"], "dinner", (220, 380)),
        ("Paneer Tikka Masala", "veg", ["spicy", "protein-rich"], "dinner", (180, 300)),
        ("Dal Makhani", "veg", ["comfort", "traditional"], "all-day", (150, 250)),
        ("Chicken Tikka", "non-veg", ["spicy", "protein-rich"], "dinner", (200, 350)),
        ("Aloo Paratha", "veg", ["comfort", "heavy"], "breakfast", (80, 150)),
        ("Chole Bhature", "veg", ["heavy", "traditional"], "lunch", (120, 200)),
        ("Rajma Chawal", "veg", ["comfort", "protein-rich"], "lunch", (130, 220)),
        ("Tandoori Roti", "veg", ["light"], "all-day", (30, 60)),
    ],
    "South Indian": [
        ("Masala Dosa", "veg", ["light", "traditional"], "breakfast", (80, 160)),
        ("Idli Sambar", "veg", ["healthy", "light", "low-calorie"], "breakfast", (60, 120)),
        ("Hyderabadi Chicken Biryani", "non-veg", ["spicy", "heavy"], "lunch", (250, 400)),
        ("Pesarattu", "veg", ["healthy", "protein-rich", "high-fibre"], "breakfast", (70, 130)),
        ("Uttapam", "veg", ["light"], "breakfast", (90, 160)),
        ("Medu Vada", "veg", ["comfort"], "breakfast", (60, 110)),
        ("Pongal", "veg", ["comfort", "traditional"], "breakfast", (80, 140)),
    ],
    "Chinese": [
        ("Veg Manchurian", "veg", ["spicy", "comfort"], "dinner", (150, 260)),
        ("Chicken Fried Rice", "non-veg", ["comfort", "heavy"], "lunch", (180, 300)),
        ("Hakka Noodles", "veg", ["comfort"], "all-day", (140, 240)),
        ("Chilli Chicken", "non-veg", ["spicy", "protein-rich"], "dinner", (200, 340)),
        ("Spring Rolls", "veg", ["light"], "snack", (100, 180)),
        ("Schezwan Noodles", "veg", ["spicy"], "all-day", (150, 250)),
        ("Dragon Chicken", "non-veg", ["spicy", "fusion"], "dinner", (220, 360)),
    ],
    "Biryani": [
        ("Hyderabadi Dum Biryani", "non-veg", ["spicy", "heavy", "traditional"], "lunch", (250, 450)),
        ("Veg Biryani", "veg", ["comfort"], "lunch", (180, 300)),
        ("Egg Biryani", "egg", ["comfort"], "lunch", (180, 300)),
        ("Mutton Biryani", "non-veg", ["spicy", "heavy", "traditional"], "lunch", (300, 500)),
        ("Chicken 65 Biryani", "non-veg", ["spicy"], "dinner", (280, 420)),
    ],
    "Italian": [
        ("Margherita Pizza", "veg", ["comfort"], "dinner", (200, 400)),
        ("Pasta Alfredo", "veg", ["comfort", "heavy"], "dinner", (220, 380)),
        ("Chicken Penne Arrabiata", "non-veg", ["spicy"], "dinner", (250, 420)),
        ("Garlic Bread", "veg", ["light"], "snack", (80, 160)),
        ("Bruschetta", "veg", ["light", "healthy"], "snack", (120, 200)),
    ],
    "Continental": [
        ("Grilled Chicken Salad", "non-veg", ["healthy", "light", "low-calorie", "protein-rich"], "lunch", (220, 380)),
        ("Quinoa Bowl", "vegan", ["healthy", "protein-rich", "gluten-free", "keto"], "lunch", (250, 400)),
        ("Avocado Toast", "vegan", ["healthy", "light"], "breakfast", (180, 300)),
        ("Mushroom Soup", "veg", ["light", "healthy"], "dinner", (140, 240)),
        ("Grilled Fish", "non-veg", ["healthy", "protein-rich", "low-calorie"], "dinner", (280, 450)),
    ],
    "Street Food": [
        ("Pani Puri", "veg", ["light", "traditional"], "snack", (40, 80)),
        ("Samosa", "veg", ["comfort", "traditional"], "snack", (30, 60)),
        ("Vada Pav", "veg", ["comfort"], "snack", (40, 80)),
        ("Bhel Puri", "veg", ["light"], "snack", (50, 100)),
        ("Dahi Puri", "veg", ["light"], "snack", (50, 100)),
        ("Pav Bhaji", "veg", ["comfort", "heavy"], "dinner", (100, 180)),
    ],
    "Mughlai": [
        ("Mutton Korma", "non-veg", ["heavy", "traditional"], "dinner", (300, 480)),
        ("Shahi Paneer", "veg", ["comfort", "traditional"], "dinner", (200, 340)),
        ("Chicken Nihari", "non-veg", ["spicy", "heavy"], "dinner", (280, 420)),
        ("Naan", "veg", ["light"], "all-day", (40, 80)),
        ("Kebab Platter", "non-veg", ["protein-rich", "spicy"], "dinner", (350, 550)),
    ],
    "Desserts": [
        ("Gulab Jamun", "veg", ["comfort", "traditional"], "all-day", (60, 120)),
        ("Rasgulla", "veg", ["light", "traditional"], "all-day", (60, 120)),
        ("Brownie with Ice Cream", "veg", ["comfort"], "all-day", (150, 280)),
        ("Fruit Custard", "veg", ["light", "healthy"], "all-day", (80, 150)),
        ("Double Ka Meetha", "veg", ["traditional", "comfort"], "all-day", (80, 140)),
    ],
    "Healthy Bowls": [
        ("Acai Bowl", "vegan", ["healthy", "low-calorie", "high-fibre"], "breakfast", (250, 400)),
        ("Chicken Protein Bowl", "non-veg", ["healthy", "protein-rich", "keto"], "lunch", (280, 420)),
        ("Mediterranean Salad", "veg", ["healthy", "light", "low-calorie"], "lunch", (200, 350)),
        ("Smoothie Bowl", "vegan", ["healthy", "light"], "breakfast", (200, 350)),
        ("Poke Bowl", "non-veg", ["healthy", "protein-rich"], "lunch", (300, 450)),
    ],
    "Fast Food": [
        ("Classic Burger", "non-veg", ["comfort", "heavy"], "all-day", (120, 250)),
        ("Veg Burger", "veg", ["comfort"], "all-day", (100, 200)),
        ("French Fries", "veg", ["comfort"], "snack", (80, 150)),
        ("Chicken Wrap", "non-veg", ["light"], "lunch", (140, 260)),
        ("Loaded Nachos", "veg", ["comfort"], "snack", (150, 280)),
    ],
    "Seafood": [
        ("Fish Curry", "non-veg", ["spicy", "traditional"], "dinner", (250, 400)),
        ("Prawn Masala", "non-veg", ["spicy", "protein-rich"], "dinner", (300, 480)),
        ("Fish Fry", "non-veg", ["comfort", "protein-rich"], "snack", (180, 300)),
        ("Crab Roast", "non-veg", ["spicy", "heavy"], "dinner", (350, 550)),
    ],
}

# ---------------------------------------------------------------------------
# Restaurant name components
# ---------------------------------------------------------------------------
PREFIXES = [
    "Royal", "Spice", "Green", "Golden", "Silver", "Taste",
    "Fresh", "Pure", "Grand", "Little", "Urban", "Desi",
    "Paradise", "Classic", "Fusion", "Saffron", "Bawarchi",
]
SUFFIXES = [
    "Kitchen", "Bites", "Express", "Dhaba", "Garden",
    "House", "Cafe", "Hub", "Grill", "Palace", "Point",
    "Junction", "Bowl", "Corner", "Eatery",
]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def _random_name(used: set) -> str:
    """Generate a unique restaurant name."""
    for _ in range(100):
        name = f"{random.choice(PREFIXES)} {random.choice(SUFFIXES)}"
        if name not in used:
            used.add(name)
            return name
    return f"Restaurant {len(used)+1}"


def _haversine_km(lat1, lon1, lat2, lon2):
    """
    Haversine formula  --  great-circle distance between two GPS points.

    AI Concept: Distance Calculation
    --------------------------------
    We use the Haversine formula rather than Euclidean distance because
    the Earth is a sphere. At Hyderabad's latitude (~17°N), 1° longitude
    ≈ 107 km and 1° latitude ≈ 111 km. Euclidean distance on raw
    lat/lon would be inaccurate by ~5-10 % at these scales.
    """
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def generate_database(n_restaurants: int = 50) -> dict:
    """
    Generate the complete restaurant + menu database.

    AI Concept: Feature-rich Synthetic Data
    ----------------------------------------
    Each restaurant carries metadata that the ranking engine uses:
      * rating        -- average customer rating (3.2 - 4.9)
      * rec_score     -- trust-aware recommendation score from the
                         collaborative-filtering recommender (0-1).
      * avg_prep_time -- average kitchen preparation time in minutes.

    These features feed into the smart ranking formula:
      rank = 0.35 * rec_score + 0.30 * normalised_rating
           + 0.20 * (1 - normalised_distance) + 0.15 * (1 - price_ratio)
    """
    used_names = set()
    restaurants = []
    menu_items = []
    menu_id = 1

    for rid in range(1, n_restaurants + 1):
        # Pick 1-3 cuisines per restaurant
        n_cuisines = random.choices([1, 2, 3], weights=[0.3, 0.5, 0.2])[0]
        cuisines = random.sample(CUISINES, n_cuisines)

        # Location
        loc = random.choice(LOCATIONS)
        # Add small jitter (±0.01°) so restaurants aren't at the exact same point
        lat = round(loc["lat"] + random.uniform(-0.01, 0.01), 6)
        lon = round(loc["lon"] + random.uniform(-0.01, 0.01), 6)

        # Rating & recommendation score (correlated)
        rating = round(random.uniform(3.2, 4.9), 1)
        # rec_score positively correlated with rating + noise
        rec_score = round(min(1.0, max(0.0,
            (rating - 3.0) / 2.0 + random.uniform(-0.15, 0.15)
        )), 3)

        avg_prep_time = random.randint(10, 35)  # minutes
        is_open = True  # all open for demo

        # ----------- Restaurant-level offer (40% chance) -----------
        rest_offer = None
        if random.random() < 0.40:
            tpl = random.choice(OFFER_TEMPLATES)
            if tpl["type"] == "percent_off":
                pct = random.choice(tpl["values"])
                rest_offer = {"type": tpl["type"], "label": tpl["label"].format(pct=pct), "value": pct}
            elif tpl["type"] == "flat_off":
                amt = random.choice(tpl["values"])
                rest_offer = {"type": tpl["type"], "label": tpl["label"].format(amt=amt), "value": amt}
            elif tpl["type"] == "bogo":
                rest_offer = {"type": tpl["type"], "label": tpl["label"], "value": None}
            elif tpl["type"] == "free_delivery":
                rest_offer = {"type": tpl["type"], "label": tpl["label"], "value": None}
            elif tpl["type"] == "combo":
                desc = random.choice(tpl["values"])
                rest_offer = {"type": tpl["type"], "label": tpl["label"].format(desc=desc), "value": desc}

        rest = {
            "id": rid,
            "name": _random_name(used_names),
            "cuisines": cuisines,
            "location": loc["name"],
            "lat": lat,
            "lon": lon,
            "rating": rating,
            "rec_score": rec_score,
            "avg_prep_time": avg_prep_time,
            "is_open": is_open,
            "offer": rest_offer,
        }
        restaurants.append(rest)

        # Generate menu items for this restaurant
        for cuisine in cuisines:
            templates = MENU_TEMPLATES.get(cuisine, [])
            # Pick 3-5 items per cuisine
            n_items = min(len(templates), random.randint(3, 5))
            chosen = random.sample(templates, n_items)

            for (item_name, diet, tags, meal_time, price_range) in chosen:
                price = round(random.uniform(price_range[0], price_range[1]))
                # Add restaurant-level price modifier (premium restaurants = +10-20%)
                if rating > 4.3:
                    price = round(price * random.uniform(1.05, 1.20))

                # ----------- Item-level offer (25% chance) -----------
                item_offer = None
                if random.random() < 0.25:
                    tpl = random.choice(OFFER_TEMPLATES[:2])  # percent or flat off
                    if tpl["type"] == "percent_off":
                        pct = random.choice([10, 15, 20, 25, 30])
                        item_offer = {"type": tpl["type"], "label": f"{pct}% OFF", "value": pct}
                    elif tpl["type"] == "flat_off":
                        amt = random.choice([v for v in tpl["values"] if v < price * 0.4]) if price > 100 else None
                        if amt:
                            item_offer = {"type": tpl["type"], "label": f"₹{amt} OFF", "value": amt}

                menu_item = {
                    "id": menu_id,
                    "restaurant_id": rid,
                    "name": item_name,
                    "price": price,
                    "cuisine": cuisine,
                    "diet_type": diet,
                    "tags": tags,
                    "meal_time": meal_time,
                    "offer": item_offer,
                }
                menu_items.append(menu_item)
                menu_id += 1

    return {
        "restaurants": restaurants,
        "menu_items": menu_items,
    }


def save_database(db: dict, data_dir: str = "data"):
    """Save generated data as JSON files."""
    os.makedirs(data_dir, exist_ok=True)

    rest_path = os.path.join(data_dir, "restaurants.json")
    with open(rest_path, "w", encoding="utf-8") as f:
        json.dump(db["restaurants"], f, indent=2, ensure_ascii=False)
    print(f"[data_generator] {len(db['restaurants'])} restaurants -> {rest_path}")

    menu_path = os.path.join(data_dir, "menu_items.json")
    with open(menu_path, "w", encoding="utf-8") as f:
        json.dump(db["menu_items"], f, indent=2, ensure_ascii=False)
    print(f"[data_generator] {len(db['menu_items'])} menu items  -> {menu_path}")


if __name__ == "__main__":
    db = generate_database()
    save_database(db)
