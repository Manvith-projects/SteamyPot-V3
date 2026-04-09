"""
Review Summarizer Service Router
==================================
Wraps the Review-Summarizer project as a FastAPI APIRouter.

Endpoints:
  POST /api/review/summarize
  GET  /api/review/restaurants
"""
import os
import time
import asyncio
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from services import get_service_dir, safe_import

router = APIRouter(prefix="/api/review", tags=["Review Summarizer"])

SERVICE_DIR = get_service_dir("Review-Summarizer")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_review_store = None
_rag_engine = None
_preprocess_fn = None
_restaurant_lookup = {}
_restaurant_list_fn = None
_main_app_bridge = None
_is_objectid_fn = None
_cache_warmup_status = {"state": "idle", "last_run": None, "built": 0, "reused": 0}
_initialized = False
_error = None


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
def init():
    global _review_store, _rag_engine, _preprocess_fn
    global _restaurant_lookup, _restaurant_list_fn
    global _main_app_bridge, _is_objectid_fn
    global _initialized, _error

    try:
        _cwd = os.getcwd()
        os.chdir(SERVICE_DIR)

        rs_mod = safe_import(SERVICE_DIR, "review_store")
        pp_mod = safe_import(SERVICE_DIR, "preprocessor")
        rag_mod = safe_import(SERVICE_DIR, "rag_engine")
        dg_mod = safe_import(SERVICE_DIR, "data_generator")

        _review_store = rs_mod.ReviewStore()
        _preprocess_fn = pp_mod.preprocess_reviews
        _restaurant_list_fn = dg_mod.get_restaurant_list
        _is_objectid_fn = rs_mod.is_objectid

        # Bridge to the main app's reviews collection
        try:
            _main_app_bridge = rs_mod.MainAppReviewBridge()
            if _main_app_bridge.ping():
                print("  [review] Main app bridge: OK")
            else:
                print("  [review] Main app bridge: connection failed")
                _main_app_bridge = None
        except Exception as be:
            print(f"  [review] Main app bridge skipped: {be}")
            _main_app_bridge = None

        if _review_store.ping():
            existing_ids = _review_store.get_all_restaurant_ids()
            if not existing_ids:
                print("  [review] Seeding MongoDB with synthetic reviews...")
                dg_mod.seed_database()
                existing_ids = _review_store.get_all_restaurant_ids()
            print(f"  [review] MongoDB OK: {len(existing_ids)} restaurants")
        else:
            print("  [review] WARNING: MongoDB connection failed")

        _rag_engine = rag_mod.RAGEngine()
        _restaurant_lookup = {r["id"]: r for r in _restaurant_list_fn()}
        _start_daily_cache_warmup()

        _initialized = True
        os.chdir(_cwd)
        print(f"  [review] RAG engine active: {_rag_engine.is_active}")
    except Exception as e:
        _error = str(e)
        try:
            os.chdir(_cwd)
        except Exception:
            pass
        print(f"  [review] FAILED: {e}")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class SummarizeRequest(BaseModel):
    restaurant_id: str = Field(..., examples=["rest_001"])
    max_reviews: int = Field(default=200, ge=10, le=500)


class PreprocessingStats(BaseModel):
    original_count: int
    duplicates_removed: int
    spam_removed: int
    after_cleaning: int
    final_count: int
    truncated: bool


class SummarizeResponse(BaseModel):
    summary: str
    top_positive_points: list[str]
    common_complaints: list[str]
    overall_sentiment: str
    restaurant_id: str
    restaurant_name: str
    average_rating: float
    rating_distribution: dict
    preprocessing_stats: PreprocessingStats
    reviews_analyzed: int
    processing_time_ms: int
    cache_status: Optional[str] = None
    cache_refreshed_at: Optional[str] = None
    cache_age_hours: Optional[float] = None
    summary_cache_status: Optional[str] = None
    summary_cache_refreshed_at: Optional[str] = None
    summary_cache_age_hours: Optional[float] = None


class RestaurantInfo(BaseModel):
    id: str
    name: str
    cuisine: str
    review_count: int
    average_rating: float


def _build_cache_entries():
    entries = []
    warnings = []

    try:
        for restaurant in _restaurant_list_fn() or []:
            raw_reviews = _review_store.get_reviews(restaurant["id"], limit=500)
            preprocessed = _preprocess_fn(raw_reviews, max_reviews=200)
            clean_reviews = preprocessed["clean_reviews"]
            if clean_reviews:
                entries.append({
                    "restaurant_id": restaurant["id"],
                    "restaurant_name": restaurant["name"],
                    "reviews": clean_reviews,
                })
    except Exception as exc:
        warnings.append(f"synthetic-db: {exc}")

    if _main_app_bridge:
        try:
            for shop in _main_app_bridge.get_reviewed_shops():
                raw_reviews = _main_app_bridge.get_reviews(shop["id"], limit=500)
                preprocessed = _preprocess_fn(raw_reviews, max_reviews=200)
                clean_reviews = preprocessed["clean_reviews"]
                if clean_reviews:
                    entries.append({
                        "restaurant_id": shop["id"],
                        "restaurant_name": shop["name"],
                        "reviews": clean_reviews,
                    })
        except Exception as exc:
            warnings.append(f"main-app-db: {exc}")

    return entries, warnings


def _start_daily_cache_warmup():
    def _runner():
        global _cache_warmup_status
        _cache_warmup_status = {"state": "running", "last_run": None, "built": 0, "reused": 0}
        try:
            entries, warnings = _build_cache_entries()
            
            # Run asyncio with timeout to prevent indefinite hanging
            import signal
            
            def _timeout_handler(signum, frame):
                raise TimeoutError("Cache warmup timeout after 10 seconds")
            
            try:
                # For Windows and non-signal-based timeout, use a custom wrapper
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, _rag_engine.prime_cache_entries(entries))
                    result = future.result(timeout=10)  # Wait max 10 seconds
            except Exception as timeout_exc:
                print(f"  [review] Cache warmup timeout: {timeout_exc}")
                result = {"built": 0, "reused": 0}
            
            state = "completed_with_warnings" if warnings else "completed"
            _cache_warmup_status = {
                "state": state,
                "last_run": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "built": result.get("built", 0),
                "reused": result.get("reused", 0),
                "warnings": warnings,
            }
            if warnings:
                print(f"  [review] Daily vector warmup partial: {result.get('built', 0)} built, {result.get('reused', 0)} reused, warnings={len(warnings)}")
            else:
                print(f"  [review] Daily vector warmup complete: {result.get('built', 0)} built, {result.get('reused', 0)} reused")
        except Exception as exc:
            _cache_warmup_status = {
                "state": "failed",
                "last_run": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "built": 0,
                "reused": 0,
                "warnings": [str(exc)],
            }
            print(f"  [review] Daily vector warmup failed: {exc}")

    threading.Thread(target=_runner, daemon=True, name="review-vector-warmup").start()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_reviews(request: SummarizeRequest):
    """Summarize restaurant reviews using RAG pipeline."""
    if not _initialized:
        await asyncio.to_thread(init)

    if not _initialized:
        return SummarizeResponse(
            summary="Review service is warming up. Please retry shortly.",
            top_positive_points=[],
            common_complaints=[],
            overall_sentiment="unknown",
            restaurant_id=request.restaurant_id,
            restaurant_name="Unknown Restaurant",
            average_rating=0.0,
            rating_distribution={},
            preprocessing_stats=PreprocessingStats(
                original_count=0,
                duplicates_removed=0,
                spam_removed=0,
                after_cleaning=0,
                final_count=0,
                truncated=False,
            ),
            reviews_analyzed=0,
            processing_time_ms=0,
        )

    start_time = time.time()
    rid = request.restaurant_id
    use_bridge = False

    restaurant = _restaurant_lookup.get(rid)

    # If not found in synthetic data, try main app bridge for real shop ObjectIds
    if not restaurant and _main_app_bridge and _is_objectid_fn and _is_objectid_fn(rid):
        shop_info = _main_app_bridge.get_shop_info(rid)
        if shop_info:
            restaurant = shop_info
            use_bridge = True

    if not restaurant:
        raise HTTPException(404,
            f"Restaurant '{rid}' not found. Use GET /api/review/restaurants.")

    store = _main_app_bridge if use_bridge else _review_store
    raw_reviews = store.get_reviews(rid, limit=500)
    if not raw_reviews:
        raise HTTPException(404, f"No reviews found for '{rid}'.")

    avg_rating = store.get_average_rating(rid)
    rating_dist = store.get_rating_distribution(rid)

    preprocessed = _preprocess_fn(raw_reviews, max_reviews=request.max_reviews)
    clean_reviews = preprocessed["clean_reviews"]
    stats = preprocessed["stats"]

    if not clean_reviews:
        raise HTTPException(422, "All reviews were filtered out during preprocessing.")

    try:
        summary_result = await _rag_engine.summarize(
            restaurant_id=rid,
            reviews=clean_reviews,
            restaurant_name=restaurant["name"],
            avg_rating=avg_rating,
            rating_distribution=rating_dist,
            max_reviews=request.max_reviews,
        )
    except Exception:
        summary_result = {
            "summary": "AI summarization is temporarily unavailable. Showing basic review stats only.",
            "top_positive_points": [],
            "common_complaints": [],
            "overall_sentiment": "unknown",
        }

    processing_time = int((time.time() - start_time) * 1000)

    return SummarizeResponse(
        summary=summary_result["summary"],
        top_positive_points=summary_result["top_positive_points"],
        common_complaints=summary_result["common_complaints"],
        overall_sentiment=summary_result["overall_sentiment"],
        restaurant_id=request.restaurant_id,
        restaurant_name=restaurant["name"],
        average_rating=avg_rating,
        rating_distribution=rating_dist,
        preprocessing_stats=PreprocessingStats(**stats),
        reviews_analyzed=stats["final_count"],
        processing_time_ms=processing_time,
        cache_status=summary_result.get("cache_status"),
        cache_refreshed_at=summary_result.get("cache_refreshed_at"),
        cache_age_hours=summary_result.get("cache_age_hours"),
        summary_cache_status=summary_result.get("summary_cache_status"),
        summary_cache_refreshed_at=summary_result.get("summary_cache_refreshed_at"),
        summary_cache_age_hours=summary_result.get("summary_cache_age_hours"),
    )


@router.get("/restaurants", response_model=list[RestaurantInfo])
async def list_restaurants():
    """List all restaurants with review data."""
    if not _initialized:
        await asyncio.to_thread(init)

    if not _initialized:
        return []

    restaurants = _restaurant_list_fn()
    result = []
    for r in restaurants:
        count = _review_store.get_review_count(r["id"])
        avg = _review_store.get_average_rating(r["id"]) if count > 0 else 0.0
        result.append(RestaurantInfo(
            id=r["id"], name=r["name"], cuisine=r["cuisine"],
            review_count=count, average_rating=avg,
        ))
    return result


@router.get("/health")
async def health():
    mongo_ok = _review_store.ping() if _review_store else False
    return {
        "status": "ok" if _initialized else "unavailable",
        "service": "review-summarizer",
        "mongodb_connected": mongo_ok,
        "rag_active": _rag_engine.is_active if _rag_engine else False,
        "vector_cache": _cache_warmup_status,
        "error": _error,
    }
