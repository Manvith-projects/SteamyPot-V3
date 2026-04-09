"""
review_store.py — MongoDB Review Store
========================================
Handles all MongoDB interactions for retrieving restaurant reviews.

This is the DATA RETRIEVAL layer of the RAG pipeline:
  1. Connect to MongoDB Atlas
  2. Fetch reviews for a specific restaurant_id
  3. Return raw review documents for downstream preprocessing

WHY MongoDB?
  - Reviews are semi-structured (text + metadata)
  - We need flexible querying by restaurant_id + timestamp
  - MongoDB Atlas provides managed hosting with built-in indexing
"""

import os
import re
from datetime import datetime, timezone
from typing import Optional
from pymongo import MongoClient, DESCENDING
from bson import ObjectId

try:
    import certifi
except Exception:
    certifi = None

# ---------------------------------------------------------------------------
# MongoDB Configuration
# ---------------------------------------------------------------------------
MONGO_URI = os.getenv(
    "MONGODB_URL",
    "mongodb+srv://manvithsai9689_db_user:Qx0oAKubfhSpoquO@cluster0.otwgjyw.mongodb.net/steamer"
)
DB_NAME = "steamer"
COLLECTION_NAME = "restaurant_reviews"

# Main app MongoDB (for bridging real shop reviews)
MAIN_APP_MONGO_URI = os.getenv(
    "MAIN_APP_MONGODB_URL",
    "mongodb+srv://manvithsai9689_db_user:Steamer23@cluster0.nlsuf8n.mongodb.net/steamypot?retryWrites=true&w=majority"
)
MAIN_APP_DB_NAME = "steamypot"

_OBJECTID_RE = re.compile(r"^[0-9a-fA-F]{24}$")

MONGO_CLIENT_KWARGS = {
    "serverSelectionTimeoutMS": 15000,
    "connectTimeoutMS": 20000,
    "socketTimeoutMS": 20000,
    "tls": True,
    "retryWrites": True,
    "retryReads": True,
}
if certifi is not None:
    MONGO_CLIENT_KWARGS["tlsCAFile"] = certifi.where()


def is_objectid(value: str) -> bool:
    """Check if a string looks like a MongoDB ObjectId."""
    return bool(_OBJECTID_RE.match(value))


class ReviewStore:
    """
    MongoDB-backed store for restaurant reviews.

    Usage:
        store = ReviewStore()
        reviews = store.get_reviews("rest_001")
        store.close()
    """

    def __init__(self, uri: str = MONGO_URI, db_name: str = DB_NAME):
        self.client = MongoClient(uri, **MONGO_CLIENT_KWARGS)
        self.db = self.client[db_name]
        self.collection = self.db[COLLECTION_NAME]

    def get_reviews(
        self,
        restaurant_id: str,
        limit: int = 500,
        since: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Retrieve reviews for a restaurant from MongoDB.

        Parameters
        ----------
        restaurant_id : str
            The unique restaurant identifier (e.g., "rest_001").
        limit : int
            Maximum number of reviews to fetch (default 500).
            We fetch more than 200 to allow for duplicates/spam removal
            in the preprocessing step.
        since : datetime, optional
            If provided, only fetch reviews after this timestamp.

        Returns
        -------
        list[dict]
            List of review documents with keys:
            review_text, rating, restaurant_id, timestamp
        """
        query = {"restaurant_id": restaurant_id}

        if since:
            query["timestamp"] = {"$gte": since}

        # Sort by most recent first — the preprocessing step will
        # cap at the latest 200 after dedup + spam removal
        cursor = self.collection.find(
            query,
            {"_id": 0, "review_text": 1, "rating": 1, "restaurant_id": 1, "timestamp": 1}
        ).sort("timestamp", DESCENDING).limit(limit)

        return list(cursor)

    def get_review_count(self, restaurant_id: str) -> int:
        """Return total review count for a restaurant."""
        return self.collection.count_documents({"restaurant_id": restaurant_id})

    def get_average_rating(self, restaurant_id: str) -> float:
        """Compute the average rating for a restaurant."""
        pipeline = [
            {"$match": {"restaurant_id": restaurant_id}},
            {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}},
        ]
        result = list(self.collection.aggregate(pipeline))
        if result:
            return round(result[0]["avg_rating"], 2)
        return 0.0

    def get_rating_distribution(self, restaurant_id: str) -> dict:
        """Return count of reviews per star rating (1-5)."""
        pipeline = [
            {"$match": {"restaurant_id": restaurant_id}},
            {"$group": {"_id": "$rating", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        result = list(self.collection.aggregate(pipeline))
        distribution = {i: 0 for i in range(1, 6)}
        for doc in result:
            distribution[doc["_id"]] = doc["count"]
        return distribution

    def get_all_restaurant_ids(self) -> list[str]:
        """Return distinct restaurant_ids in the collection."""
        return self.collection.distinct("restaurant_id")

    def ping(self) -> bool:
        """Check if MongoDB connection is alive."""
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def close(self):
        """Close the MongoDB client connection."""
        self.client.close()


# ---------------------------------------------------------------------------
# Main App Review Bridge
# ---------------------------------------------------------------------------
class MainAppReviewBridge:
    """
    Bridge to read reviews from the main app's MongoDB (steamypot).
    Used when restaurant_id is a real shop ObjectId instead of rest_XXX.
    """

    def __init__(self, uri: str = MAIN_APP_MONGO_URI, db_name: str = MAIN_APP_DB_NAME):
        self.client = MongoClient(uri, **MONGO_CLIENT_KWARGS)
        self.db = self.client[db_name]
        self.reviews_col = self.db["reviews"]
        self.shops_col = self.db["shops"]

    def get_shop_info(self, shop_id: str) -> Optional[dict]:
        """Look up shop name and cuisine from the main app's shops collection."""
        try:
            shop = self.shops_col.find_one({"_id": ObjectId(shop_id)})
            if shop:
                return {
                    "id": str(shop["_id"]),
                    "name": shop.get("name", "Unknown Restaurant"),
                    "cuisine": shop.get("category", "Multi-Cuisine"),
                }
        except Exception:
            pass
        return None

    def get_reviews(self, shop_id: str, limit: int = 500) -> list[dict]:
        """Fetch reviews from the main app, mapped to the AI Layer format."""
        try:
            cursor = self.reviews_col.find(
                {"shop": ObjectId(shop_id)},
                {"_id": 0, "reviewText": 1, "rating": 1, "createdAt": 1}
            ).sort("createdAt", DESCENDING).limit(limit)

            return [
                {
                    "review_text": doc.get("reviewText", ""),
                    "rating": doc.get("rating", 3),
                    "restaurant_id": shop_id,
                    "timestamp": doc.get("createdAt"),
                }
                for doc in cursor
                if doc.get("reviewText")
            ]
        except Exception:
            return []

    def get_review_count(self, shop_id: str) -> int:
        try:
            return self.reviews_col.count_documents({"shop": ObjectId(shop_id)})
        except Exception:
            return 0

    def get_average_rating(self, shop_id: str) -> float:
        try:
            pipeline = [
                {"$match": {"shop": ObjectId(shop_id)}},
                {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}},
            ]
            result = list(self.reviews_col.aggregate(pipeline))
            if result:
                return round(result[0]["avg_rating"], 2)
        except Exception:
            pass
        return 0.0

    def get_rating_distribution(self, shop_id: str) -> dict:
        try:
            pipeline = [
                {"$match": {"shop": ObjectId(shop_id)}},
                {"$group": {"_id": "$rating", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
            result = list(self.reviews_col.aggregate(pipeline))
            distribution = {i: 0 for i in range(1, 6)}
            for doc in result:
                distribution[doc["_id"]] = doc["count"]
            return distribution
        except Exception:
            return {i: 0 for i in range(1, 6)}

    def get_reviewed_shops(self) -> list[dict]:
        """Return metadata for shops that have at least one stored review."""
        try:
            shop_ids = self.reviews_col.distinct("shop")
            if not shop_ids:
                return []

            shops = self.shops_col.find(
                {"_id": {"$in": shop_ids}},
                {"name": 1, "category": 1}
            )

            return [
                {
                    "id": str(shop["_id"]),
                    "name": shop.get("name", "Unknown Restaurant"),
                    "cuisine": shop.get("category", "Multi-Cuisine"),
                }
                for shop in shops
            ]
        except Exception:
            return []

    def ping(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def close(self):
        self.client.close()


if __name__ == "__main__":
    # Quick test
    store = ReviewStore()
    if store.ping():
        print("[review_store] MongoDB connection OK")
        ids = store.get_all_restaurant_ids()
        print(f"  Restaurants with reviews: {len(ids)}")
        if ids:
            rid = ids[0]
            reviews = store.get_reviews(rid)
            print(f"  Reviews for {rid}: {len(reviews)}")
            print(f"  Avg rating: {store.get_average_rating(rid)}")
            print(f"  Distribution: {store.get_rating_distribution(rid)}")
    else:
        print("[review_store] MongoDB connection FAILED")
    store.close()
