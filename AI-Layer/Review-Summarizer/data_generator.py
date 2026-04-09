"""
data_generator.py — Synthetic Review Data Generator
=====================================================
Generates realistic restaurant reviews and inserts them into MongoDB.

Each review document contains:
  - restaurant_id  : str   (e.g., "rest_001")
  - review_text    : str   (natural language review)
  - rating         : int   (1-5 stars)
  - timestamp      : datetime

This gives us a realistic corpus for the RAG summarization pipeline.
"""

import os
import random
import datetime
from pymongo import MongoClient

# ---------------------------------------------------------------------------
# MongoDB connection
# ---------------------------------------------------------------------------
MONGO_URI = os.getenv(
    "MONGODB_URL",
    "mongodb+srv://manvithsai9689_db_user:Qx0oAKubfhSpoquO@cluster0.otwgjyw.mongodb.net/steamer"
)
DB_NAME = "steamer"
COLLECTION_NAME = "restaurant_reviews"

# ---------------------------------------------------------------------------
# Restaurant metadata  (15 restaurants)
# ---------------------------------------------------------------------------
RESTAURANTS = [
    {"id": "rest_001", "name": "Spice Garden", "cuisine": "North Indian"},
    {"id": "rest_002", "name": "Biryani Palace", "cuisine": "Hyderabadi"},
    {"id": "rest_003", "name": "Dosa Corner", "cuisine": "South Indian"},
    {"id": "rest_004", "name": "Wok Express", "cuisine": "Chinese"},
    {"id": "rest_005", "name": "Pizza Planet", "cuisine": "Italian"},
    {"id": "rest_006", "name": "Burger Barn", "cuisine": "American"},
    {"id": "rest_007", "name": "Sushi Station", "cuisine": "Japanese"},
    {"id": "rest_008", "name": "Kebab King", "cuisine": "Mughlai"},
    {"id": "rest_009", "name": "Green Leaf", "cuisine": "Healthy"},
    {"id": "rest_010", "name": "Tandoor Nights", "cuisine": "Punjabi"},
    {"id": "rest_011", "name": "Chaat Street", "cuisine": "Street Food"},
    {"id": "rest_012", "name": "Coastal Catch", "cuisine": "Seafood"},
    {"id": "rest_013", "name": "Curry House", "cuisine": "South Indian"},
    {"id": "rest_014", "name": "Noodle Bar", "cuisine": "Pan-Asian"},
    {"id": "rest_015", "name": "Sweet Spot", "cuisine": "Desserts"},
]

# ---------------------------------------------------------------------------
# Review templates — categorized by sentiment so generated reviews
# are realistic and correlate with their star rating.
# ---------------------------------------------------------------------------

POSITIVE_REVIEWS = [
    "Absolutely loved the food! Fresh ingredients and amazing flavors.",
    "Best {cuisine} food I've had in a long time. Will definitely order again.",
    "The delivery was super fast and the food was still hot. Great experience!",
    "Portion sizes are generous and the taste is authentic. Highly recommend!",
    "Tried their special thali and it was a feast. Every dish was delicious.",
    "Great packaging, food arrived in perfect condition. Top quality!",
    "Been ordering from here for months. Consistently great quality.",
    "The butter chicken here is out of this world. Creamy and flavorful.",
    "Loved the variety on the menu. Everything we tried was excellent.",
    "Quick delivery, reasonable prices, and fantastic taste. What more do you need?",
    "My go-to place for {cuisine} cravings. Never disappoints!",
    "Amazing flavors! You can tell they use fresh spices.",
    "The staff was very helpful when I called about a customization. Food was perfect.",
    "Ordered for a party of 10 and everyone loved it. Great for group orders!",
    "The biryani rice was perfectly cooked, meat was tender. Chef's kiss!",
    "Love their weekend specials. Always something new and exciting.",
    "Healthy options that actually taste good! Rare find.",
    "The gravy was rich and the naan was soft and fresh. Excellent combo.",
    "Ordered desserts on a whim — the gulab jamun was heavenly!",
    "Five stars is not enough. This place deserves all the praise.",
    "One of the best restaurants on this platform. Period.",
    "Their paneer tikka is matchless. Perfectly marinated and grilled.",
    "Food quality has been consistent across all my 20+ orders.",
    "Clean packaging, labeled allergens, fresh food. Very professional.",
    "The masala dosa was crispy and the chutney had a lovely tang.",
]

NEUTRAL_REVIEWS = [
    "Food was okay. Nothing special but not bad either.",
    "Decent food, slightly overpriced for the portion size.",
    "Delivery took a bit longer than expected but the food was alright.",
    "Average taste, could use more seasoning. It was fine for a quick meal.",
    "Good food but the packaging could be better. Some items leaked.",
    "Taste was fine, but the menu hasn't changed in ages. Need more variety.",
    "The appetizers were great but the mains were underwhelming.",
    "Reasonable quality for the price point. Not my first choice though.",
    "Food was warm but not hot. Taste was acceptable.",
    "I'd rate this somewhere in the middle. Some items hit, some miss.",
    "Ordered three items — two were good, one was disappointingly bland.",
    "It's a safe option when you can't decide what else to eat.",
    "Not bad for a weeknight dinner. Gets the job done.",
    "The rice was good but the curry lacked depth in flavor.",
    "Consistent mediocre quality. Not terrible, not great.",
]

NEGATIVE_REVIEWS = [
    "Very disappointing. Food was cold and tasteless.",
    "Waited over an hour for delivery. Food was soggy by the time it arrived.",
    "Found a hair in my food. Absolutely unacceptable hygiene standards.",
    "Portion size was laughably small for the price. Total rip-off.",
    "The food tasted stale. I suspect it was reheated leftover food.",
    "Ordered butter chicken and got plain gravy with barely any chicken pieces.",
    "Way too oily and greasy. Could not finish the meal.",
    "Completely wrong order delivered. Customer support was unhelpful.",
    "The biryani was just flavored rice with no meat. Very misleading menu photos.",
    "Never ordering again. Quality has gone down drastically.",
    "Food gave me a stomach ache. Questionable freshness of ingredients.",
    "The packaging was leaking all over. What a mess!",
    "Overpriced and underwhelming. Save your money and cook at home.",
    "Spice level was insane even though I asked for mild. Inedible.",
    "Delivery guy was rude and the food was cold. Terrible experience overall.",
    "Menu shows one thing, you get something completely different.",
    "Used to be good but quality has dropped significantly in recent months.",
    "The naan was hard as cardboard. Clearly not freshly made.",
    "Charged extra for items that should be included. Sneaky pricing.",
    "Worst food I've ever ordered on this app. Zero stars if I could.",
]

SPAM_REVIEWS = [
    "Buy followers at www.fakesite.com! Cheap prices!",
    "EARN $5000 WORKING FROM HOME! Click here!!!",
    "asdfghjkl random text spam 12345 garbage review",
    "This review is sponsored by XYZ Company. Visit us now!",
    "FREE GIFT CARDS available at totally-legit-site.com",
    "!!!!! BEST DEAL EVER !!!!! Not about food at all !!!!!",
    "Copy paste copy paste copy paste review template bot",
    "I am a bot and this is an automated fake review submission.",
]

DUPLICATE_TEMPLATES = [
    "Great food, loved it!",
    "Good food, fast delivery.",
    "Nice restaurant, will order again.",
]


def _random_timestamp(days_back: int = 365) -> datetime.datetime:
    """Return a random datetime within the last `days_back` days."""
    offset = random.randint(0, days_back * 24 * 3600)
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=offset)


def generate_reviews_for_restaurant(restaurant: dict, count: int = 250) -> list[dict]:
    """
    Generate `count` reviews for a single restaurant.

    Distribution logic:
      - ~50% positive (4-5 stars)
      - ~25% neutral  (3 stars)
      - ~15% negative (1-2 stars)
      - ~5%  duplicates  (to test dedup logic)
      - ~5%  spam         (to test spam filter)
    """
    reviews = []

    for _ in range(int(count * 0.50)):
        text = random.choice(POSITIVE_REVIEWS).format(cuisine=restaurant["cuisine"])
        reviews.append({
            "restaurant_id": restaurant["id"],
            "restaurant_name": restaurant["name"],
            "review_text": text,
            "rating": random.choice([4, 5]),
            "timestamp": _random_timestamp(),
        })

    for _ in range(int(count * 0.25)):
        text = random.choice(NEUTRAL_REVIEWS)
        reviews.append({
            "restaurant_id": restaurant["id"],
            "restaurant_name": restaurant["name"],
            "review_text": text,
            "rating": 3,
            "timestamp": _random_timestamp(),
        })

    for _ in range(int(count * 0.15)):
        text = random.choice(NEGATIVE_REVIEWS)
        reviews.append({
            "restaurant_id": restaurant["id"],
            "restaurant_name": restaurant["name"],
            "review_text": text,
            "rating": random.choice([1, 2]),
            "timestamp": _random_timestamp(),
        })

    # Duplicates (exact copies to test dedup)
    for _ in range(int(count * 0.05)):
        text = random.choice(DUPLICATE_TEMPLATES)
        reviews.append({
            "restaurant_id": restaurant["id"],
            "restaurant_name": restaurant["name"],
            "review_text": text,
            "rating": random.choice([3, 4]),
            "timestamp": _random_timestamp(),
        })

    # Spam reviews (to test spam filter)
    for _ in range(int(count * 0.05)):
        text = random.choice(SPAM_REVIEWS)
        reviews.append({
            "restaurant_id": restaurant["id"],
            "restaurant_name": restaurant["name"],
            "review_text": text,
            "rating": random.choice([1, 5]),  # spam often has extreme ratings
            "timestamp": _random_timestamp(),
        })

    random.shuffle(reviews)
    return reviews


def seed_database(drop_existing: bool = True) -> dict:
    """
    Seed MongoDB with synthetic reviews for all restaurants.

    Returns a summary dict with counts.
    """
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    if drop_existing:
        collection.drop()
        print(f"[data_generator] Dropped existing '{COLLECTION_NAME}' collection.")

    total_inserted = 0
    for restaurant in RESTAURANTS:
        reviews = generate_reviews_for_restaurant(restaurant, count=250)
        if reviews:
            collection.insert_many(reviews)
            total_inserted += len(reviews)
            print(f"  → Inserted {len(reviews)} reviews for {restaurant['name']} ({restaurant['id']})")

    # Create indexes for fast queries
    collection.create_index("restaurant_id")
    collection.create_index("timestamp")
    collection.create_index([("restaurant_id", 1), ("timestamp", -1)])

    summary = {
        "restaurants": len(RESTAURANTS),
        "total_reviews": total_inserted,
        "collection": COLLECTION_NAME,
        "database": DB_NAME,
    }
    print(f"\n[data_generator] Seeding complete: {total_inserted} reviews for {len(RESTAURANTS)} restaurants.")
    client.close()
    return summary


def get_restaurant_list() -> list[dict]:
    """Return the list of restaurant metadata."""
    return RESTAURANTS


if __name__ == "__main__":
    seed_database()
