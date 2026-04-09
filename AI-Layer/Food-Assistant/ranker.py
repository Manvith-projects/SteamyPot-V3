"""
ranker.py  --  Smart Ranking Engine for Food Recommendations
=============================================================
Combines multiple signals to produce a single recommendation score
for each restaurant+item candidate.

AI Concepts
-----------
1. **Learning-to-Rank (simplified)**:
   Production recommenders use ML models (LambdaMART, neural L2R) to
   learn the optimal ranking from click-through data. Here we use a
   weighted linear combination of normalised features -- the simplest
   ranking model that still captures the key trade-offs.

2. **Multi-Objective Ranking**:
   Users care about multiple factors simultaneously:
     * Relevance   -- does the item match their query?
     * Quality     -- is the restaurant well-rated?
     * Proximity   -- how far away is it?
     * Value       -- is the price reasonable?
     * Trust       -- collaborative filtering recommendation score.

   Our ranking formula balances these:
     score = w_rec  * rec_score           (trust-aware CF score)
           + w_rat  * norm_rating         (restaurant quality)
           + w_dist * (1 - norm_distance) (closer = better)
           + w_price* (1 - norm_price)    (cheaper = better, given similar quality)
           + w_match* item_match_boost    (bonus for exact item name match)

3. **Normalisation**:
   Each feature is min-max normalised to [0, 1] so that the weights
   are comparable.  Without normalisation, a feature measured in km
   would dominate one measured in 0-5 stars.

4. **Diversity Injection**:
   We ensure the top-5 results come from different restaurants
   (no restaurant appears twice).  This increases discovery and
   prevents a single high-rated restaurant from monopolising results.
"""

from typing import List, Optional


# ---------------------------------------------------------------------------
# Ranking weights (tunable)
# ---------------------------------------------------------------------------
# These weights reflect business priorities:
#   * rec_score (0.30) -- highest because it incorporates user preferences
#   * rating (0.25) -- restaurant quality matters a lot
#   * distance (0.20) -- proximity affects delivery time
#   * price (0.15) -- value-for-money
#   * item_match (0.10) -- bonus for matching specific food item

W_REC   = 0.30
W_RAT   = 0.25
W_DIST  = 0.20
W_PRICE = 0.15
W_MATCH = 0.10


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _min_max(value: float, min_val: float, max_val: float) -> float:
    """
    Min-max normalise a value to [0, 1].

    AI Concept: Feature Scaling
    ---------------------------
    min-max normalisation preserves the relative ordering and maps
    the feature to a fixed range. This is preferred over z-score
    normalisation for ranking because we need bounded [0,1] values.
    """
    if max_val == min_val:
        return 0.5
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


# ---------------------------------------------------------------------------
# Ranking engine
# ---------------------------------------------------------------------------

def rank_results(
    candidates: List[dict],
    specific_item: Optional[str] = None,
    top_k: int = 5,
) -> List[dict]:
    """
    Score and rank food search candidates.

    AI Concept: Two-Stage Recommender Pattern
    -------------------------------------------
    Stage 1 (database.py): Candidate generation  -- fast filters narrow
            50 restaurants → 10-30 candidates.
    Stage 2 (this function): Ranking -- ML scoring ranks candidates
            by relevance and returns top-K.

    This two-stage pattern is used by Netflix, YouTube, Uber Eats
    because it balances quality with latency:
      * Stage 1: O(n) scan with simple predicates (~1ms)
      * Stage 2: O(k) scoring with feature computation (~2ms)

    Parameters
    ----------
    candidates : list of {restaurant, item, distance_km} dicts
    specific_item : item name the user asked for (for match boost)
    top_k : number of results to return

    Returns
    -------
    list : top-K candidates sorted by score, with score added.
    """
    if not candidates:
        return []

    # -----------------------------------------------------------------------
    # Compute normalisation bounds from this candidate set
    # -----------------------------------------------------------------------
    ratings = [c["restaurant"]["rating"] for c in candidates]
    prices = [c["item"]["price"] for c in candidates]
    distances = [c.get("distance_km") or 0.0 for c in candidates]
    rec_scores = [c["restaurant"]["rec_score"] for c in candidates]

    min_rat, max_rat = min(ratings), max(ratings)
    min_pri, max_pri = min(prices), max(prices)
    min_dist, max_dist = min(distances), max(distances) if distances else (0, 1)
    min_rec, max_rec = min(rec_scores), max(rec_scores)

    # -----------------------------------------------------------------------
    # Score each candidate
    # -----------------------------------------------------------------------
    for c in candidates:
        # Normalised features
        norm_rec = _min_max(c["restaurant"]["rec_score"], min_rec, max_rec)
        norm_rat = _min_max(c["restaurant"]["rating"], min_rat, max_rat)
        norm_dist = _min_max(c.get("distance_km") or 0.0, min_dist, max_dist)
        norm_price = _min_max(c["item"]["price"], min_pri, max_pri)

        # Item name match boost
        item_match = 0.0
        if specific_item:
            item_name_lower = c["item"]["name"].lower()
            if specific_item.lower() in item_name_lower:
                item_match = 1.0
            elif any(word in item_name_lower for word in specific_item.lower().split()):
                item_match = 0.5

        # ---------------------------------------------------------------
        # Final ranking score
        # ---------------------------------------------------------------
        # AI Concept: Weighted Linear Model
        # This is the simplest ranking model. Each feature contributes
        # proportionally to its weight. The score is bounded [0, 1].
        # In production, this would be replaced with a trained model
        # (XGBoost/neural net) using click-through rate as the label.
        score = (
            W_REC   * norm_rec +
            W_RAT   * norm_rat +
            W_DIST  * (1.0 - norm_dist) +    # closer = higher score
            W_PRICE * (1.0 - norm_price) +    # cheaper = higher score
            W_MATCH * item_match
        )

        c["score"] = round(score, 4)
        c["norm_features"] = {
            "rec_score": round(norm_rec, 3),
            "rating": round(norm_rat, 3),
            "distance": round(1.0 - norm_dist, 3),
            "price_value": round(1.0 - norm_price, 3),
            "item_match": round(item_match, 3),
        }

    # -----------------------------------------------------------------------
    # Sort by score (descending)
    # -----------------------------------------------------------------------
    candidates.sort(key=lambda c: c["score"], reverse=True)

    # -----------------------------------------------------------------------
    # Diversity: at most one item per restaurant in top-K
    # -----------------------------------------------------------------------
    # AI Concept: Result Diversification
    # Without diversity, a single high-rated restaurant with 5 menu items
    # could dominate the top-5.  Users value variety -- they want to see
    # different restaurant options.  This is a common technique in search
    # engines (MMR -- Maximal Marginal Relevance).
    seen_restaurants = set()
    diverse_results = []
    for c in candidates:
        rid = c["restaurant"]["id"]
        if rid not in seen_restaurants:
            seen_restaurants.add(rid)
            diverse_results.append(c)
            if len(diverse_results) >= top_k:
                break

    # If we couldn't fill top_k with diversity, fill from remaining
    if len(diverse_results) < top_k:
        for c in candidates:
            if c not in diverse_results:
                diverse_results.append(c)
                if len(diverse_results) >= top_k:
                    break

    return diverse_results
