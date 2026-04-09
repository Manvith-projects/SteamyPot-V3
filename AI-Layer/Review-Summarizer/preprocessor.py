"""
preprocessor.py — Review Preprocessing Pipeline
=================================================
Cleans raw reviews before they enter the RAG pipeline.

Preprocessing steps:
  1. DEDUPLICATION  — Exact and near-duplicate removal
  2. SPAM FILTERING — Heuristic-based spam detection
  3. RECENCY LIMIT  — Keep only the latest 200 reviews

WHY preprocess?
  - Duplicate reviews add noise and bias the embedding space
  - Spam reviews (ads, gibberish) corrupt the vector store
  - Limiting to 200 keeps the pipeline fast and focused on recent feedback
  - Clean data = better embeddings = more relevant retrieval = better summaries
"""

import re
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Spam detection heuristics
# ---------------------------------------------------------------------------

# Patterns that indicate a review is spam
SPAM_PATTERNS = [
    r"https?://",                    # URLs
    r"www\.",                        # Web addresses
    r"\$\d{3,}",                     # Dollar amounts (scam indicators)
    r"click\s+here",                # Clickbait
    r"buy\s+followers",             # Follower spam
    r"earn\s+\$",                   # Money spam
    r"free\s+gift",                 # Gift card spam
    r"working\s+from\s+home",       # Work-from-home scam
    r"sponsored\s+by",              # Sponsored content
    r"totally[\-\s]legit",          # Sarcastic spam
    r"automated\s+fake",            # Bot declaration
    r"copy\s+paste",               # Copy-paste spam
    r"[!]{4,}",                     # Excessive exclamation marks
]

# Compile for performance
_SPAM_REGEX = re.compile("|".join(SPAM_PATTERNS), re.IGNORECASE)


def is_spam(text: str) -> bool:
    """
    Detect spam reviews using heuristic rules.

    A review is flagged as spam if:
      - It matches known spam patterns (URLs, scam phrases, etc.)
      - It's too short to be meaningful (< 10 chars)
      - It has very low alphabetic ratio (gibberish)
      - It has excessive repetition of characters

    Returns True if the review is likely spam.
    """
    # Too short — not a real review
    if len(text.strip()) < 10:
        return True

    # Check for known spam patterns
    if _SPAM_REGEX.search(text):
        return True

    # Low alphabetic ratio — gibberish like "asdfghjkl 12345"
    alpha_chars = sum(1 for c in text if c.isalpha())
    if len(text) > 0 and (alpha_chars / len(text)) < 0.4:
        return True

    # Excessive character repetition (e.g., "aaaaaaaa")
    if re.search(r"(.)\1{6,}", text):
        return True

    return False


def remove_duplicates(reviews: list[dict]) -> list[dict]:
    """
    Remove exact-duplicate reviews (same review_text).

    Uses a set of normalized text for O(n) deduplication.
    Keeps the most recent occurrence of each duplicate.

    Parameters
    ----------
    reviews : list[dict]
        List of review documents (assumed sorted by timestamp descending).

    Returns
    -------
    list[dict]
        Deduplicated list, preserving order.
    """
    seen_texts = set()
    unique_reviews = []

    for review in reviews:
        # Normalize: lowercase, strip whitespace, collapse spaces
        normalized = re.sub(r"\s+", " ", review["review_text"].lower().strip())

        if normalized not in seen_texts:
            seen_texts.add(normalized)
            unique_reviews.append(review)

    return unique_reviews


def filter_spam(reviews: list[dict]) -> tuple[list[dict], int]:
    """
    Remove spam reviews from the list.

    Returns
    -------
    tuple[list[dict], int]
        (filtered_reviews, spam_count)
    """
    clean = []
    spam_count = 0

    for review in reviews:
        if is_spam(review["review_text"]):
            spam_count += 1
        else:
            clean.append(review)

    return clean, spam_count


def limit_to_recent(reviews: list[dict], max_count: int = 200) -> list[dict]:
    """
    Keep only the latest `max_count` reviews.

    Reviews should already be sorted by timestamp descending
    (from the MongoDB query). This just caps the list.

    WHY 200?
      - Enough for statistically meaningful sentiment analysis
      - Not so many that embedding + retrieval becomes slow
      - Focuses on recent, relevant customer feedback
    """
    return reviews[:max_count]


def preprocess_reviews(
    reviews: list[dict],
    max_reviews: int = 200,
) -> dict:
    """
    Full preprocessing pipeline:
      1. Remove duplicates
      2. Filter spam
      3. Limit to latest `max_reviews`

    Parameters
    ----------
    reviews : list[dict]
        Raw reviews from MongoDB (sorted by timestamp desc).
    max_reviews : int
        Maximum reviews to keep after cleaning.

    Returns
    -------
    dict with keys:
        clean_reviews : list[dict]  — Processed reviews
        stats : dict — Preprocessing statistics
    """
    original_count = len(reviews)

    # Step 1: Remove duplicates
    deduped = remove_duplicates(reviews)
    duplicates_removed = original_count - len(deduped)

    # Step 2: Filter spam
    clean, spam_removed = filter_spam(deduped)

    # Step 3: Limit to recent reviews
    limited = limit_to_recent(clean, max_reviews)

    stats = {
        "original_count": original_count,
        "duplicates_removed": duplicates_removed,
        "spam_removed": spam_removed,
        "after_cleaning": len(clean),
        "final_count": len(limited),
        "truncated": len(clean) > max_reviews,
    }

    return {
        "clean_reviews": limited,
        "stats": stats,
    }


if __name__ == "__main__":
    # Quick self-test with sample data
    sample_reviews = [
        {"review_text": "Great food, loved it!", "rating": 5, "restaurant_id": "rest_001",
         "timestamp": datetime(2026, 1, 15)},
        {"review_text": "Great food, loved it!", "rating": 5, "restaurant_id": "rest_001",
         "timestamp": datetime(2026, 1, 10)},  # duplicate
        {"review_text": "Buy followers at www.fakesite.com!", "rating": 1, "restaurant_id": "rest_001",
         "timestamp": datetime(2026, 1, 12)},  # spam
        {"review_text": "Decent meal, nothing special.", "rating": 3, "restaurant_id": "rest_001",
         "timestamp": datetime(2026, 1, 14)},
        {"review_text": "asdfghjkl", "rating": 1, "restaurant_id": "rest_001",
         "timestamp": datetime(2026, 1, 11)},  # spam (gibberish)
    ]

    result = preprocess_reviews(sample_reviews)
    print(f"Stats: {result['stats']}")
    print(f"Clean reviews ({len(result['clean_reviews'])}):")
    for r in result["clean_reviews"]:
        print(f"  [{r['rating']}★] {r['review_text']}")
