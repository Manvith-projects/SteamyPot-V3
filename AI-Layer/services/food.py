"""
Food Assistant Service Router
==============================
Wraps the Food-Assistant project as a FastAPI APIRouter.

Endpoint:  POST /api/food/assistant
"""
import os
import time
import threading
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import get_service_dir, safe_import

router = APIRouter(prefix="/api/food", tags=["Food Assistant"])

SERVICE_DIR = get_service_dir("Food-Assistant")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_db = None
_llm = None
_rank_results = None
_estimate_eta = None
_initialized = False
_error = None
_init_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
def init():
    global _db, _llm, _rank_results, _estimate_eta, _initialized, _error
    try:
        _cwd = os.getcwd()
        os.chdir(SERVICE_DIR)

        # Generate data if not present
        if not os.path.exists(os.path.join(SERVICE_DIR, "data", "restaurants.json")):
            dg = safe_import(SERVICE_DIR, "data_generator")
            data = dg.generate_database()
            dg.save_database(data)

        db_mod = safe_import(SERVICE_DIR, "database")
        _db = db_mod.FoodDatabase()

        llm_mod = safe_import(SERVICE_DIR, "llm_engine")
        _llm = llm_mod.LLMEngine()

        ranker_mod = safe_import(SERVICE_DIR, "ranker")
        _rank_results = ranker_mod.rank_results

        eta_mod = safe_import(SERVICE_DIR, "eta_predictor")
        _estimate_eta = eta_mod.estimate_eta

        _initialized = True
        os.chdir(_cwd)
        print(f"  [food] Loaded: {len(_db.restaurants)} restaurants, "
              f"{len(_db.menu_items)} items")
    except Exception as e:
        _error = str(e)
        try:
            os.chdir(_cwd)
        except Exception:
            pass
        print(f"  [food] FAILED: {e}")


def _ensure_initialized() -> bool:
    """Lazily initialize the service on first request if startup raced."""
    global _initialized
    if _initialized:
        return True

    with _init_lock:
        if _initialized:
            return True
        init()
        return _initialized


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class FoodRequest(BaseModel):
    query: str = Field(..., description="Natural language food query")
    user_lat: Optional[float] = Field(default=17.4486)
    user_lon: Optional[float] = Field(default=78.3908)


class FoodOption(BaseModel):
    restaurant_name: str
    restaurant_rating: float
    menu_item: str
    price: str
    cuisine: str
    diet_type: str
    distance: str
    estimated_delivery_time: str
    score: float
    tags: List[str] = []
    offer: Optional[str] = None


class FoodResponse(BaseModel):
    message: str
    intent: str
    extracted_params: dict
    results: List[FoodOption] = []
    total_candidates: int = 0
    processing_time_ms: int = 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/assistant", response_model=FoodResponse)
async def ai_food_assistant(req: FoodRequest):
    """Natural-language food search powered by LangChain + Gemini."""
    if not _ensure_initialized():
        raise HTTPException(503, f"Food assistant unavailable: {_error}")

    t0 = time.time()

    # Step 1: Intent detection + entity extraction
    params = await _llm.extract_query_params(req.query)
    intent = params.get("intent", "search_food")

    if intent == "greeting":
        elapsed = int((time.time() - t0) * 1000)
        return FoodResponse(
            message="Hello! I'm your AI food assistant. Tell me what you're craving!",
            intent=intent, extracted_params=params, processing_time_ms=elapsed,
        )

    if intent in ("general_question", "unclear"):
        elapsed = int((time.time() - t0) * 1000)
        return FoodResponse(
            message="I specialise in finding food! Try: 'Healthy dinner under 300' or 'Best pizza near Kondapur'.",
            intent=intent, extracted_params=params, processing_time_ms=elapsed,
        )

    # Step 1b: Offers intent
    if intent == "browse_offers":
        user_lat, user_lon = req.user_lat, req.user_lon
        mentioned_location = params.get("location")
        if mentioned_location:
            coords = _db.get_location_coords(mentioned_location)
            if coords:
                user_lat, user_lon = coords["lat"], coords["lon"]

        offer_candidates = _db.get_items_with_offers(user_lat=user_lat, user_lon=user_lon)

        if params.get("cuisine"):
            offer_candidates = [c for c in offer_candidates if params["cuisine"].lower() in c["item"]["cuisine"].lower()]
        if params.get("diet_type"):
            dt = params["diet_type"].lower()
            if dt in ("veg", "vegetarian"):
                offer_candidates = [c for c in offer_candidates if c["item"]["diet_type"] in ("veg", "vegan")]
            elif dt == "non-veg":
                offer_candidates = [c for c in offer_candidates if c["item"]["diet_type"] == "non-veg"]
            elif dt == "vegan":
                offer_candidates = [c for c in offer_candidates if c["item"]["diet_type"] == "vegan"]
        if params.get("price_limit"):
            offer_candidates = [c for c in offer_candidates if c["item"]["price"] <= params["price_limit"]]

        total_offers = len(offer_candidates)
        if not offer_candidates:
            elapsed = int((time.time() - t0) * 1000)
            return FoodResponse(
                message="No active offers matching your criteria right now.",
                intent=intent, extracted_params=params, total_candidates=0,
                processing_time_ms=elapsed,
            )

        top_offers = _rank_results(offer_candidates, specific_item=params.get("specific_item"), top_k=5)
        food_options = _build_food_options(top_offers)

        elapsed = int((time.time() - t0) * 1000)
        return FoodResponse(
            message=f"Found {total_offers} items with active offers! Here are the best deals:",
            intent=intent, extracted_params=params, results=food_options,
            total_candidates=total_offers, processing_time_ms=elapsed,
        )

    # Step 2: Resolve location
    user_lat, user_lon = req.user_lat, req.user_lon
    mentioned_location = params.get("location")
    if mentioned_location:
        coords = _db.get_location_coords(mentioned_location)
        if coords:
            user_lat, user_lon = coords["lat"], coords["lon"]

    # Step 3: Database filtering
    candidates = _db.search(
        price_limit=params.get("price_limit"),
        cuisine=params.get("cuisine"),
        diet_type=params.get("diet_type"),
        tags=params.get("tags"),
        meal_time=params.get("meal_time"),
        location=mentioned_location,
        user_lat=user_lat, user_lon=user_lon,
        max_distance_km=params.get("max_distance_km"),
    )
    total_candidates = len(candidates)

    if not candidates:
        candidates = _db.search(
            cuisine=params.get("cuisine"),
            diet_type=params.get("diet_type"),
            tags=params.get("tags"),
            user_lat=user_lat, user_lon=user_lon,
        )
        if not candidates:
            elapsed = int((time.time() - t0) * 1000)
            return FoodResponse(
                message="Sorry, no matching restaurants found. Try broadening your search.",
                intent=intent, extracted_params=params, total_candidates=0,
                processing_time_ms=elapsed,
            )

    # Step 4: Ranking
    top_results = _rank_results(candidates, specific_item=params.get("specific_item"), top_k=5)

    # Step 5: ETA + response
    food_options = _build_food_options(top_results)

    diet_str = params.get("diet_type", "")
    cuisine_str = params.get("cuisine", "")
    loc_str = f" near {mentioned_location}" if mentioned_location else ""
    price_str = f" under ₹{int(params['price_limit'])}" if params.get("price_limit") else ""
    desc_parts = [p for p in [diet_str, cuisine_str] if p]
    desc = " ".join(desc_parts) if desc_parts else "food"
    message = f"Found {total_candidates} options for {desc}{price_str}{loc_str}. Here are the top {len(food_options)} picks!"

    elapsed = int((time.time() - t0) * 1000)
    return FoodResponse(
        message=message, intent=intent, extracted_params=params,
        results=food_options, total_candidates=total_candidates,
        processing_time_ms=elapsed,
    )


def _build_food_options(results: list) -> List[FoodOption]:
    """Convert ranked results to FoodOption list."""
    options = []
    for r in results:
        rest = r["restaurant"]
        item = r["item"]
        dist = r.get("distance_km") or 0.0
        eta = _estimate_eta(distance_km=dist, avg_prep_time_min=rest["avg_prep_time"])

        offer_label = None
        if item.get("offer"):
            offer_label = item["offer"]["label"]
        elif rest.get("offer"):
            offer_label = rest["offer"]["label"]

        options.append(FoodOption(
            restaurant_name=rest["name"],
            restaurant_rating=rest["rating"],
            menu_item=item["name"],
            price=f"₹{item['price']}",
            cuisine=item["cuisine"],
            diet_type=item["diet_type"],
            distance=f"{dist:.1f} km" if dist else "N/A",
            estimated_delivery_time=f"{eta['eta_minutes']} min",
            score=r["score"],
            tags=item.get("tags", []),
            offer=offer_label,
        ))
    return options


@router.get("/health")
async def health():
    return {
        "status": "ok" if _initialized else "unavailable",
        "service": "food-assistant",
        "restaurants": len(_db.restaurants) if _db else 0,
        "menu_items": len(_db.menu_items) if _db else 0,
        "llm_active": _llm.chain is not None if _llm else False,
        "error": _error,
    }
