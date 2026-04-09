"""
Recommendation Engine Service Router
======================================
Wraps the Recommendation_Engine project as a FastAPI APIRouter.

Endpoint:  GET /api/recommend/{user_id}
"""
import os
import asyncio
import numpy as np
import pandas as pd
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from services import get_service_dir, safe_import

router = APIRouter(prefix="/api/recommend", tags=["Recommendation Engine"])

SERVICE_DIR = get_service_dir("Recommendation_Engine")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_graph = None
_orders_df = None
_restaurants_df = None
_users_df = None
_user_order_list = None
_user_order_weighted = None
_global_popularity = None
_user_visited_map = None
_recommend_fn = None
_initialized = False
_error = None


# ---------------------------------------------------------------------------
# Init  (lightweight — only loads CSV + imports; graph built lazily)
# ---------------------------------------------------------------------------
_gb_mod = None
_rec_mod = None
_graph_ready = False


def init():
    global _orders_df, _restaurants_df, _users_df
    global _user_order_list, _global_popularity, _user_visited_map
    global _recommend_fn, _gb_mod, _rec_mod
    global _initialized, _error

    try:
        _cwd = os.getcwd()
        os.chdir(SERVICE_DIR)

        _orders_df = pd.read_csv(os.path.join(SERVICE_DIR, "orders.csv"))
        _restaurants_df = pd.read_csv(os.path.join(SERVICE_DIR, "restaurants.csv"))
        users_path = os.path.join(SERVICE_DIR, "users.csv")
        if os.path.exists(users_path):
            _users_df = pd.read_csv(users_path)

        _gb_mod = safe_import(SERVICE_DIR, "graph_builder")
        _rec_mod = safe_import(SERVICE_DIR, "recommender")
        _recommend_fn = _rec_mod.recommend

        # Precompute auxiliary data structures (vectorised — fast)
        _user_order_list = defaultdict(list)
        for uid, rid in zip(_orders_df["user_id"].values, _orders_df["restaurant_id"].values):
            _user_order_list[int(uid)].append(int(rid))

        pop_counts = _orders_df["restaurant_id"].value_counts()
        _global_popularity = pop_counts.index.tolist()

        _user_visited_map = {}
        for uid, rids in _user_order_list.items():
            _user_visited_map[uid] = set(rids)

        _initialized = True
        os.chdir(_cwd)
        print(f"  [recommend] Loaded: {len(_orders_df)} orders, "
              f"{len(_restaurants_df)} restaurants, "
              f"{len(_user_order_list)} users  (graph built on first request)")
    except Exception as e:
        _error = str(e)
        try:
            os.chdir(_cwd)
        except Exception:
            pass
        print(f"  [recommend] FAILED: {e}")


def _ensure_graph():
    """Build the social graph lazily on first recommendation request."""
    global _graph, _graph_ready, _user_order_weighted
    if _graph_ready:
        return
    print("  [recommend] Building social graph (one-time, may take a moment)...")
    import time
    t0 = time.time()
    _graph = _gb_mod.build_social_graph(_orders_df)
    _user_order_weighted = None
    _graph_ready = True
    elapsed = round(time.time() - t0, 1)
    print(f"  [recommend] Graph ready: {_graph.number_of_nodes()} nodes, "
          f"{_graph.number_of_edges()} edges ({elapsed}s)")


async def _ensure_graph_async():
    """Run the blocking graph build in a thread pool so it doesn't block the event loop."""
    if _graph_ready:
        return
    await asyncio.to_thread(_ensure_graph)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/{user_id}")
async def get_recommendations(
    user_id: int,
    strategy: str = Query(default="trust_basic",
                          description="popularity | trust_basic | trust_cosine | trust_full"),
    k: int = Query(default=5, ge=1, le=20),
):
    """Get restaurant recommendations for a user."""
    if not _initialized:
        await asyncio.to_thread(init)

    if not _initialized:
        return {
            "user_id": user_id,
            "strategy": "fallback_unavailable",
            "requested_strategy": strategy,
            "recommendations": [],
            "count": 0,
            "unavailable_reason": _error,
        }

    requested_strategy = strategy

    # Only build the expensive social graph for trust-based strategies
    if strategy != "popularity":
        await _ensure_graph_async()

    user_visited = _user_visited_map.get(user_id, set())

    # Cold-start / sparse-user handling for production users:
    # if user has no history OR no trust neighbours, fallback to popularity.
    if strategy != "popularity":
        no_history = len(user_visited) == 0
        no_neighbours = (_graph is None) or (user_id not in _graph) or (_graph.degree(user_id) == 0)
        if no_history or no_neighbours:
            strategy = "popularity"

    try:
        recs = _recommend_fn(
            user_id=user_id,
            strategy=strategy,
            graph=_graph,
            user_order_list=dict(_user_order_list),
            user_order_weighted=_user_order_weighted,
            global_popularity=_global_popularity,
            user_visited=user_visited,
            k=k,
        )

        if not recs and strategy != "popularity":
            # Secondary fallback: if trust mode returns no candidates,
            # fall back to popularity instead of empty response.
            recs = _recommend_fn(
                user_id=user_id,
                strategy="popularity",
                graph=_graph,
                user_order_list=dict(_user_order_list),
                user_order_weighted=_user_order_weighted,
                global_popularity=_global_popularity,
                user_visited=user_visited,
                k=k,
            )
            strategy = "popularity"

        # Enrich with restaurant info after final recommendation list is ready.
        rest_map = {int(r["restaurant_id"]): r for _, r in _restaurants_df.iterrows()}
        enriched = []
        for rid in recs:
            info = rest_map.get(rid, {})
            enriched.append({
                "restaurant_id": rid,
                "name": info.get("name", f"Restaurant {rid}"),
                "zone": info.get("zone", "Unknown"),
                "rating": float(info.get("rating", 0)),
            })

        return {
            "user_id": user_id,
            "strategy": strategy,
            "requested_strategy": requested_strategy,
            "recommendations": enriched,
            "count": len(enriched),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        return {
            "user_id": user_id,
            "strategy": "fallback_error",
            "requested_strategy": requested_strategy,
            "recommendations": [],
            "count": 0,
            "unavailable_reason": str(e),
        }


@router.get("/")
async def list_users(limit: int = Query(default=20, ge=1, le=100)):
    """List available user IDs for testing."""
    if not _initialized:
        await asyncio.to_thread(init)

    if not _initialized:
        return {
            "users": [],
            "total_users": 0,
            "total_restaurants": 0,
            "unavailable_reason": _error,
        }

    user_ids = sorted(_orders_df["user_id"].unique().tolist())
    return {
        "users": user_ids[:limit],
        "total_users": len(user_ids),
        "total_restaurants": len(_restaurants_df),
    }


@router.get("/health", tags=["Health"])
async def health():
    return {
        "status": "ok" if _initialized else "unavailable",
        "service": "recommendation-engine",
        "users": len(_user_order_list) if _user_order_list else 0,
        "graph_built": _graph_ready,
        "graph_nodes": _graph.number_of_nodes() if _graph and _graph_ready else 0,
        "graph_edges": _graph.number_of_edges() if _graph and _graph_ready else 0,
        "error": _error,
    }
