"""
app.py  --  FastAPI Server for AI Food Assistant
=================================================
Serves the AI food assistant as a REST API.

Architecture
------------
  User query (natural language)
      ↓  POST /ai-food-assistant
  1. LLM Engine  → extract intent + entities (LangChain + Gemini)
      ↓
  2. Database    → filter restaurants/items by extracted params
      ↓
  3. Ranker      → score & rank candidates (ML ranking model)
      ↓
  4. ETA         → predict delivery time per result
      ↓
  5. Response    → top-5 recommendations as JSON

AI Concept: ML Microservice Pattern
-------------------------------------
Each AI component (LLM, recommender, ETA) is a separate module with
a clean interface.  This follows the "ML microservice" pattern:
  * Each model can be updated independently.
  * Each component can be tested and monitored separately.
  * The orchestrator (this file) handles composition and error handling.

CORS is enabled for the React frontend to call from localhost:5173.
"""

import os
import time
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Local modules
from database import FoodDatabase
from llm_engine import LLMEngine
from ranker import rank_results
from eta_predictor import estimate_eta

# ---------------------------------------------------------------------------
# Pydantic models for request / response
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """
    User chat message.

    AI Concept: Structured API Contract
    ------------------------------------
    The API accepts free-text queries but can also accept
    optional user_lat/lon for personalised distance-based ranking.
    """
    query: str = Field(..., description="Natural language food query")
    user_lat: Optional[float] = Field(default=17.4486, description="User latitude (default: Madhapur)")
    user_lon: Optional[float] = Field(default=78.3908, description="User longitude (default: Madhapur)")


class FoodOption(BaseModel):
    """Single recommended food option."""
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
    offer: Optional[str] = None          # e.g. "20% OFF", "Buy 1 Get 1 Free"


class ChatResponse(BaseModel):
    """
    Full response to user query.

    AI Concept: Explainable AI (XAI)
    ---------------------------------
    We return not just the results but also the extracted_params
    (what the LLM understood) and a natural-language message.
    This transparency helps users understand why they got these
    results and correct any misunderstandings ("I said veg, not non-veg").
    """
    message: str
    intent: str
    extracted_params: dict
    results: List[FoodOption] = []
    total_candidates: int = 0
    processing_time_ms: int = 0


# ---------------------------------------------------------------------------
# Lifespan: init database + LLM on startup
# ---------------------------------------------------------------------------

db: Optional[FoodDatabase] = None
llm: Optional[LLMEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown lifecycle.

    AI Concept: Model Loading at Startup
    -------------------------------------
    LLM connections and database indexes are initialized once at
    server startup, not per-request.  This ensures:
      * First request is fast (no cold-start).
      * Memory is allocated predictably.
      * Connection pools are reused.
    """
    global db, llm

    # Generate data if not present
    if not os.path.exists("data/restaurants.json"):
        print("[app] Generating database...")
        from data_generator import generate_database, save_database
        data = generate_database()
        save_database(data)

    db = FoodDatabase()
    print(f"[app] Database loaded: {len(db.restaurants)} restaurants, {len(db.menu_items)} menu items")

    llm = LLMEngine()
    print("[app] LLM engine ready.")

    yield
    print("[app] Shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Food Assistant",
    description="Natural language food search powered by LangChain + Gemini",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for React frontend (Vite default port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# POST /ai-food-assistant
# ---------------------------------------------------------------------------

@app.post("/ai-food-assistant", response_model=ChatResponse)
async def ai_food_assistant(req: ChatRequest):
    """
    Main AI food assistant endpoint.

    AI Concept: End-to-End ML Pipeline
    ------------------------------------
    This endpoint orchestrates the full pipeline:
      1. NLU (intent + entity extraction via LLM)
      2. Candidate generation (database filtering)
      3. Ranking (multi-signal scoring)
      4. ETA prediction
      5. Response formatting

    Each step has a clear input→output contract, making the
    pipeline debuggable and testable.
    """
    t0 = time.time()

    # ------------------------------------------------------------------
    # Step 1: Intent detection + entity extraction (LLM / rules)
    # ------------------------------------------------------------------
    # AI Concept: NLU (Natural Language Understanding)
    # The LLM reads the free-text query and outputs structured fields.
    # This is the most "AI-heavy" step -- everything downstream is
    # deterministic given the extracted params.
    params = await llm.extract_query_params(req.query)
    intent = params.get("intent", "search_food")

    # Handle non-food intents
    if intent == "greeting":
        elapsed = int((time.time() - t0) * 1000)
        return ChatResponse(
            message="Hello! 👋 I'm your AI food assistant. Tell me what you're craving — for example: 'Show me spicy biryani under ₹400 near Madhapur'",
            intent=intent,
            extracted_params=params,
            processing_time_ms=elapsed,
        )

    if intent in ("general_question", "unclear"):
        elapsed = int((time.time() - t0) * 1000)
        return ChatResponse(
            message="I specialise in finding food for you! Try something like: 'Healthy dinner under ₹300' or 'Best pizza near Kondapur'.",
            intent=intent,
            extracted_params=params,
            processing_time_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # Step 1b: Handle offers / deals intent
    # ------------------------------------------------------------------
    if intent == "browse_offers":
        user_lat = req.user_lat
        user_lon = req.user_lon

        mentioned_location = params.get("location")
        if mentioned_location:
            coords = db.get_location_coords(mentioned_location)
            if coords:
                user_lat = coords["lat"]
                user_lon = coords["lon"]

        offer_candidates = db.get_items_with_offers(
            user_lat=user_lat,
            user_lon=user_lon,
        )

        # Apply optional filters (cuisine, diet, price) even to offers
        if params.get("cuisine"):
            offer_candidates = [
                c for c in offer_candidates
                if params["cuisine"].lower() in c["item"]["cuisine"].lower()
            ]
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
            return ChatResponse(
                message="No active offers right now matching your criteria. Try searching for food directly!",
                intent=intent,
                extracted_params=params,
                total_candidates=0,
                processing_time_ms=elapsed,
            )

        # Rank offer candidates and pick top 5
        top_offers = rank_results(offer_candidates, specific_item=params.get("specific_item"), top_k=5)

        food_options = []
        for r in top_offers:
            rest = r["restaurant"]
            item = r["item"]
            dist = r.get("distance_km") or 0.0
            eta = estimate_eta(distance_km=dist, avg_prep_time_min=rest["avg_prep_time"])

            # Offer label: prefer item-level, fallback to restaurant-level
            offer_label = None
            if item.get("offer"):
                offer_label = item["offer"]["label"]
            elif rest.get("offer"):
                offer_label = rest["offer"]["label"]

            food_options.append(FoodOption(
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

        elapsed = int((time.time() - t0) * 1000)
        return ChatResponse(
            message=f"🎉 Found {total_offers} items with active offers! Here are the best deals for you:",
            intent=intent,
            extracted_params=params,
            results=food_options,
            total_candidates=total_offers,
            processing_time_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # Step 2: Resolve user location
    # ------------------------------------------------------------------
    # AI Concept: Geospatial Context
    # If the user mentions a location name (e.g., "Kukatpally"), we
    # look up its coordinates.  If they provide lat/lon directly, we
    # use that.  Location is critical for distance-based ranking.
    user_lat = req.user_lat
    user_lon = req.user_lon

    mentioned_location = params.get("location")
    if mentioned_location:
        coords = db.get_location_coords(mentioned_location)
        if coords:
            user_lat = coords["lat"]
            user_lon = coords["lon"]

    # ------------------------------------------------------------------
    # Step 3: Database filtering (candidate generation)
    # ------------------------------------------------------------------
    # AI Concept: Candidate Generation
    # Apply hard filters to narrow the full catalog to matching items.
    # This is fast (O(n) scan) and deterministic.
    candidates = db.search(
        price_limit=params.get("price_limit"),
        cuisine=params.get("cuisine"),
        diet_type=params.get("diet_type"),
        tags=params.get("tags"),
        meal_time=params.get("meal_time"),
        location=mentioned_location,
        user_lat=user_lat,
        user_lon=user_lon,
        max_distance_km=params.get("max_distance_km"),
    )

    total_candidates = len(candidates)

    if not candidates:
        # Retry with relaxed filters (remove price limit)
        candidates = db.search(
            cuisine=params.get("cuisine"),
            diet_type=params.get("diet_type"),
            tags=params.get("tags"),
            user_lat=user_lat,
            user_lon=user_lon,
        )
        if not candidates:
            elapsed = int((time.time() - t0) * 1000)
            return ChatResponse(
                message="Sorry, I couldn't find any matching restaurants. Try broadening your search — for example, remove the price limit or try a different area.",
                intent=intent,
                extracted_params=params,
                total_candidates=0,
                processing_time_ms=elapsed,
            )

    # ------------------------------------------------------------------
    # Step 4: Smart ranking
    # ------------------------------------------------------------------
    # AI Concept: Learning-to-Rank (simplified)
    # Score each candidate using a weighted combination of:
    #   recommendation_score, rating, distance, price, item_match
    # Then apply diversity filter (1 item per restaurant).
    top_results = rank_results(
        candidates,
        specific_item=params.get("specific_item"),
        top_k=5,
    )

    # ------------------------------------------------------------------
    # Step 5: ETA prediction for each result
    # ------------------------------------------------------------------
    # AI Concept: Delivery Time Estimation
    # For each ranked result, predict how long delivery will take.
    # This is the last feature the user sees and often determines
    # their final choice.
    food_options = []
    for r in top_results:
        rest = r["restaurant"]
        item = r["item"]
        dist = r.get("distance_km") or 0.0

        eta = estimate_eta(
            distance_km=dist,
            avg_prep_time_min=rest["avg_prep_time"],
        )

        food_options.append(FoodOption(
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
            offer=item.get("offer", {}).get("label") if item.get("offer") else (
                rest.get("offer", {}).get("label") if rest.get("offer") else None
            ),
        ))

    # ------------------------------------------------------------------
    # Step 6: Generate natural language response message
    # ------------------------------------------------------------------
    diet_str = params.get("diet_type", "")
    cuisine_str = params.get("cuisine", "")
    loc_str = f" near {mentioned_location}" if mentioned_location else ""
    price_str = f" under ₹{int(params['price_limit'])}" if params.get("price_limit") else ""

    desc_parts = [p for p in [diet_str, cuisine_str] if p]
    desc = " ".join(desc_parts) if desc_parts else "food"

    message = f"Found {total_candidates} options for {desc}{price_str}{loc_str}. Here are the top {len(food_options)} picks for you! 🍽️"

    elapsed = int((time.time() - t0) * 1000)

    return ChatResponse(
        message=message,
        intent=intent,
        extracted_params=params,
        results=food_options,
        total_candidates=total_candidates,
        processing_time_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "ai-food-assistant",
        "restaurants": len(db.restaurants) if db else 0,
        "menu_items": len(db.menu_items) if db else 0,
        "llm_active": llm.chain is not None if llm else False,
    }


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
