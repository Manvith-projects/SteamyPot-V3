"""
recommender.py — Multi-Strategy Trust-Aware Restaurant Recommender

Supports four scoring strategies:

    1. "popularity"    — Globally popular restaurants the user hasn't visited.
    2. "trust_basic"   — Neighbour trust = shared restaurant count.
    3. "trust_cosine"  — Trust = alpha*common + beta*cosine_similarity (binary).
    4. "trust_full"    — Trust = alpha*common + beta*cosine_similarity (decayed).

For trust-based strategies, the score of restaurant r for user u is:

    score(u, r) = SUM over neighbours v of  Trust(u,v) * signal(v, r)

where signal(v, r) depends on the strategy:
    - trust_basic / trust_cosine: 1 for each order v placed at r  (count)
    - trust_full: temporally-decayed weight of v's orders at r

All functions operate on pre-computed data structures (dicts / numpy arrays)
and do ZERO DataFrame filtering, making them safe for tight evaluation loops.
"""

from __future__ import annotations
import numpy as np


# ---------------------------------------------------------------------------
# Popularity baseline
# ---------------------------------------------------------------------------

def recommend_popularity(user_id: int,
                         global_popularity: list[int],
                         user_visited: set[int],
                         k: int = 5) -> list[int]:
    """
    Recommend the K most globally popular restaurants the user has NOT
    visited in training data.

    Parameters
    ----------
    user_id : int
    global_popularity : list[int]
        Restaurant IDs sorted descending by order count.
    user_visited : set[int]
        Restaurants the user already ordered from (training set).
    k : int

    Returns
    -------
    list[int]  Top-K restaurant IDs.
    """
    recs: list[int] = []
    for r in global_popularity:
        if r not in user_visited:
            recs.append(r)
            if len(recs) >= k:
                break
    return recs


# ---------------------------------------------------------------------------
# Trust-based recommendation (basic & cosine — count-weighted signals)
# ---------------------------------------------------------------------------

def recommend_trust(user_id: int,
                    graph,
                    user_order_list: dict[int, list[int]],
                    k: int = 5) -> list[int]:
    """
    Trust-based scoring where each neighbour's orders contribute
    proportionally to the edge trust weight.

    score(r) = SUM_v  Trust(u,v) * count_of_r_in_v's_orders

    Works for strategies: trust_basic, trust_cosine.
    The trust weight already encodes the chosen formula (basic or cosine)
    because it's baked into the graph edge weight.
    """
    if user_id not in graph or graph.degree(user_id) == 0:
        return []

    scores: dict[int, float] = {}
    for neighbor in graph[user_id]:
        trust = graph[user_id][neighbor]["weight"]
        for r in user_order_list.get(neighbor, []):
            scores[r] = scores.get(r, 0.0) + trust

    sorted_recs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [r for r, _ in sorted_recs[:k]]


# ---------------------------------------------------------------------------
# Trust-based recommendation with temporal decay signals
# ---------------------------------------------------------------------------

def recommend_trust_full(user_id: int,
                         graph,
                         user_order_weighted: dict[int, dict[int, float]],
                         k: int = 5) -> list[int]:
    """
    Trust-based scoring where each neighbour's restaurant signal is
    temporally-decayed rather than a raw count.

    score(r) = SUM_v  Trust(u,v) * decayed_weight(v, r)

    Parameters
    ----------
    user_order_weighted : dict[int, dict[int, float]]
        Mapping  user_id → {restaurant_id → summed_decayed_weight}.
        Pre-computed once from the decayed interaction matrix.
    """
    if user_id not in graph or graph.degree(user_id) == 0:
        return []

    scores: dict[int, float] = {}
    for neighbor in graph[user_id]:
        trust = graph[user_id][neighbor]["weight"]
        for r, w in user_order_weighted.get(neighbor, {}).items():
            scores[r] = scores.get(r, 0.0) + trust * w

    sorted_recs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [r for r, _ in sorted_recs[:k]]


# ---------------------------------------------------------------------------
# Unified dispatcher
# ---------------------------------------------------------------------------

def recommend(user_id: int,
              strategy: str,
              graph,
              user_order_list: dict[int, list[int]],
              user_order_weighted: dict[int, dict[int, float]] | None,
              global_popularity: list[int],
              user_visited: set[int],
              k: int = 5) -> list[int]:
    """
    Unified recommendation interface.

    Parameters
    ----------
    strategy : str
        One of {"popularity", "trust_basic", "trust_cosine", "trust_full"}.
    graph : nx.Graph
        Social graph with trust-weighted edges.
    user_order_list : dict
        user_id → [restaurant_id, ...] with duplicates (for count scoring).
    user_order_weighted : dict or None
        user_id → {restaurant_id: decayed_weight}  (only for trust_full).
    global_popularity : list
        Restaurant IDs sorted descending by global frequency.
    user_visited : set
        Restaurants this user visited in training data.
    k : int

    Returns
    -------
    list[int]  Top-K recommended restaurant IDs.
    """
    if strategy == "popularity":
        return recommend_popularity(user_id, global_popularity,
                                    user_visited, k)

    elif strategy in ("trust_basic", "trust_cosine"):
        return recommend_trust(user_id, graph, user_order_list, k)

    elif strategy in ("trust_full", "trust_location"):
        if user_order_weighted is None:
            raise ValueError(f"{strategy} requires user_order_weighted dict")
        return recommend_trust_full(user_id, graph,
                                    user_order_weighted, k)

    else:
        raise ValueError(f"Unknown strategy: {strategy}")


# ---------------------------------------------------------------------------
# Precision metric (kept here for backward compatibility)
# ---------------------------------------------------------------------------

def precision_at_k(recommended: list, actual: list, k: int = 5) -> float:
    """Proportion of top-K recommendations that appear in the actual set."""
    top_k = recommended[:k]
    hits = len(set(top_k) & set(actual))
    return hits / k