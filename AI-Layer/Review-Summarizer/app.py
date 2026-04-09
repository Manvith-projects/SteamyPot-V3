"""
app.py — FastAPI Server for Review Summarization
==================================================
Exposes the RAG review summarization pipeline as a REST API.

Endpoints:
  POST /summarize-reviews  — Summarize reviews for a restaurant
  GET  /health             — Health check
  GET  /restaurants        — List available restaurants

Architecture:
  ┌─────────┐     ┌──────────┐     ┌──────────────┐     ┌───────────┐     ┌─────────┐
  │ Client   │────▶│ FastAPI   │────▶│ MongoDB      │────▶│ Preprocess│────▶│ RAG     │
  │ (POST)   │     │ /summarize│     │ (reviews)    │     │ (clean)   │     │ Engine  │
  └─────────┘     └──────────┘     └──────────────┘     └───────────┘     └────┬────┘
                                                                               │
                                                          ┌────────────────────┘
                                                          ▼
                                                   ┌─────────────┐
                                                   │ FAISS Index  │
                                                   │ (embeddings) │
                                                   └──────┬──────┘
                                                          │ retrieve
                                                          ▼
                                                   ┌─────────────┐
                                                   │ Gemini LLM   │
                                                   │ (summarize)  │
                                                   └──────┬──────┘
                                                          │
                                                          ▼
                                                   ┌─────────────┐
                                                   │ JSON Summary │
                                                   └─────────────┘
"""

import os
import time
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Internal modules
from review_store import ReviewStore
from preprocessor import preprocess_reviews
from rag_engine import RAGEngine
from data_generator import seed_database, get_restaurant_list

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
ENABLE_NGROK_TESTING = os.getenv("ENABLE_NGROK_TESTING", "false").lower() == "true"
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "")


# ---------------------------------------------------------------------------
# Pydantic Models — Request / Response schemas
# ---------------------------------------------------------------------------

class SummarizeRequest(BaseModel):
    """Request body for POST /summarize-reviews."""
    restaurant_id: str = Field(
        ...,
        description="Unique restaurant identifier (e.g., 'rest_001')",
        examples=["rest_001"],
    )
    max_reviews: int = Field(
        default=200,
        description="Maximum number of reviews to analyze (after preprocessing)",
        ge=10,
        le=500,
    )


class PreprocessingStats(BaseModel):
    """Statistics from the review preprocessing step."""
    original_count: int
    duplicates_removed: int
    spam_removed: int
    after_cleaning: int
    final_count: int
    truncated: bool


class SummarizeResponse(BaseModel):
    """
    Response body for POST /summarize-reviews.

    Contains the AI-generated summary plus metadata about the
    restaurant and the preprocessing pipeline.
    """
    # ── Core summary (from RAG pipeline) ──
    summary: str = Field(description="2-4 sentence natural language summary")
    top_positive_points: list[str] = Field(description="Key positive feedback themes")
    common_complaints: list[str] = Field(description="Recurring customer complaints")
    overall_sentiment: str = Field(description="positive | mixed | negative | unknown")

    # ── Restaurant metadata ──
    restaurant_id: str
    restaurant_name: str
    average_rating: float
    rating_distribution: dict

    # ── Pipeline metadata ──
    preprocessing_stats: PreprocessingStats
    reviews_analyzed: int
    processing_time_ms: int


class HealthResponse(BaseModel):
    """Response body for GET /health."""
    status: str
    service: str
    mongodb_connected: bool
    llm_active: bool
    restaurants_in_db: int
    total_reviews: int


class RestaurantInfo(BaseModel):
    """Restaurant metadata for the /restaurants endpoint."""
    id: str
    name: str
    cuisine: str
    review_count: int
    average_rating: float


# ---------------------------------------------------------------------------
# Application Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup:
      1. Check if MongoDB has review data
      2. If empty, seed with synthetic reviews
      3. Initialize the RAG engine

    Shutdown:
      Close MongoDB connection.
    """
    print("\n" + "=" * 60)
    print("  AI Review Summarizer — Starting Up")
    print("=" * 60)

    # Initialize MongoDB store
    app.state.review_store = ReviewStore()

    if app.state.review_store.ping():
        print("[startup] MongoDB connection: OK")
    else:
        print("[startup] WARNING: MongoDB connection failed!")
        print("          Make sure MongoDB Atlas is accessible.")

    # Check if data exists; seed if empty
    existing_ids = app.state.review_store.get_all_restaurant_ids()
    if not existing_ids:
        print("[startup] No reviews found in MongoDB. Seeding synthetic data...")
        seed_database()
        existing_ids = app.state.review_store.get_all_restaurant_ids()
        print(f"[startup] Seeded reviews for {len(existing_ids)} restaurants.")
    else:
        print(f"[startup] Found existing reviews for {len(existing_ids)} restaurants.")

    # Initialize RAG engine
    app.state.rag_engine = RAGEngine()
    print(f"[startup] RAG Engine active: {app.state.rag_engine.is_active}")

    if not GOOGLE_API_KEY:
        print("[startup] WARNING: GOOGLE_API_KEY not set. LLM features disabled.")

    # Build restaurant lookup
    app.state.restaurant_lookup = {r["id"]: r for r in get_restaurant_list()}

    print(f"\n[startup] Ready! Serving {len(existing_ids)} restaurants.")
    print("=" * 60 + "\n")

    yield

    # Shutdown
    print("\n[shutdown] Closing MongoDB connection...")
    app.state.review_store.close()
    print("[shutdown] Done.")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Review Summarizer",
    description=(
        "RAG-powered restaurant review summarization.\n\n"
        "Uses Retrieval-Augmented Generation to analyze hundreds of reviews "
        "and produce a concise, structured summary with sentiment analysis."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Allow ngrok browser origins during explicit testing mode.
    allow_origin_regex=r"https://.*\.(ngrok-free\.app|ngrok\.io)" if ENABLE_NGROK_TESTING else None,
)


# ---------------------------------------------------------------------------
# POST /summarize-reviews — The main RAG endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/summarize-reviews",
    response_model=SummarizeResponse,
    summary="Summarize restaurant reviews using RAG",
    description=(
        "Retrieves reviews from MongoDB, preprocesses them (dedup + spam removal), "
        "creates embeddings, stores in FAISS, retrieves relevant chunks, and sends "
        "them to Gemini LLM for structured summarization."
    ),
)
async def summarize_reviews(request: SummarizeRequest):
    """
    Full RAG pipeline for review summarization.

    Steps:
      1. Fetch reviews from MongoDB for the given restaurant_id
      2. Preprocess: remove duplicates, filter spam, limit to max_reviews
      3. Embed review chunks using HuggingFace all-MiniLM-L6-v2 (free, local)
      4. Store embeddings in an ephemeral FAISS vector index
      5. Retrieve most relevant chunks via multi-query similarity search
      6. Send retrieved context to Gemini LLM for summary generation
      7. Return structured summary with sentiment analysis
    """
    start_time = time.time()

    store: ReviewStore = app.state.review_store
    rag: RAGEngine = app.state.rag_engine

    # ── Step 1: Validate restaurant_id ───────────────────────────────
    restaurant = app.state.restaurant_lookup.get(request.restaurant_id)
    if not restaurant:
        raise HTTPException(
            status_code=404,
            detail=f"Restaurant '{request.restaurant_id}' not found. "
                   f"Use GET /restaurants to see available IDs.",
        )

    # ── Step 2: Fetch reviews from MongoDB ───────────────────────────
    # We fetch up to 500 raw reviews (more than max_reviews) to allow
    # for losses during dedup + spam removal.
    raw_reviews = store.get_reviews(request.restaurant_id, limit=500)

    if not raw_reviews:
        raise HTTPException(
            status_code=404,
            detail=f"No reviews found for restaurant '{request.restaurant_id}'.",
        )

    # Get aggregated stats from MongoDB
    avg_rating = store.get_average_rating(request.restaurant_id)
    rating_dist = store.get_rating_distribution(request.restaurant_id)

    # ── Step 3: Preprocess reviews ───────────────────────────────────
    # Remove duplicates, filter spam, cap at max_reviews
    preprocessed = preprocess_reviews(raw_reviews, max_reviews=request.max_reviews)
    clean_reviews = preprocessed["clean_reviews"]
    stats = preprocessed["stats"]

    if not clean_reviews:
        raise HTTPException(
            status_code=422,
            detail="All reviews were filtered out during preprocessing (duplicates/spam).",
        )

    # ── Step 4-7: RAG Pipeline (embed → index → retrieve → generate) ─
    summary_result = await rag.summarize(
        restaurant_id=request.restaurant_id,
        reviews=clean_reviews,
        restaurant_name=restaurant["name"],
        avg_rating=avg_rating,
        rating_distribution=rating_dist,
        max_reviews=request.max_reviews,
    )

    processing_time = int((time.time() - start_time) * 1000)

    # ── Build response ───────────────────────────────────────────────
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
    )


# ---------------------------------------------------------------------------
# GET /health — Health check
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
)
async def health_check():
    """Check service health: MongoDB connectivity + LLM status."""
    store: ReviewStore = app.state.review_store
    rag: RAGEngine = app.state.rag_engine

    mongo_ok = store.ping()
    restaurant_ids = store.get_all_restaurant_ids() if mongo_ok else []

    total_reviews = 0
    if mongo_ok:
        for rid in restaurant_ids:
            total_reviews += store.get_review_count(rid)

    return HealthResponse(
        status="ok" if mongo_ok else "degraded",
        service="ai-review-summarizer",
        mongodb_connected=mongo_ok,
        llm_active=rag.is_active,
        restaurants_in_db=len(restaurant_ids),
        total_reviews=total_reviews,
    )


# ---------------------------------------------------------------------------
# GET /restaurants — List available restaurants
# ---------------------------------------------------------------------------

@app.get(
    "/restaurants",
    response_model=list[RestaurantInfo],
    summary="List restaurants with review data",
)
async def list_restaurants():
    """Return all restaurants with their review count and average rating."""
    store: ReviewStore = app.state.review_store
    restaurants = get_restaurant_list()

    result = []
    for r in restaurants:
        count = store.get_review_count(r["id"])
        avg = store.get_average_rating(r["id"]) if count > 0 else 0.0
        result.append(
            RestaurantInfo(
                id=r["id"],
                name=r["name"],
                cuisine=r["cuisine"],
                review_count=count,
                average_rating=avg,
            )
        )

    return result


# ---------------------------------------------------------------------------
# Run with uvicorn
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    ngrok_tunnel = None

    if ENABLE_NGROK_TESTING:
        try:
            from pyngrok import conf, ngrok

            if NGROK_AUTHTOKEN:
                conf.get_default().auth_token = NGROK_AUTHTOKEN

            ngrok_tunnel = ngrok.connect(addr=8001, bind_tls=True)
            public_url = ngrok_tunnel.public_url
            print(f"[testing] ngrok tunnel active: {public_url}")
            print(f"[testing] Swagger Docs: {public_url}/docs")
        except ImportError:
            print("[testing] pyngrok is not installed. Run: pip install pyngrok")
        except Exception as exc:
            print(f"[testing] Failed to start ngrok tunnel: {exc}")

    print("\nStarting AI Review Summarizer on http://0.0.0.0:8001")
    print("Docs: http://localhost:8001/docs\n")

    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8001,
            log_level="info",
        )
    finally:
        if ngrok_tunnel is not None:
            try:
                from pyngrok import ngrok
                ngrok.disconnect(ngrok_tunnel.public_url)
                ngrok.kill()
            except Exception:
                pass
