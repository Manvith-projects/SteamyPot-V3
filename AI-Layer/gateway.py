"""
=============================================================================
  AI-Layer Unified Gateway
=============================================================================
  Single FastAPI server that exposes ALL AI microservices on one port.

  Port: 9000
  Docs: http://localhost:9000/docs

  Services:
  ─────────────────────────────────────────────────────────────────
  Prefix                 │ Service                │ Key Endpoint
  ─────────────────────────────────────────────────────────────────
  /api/churn             │ Churn Prediction       │ POST /predict
  /api/driver            │ Driver Allocation      │ POST /allocate
  /api/pricing           │ Dynamic Pricing        │ POST /calculate
  /api/eta               │ ETA Predictor          │ POST /predict
  /api/food              │ AI Food Assistant      │ POST /assistant
  /api/recommend         │ Recommendation Engine  │ GET  /{user_id}
  /api/recovery          │ Recovery Agent         │ POST /agent
  /api/review            │ Review Summarizer      │ POST /summarize
  ─────────────────────────────────────────────────────────────────

  Architecture:
  ┌─────────────────────────────────────────────────────────────┐
  │                    FastAPI Gateway (:9000)                   │
  │                                                             │
  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
  │  │  Churn   │ │ Driver  │ │ Pricing │ │   ETA   │          │
  │  │ Router   │ │ Router  │ │ Router  │ │ Router  │          │
  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘          │
  │       │           │           │           │                │
  │  ┌────┴────┐ ┌────┴────┐ ┌────┴────┐ ┌────┴────┐          │
  │  │  Food   │ │ Recomm  │ │Recovery │ │ Review  │          │
  │  │ Router  │ │ Router  │ │ Router  │ │ Router  │          │
  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
  │                                                             │
  │  Each router imports business logic from its project        │
  │  folder (Churn-Prediction/, Driver-Allocation/, etc.)       │
  │  Models & data load lazily at startup.                      │
  └─────────────────────────────────────────────────────────────┘
"""

import os
import sys
import time
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure the AI-Layer root is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Set env vars
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Import routers
from services.churn import router as churn_router, init as init_churn
from services.driver import router as driver_router, init as init_driver
from services.pricing import router as pricing_router, init as init_pricing
from services.eta import router as eta_router, init as init_eta
from services.food import router as food_router, init as init_food
from services.recommend import router as recommend_router, init as init_recommend
from services.recovery import router as recovery_router, init as init_recovery
from services.review import router as review_router, init as init_review


# ---------------------------------------------------------------------------
# Service Registry
# ---------------------------------------------------------------------------
SERVICES = [
    {"name": "Churn Prediction",      "prefix": "/api/churn",     "init": init_churn,     "router": churn_router},
    {"name": "Driver Allocation",     "prefix": "/api/driver",    "init": init_driver,    "router": driver_router},
    {"name": "Dynamic Pricing",       "prefix": "/api/pricing",   "init": init_pricing,   "router": pricing_router},
    {"name": "ETA Predictor",         "prefix": "/api/eta",       "init": init_eta,       "router": eta_router},
    {"name": "Food Assistant",        "prefix": "/api/food",      "init": init_food,      "router": food_router},
    {"name": "Recommendation Engine", "prefix": "/api/recommend", "init": init_recommend, "router": recommend_router},
    {"name": "Recovery Agent",        "prefix": "/api/recovery",  "init": init_recovery,  "router": recovery_router},
    {"name": "Review Summarizer",     "prefix": "/api/review",    "init": init_review,    "router": review_router},
]

_service_status = {}


async def _initialize_services() -> None:
    """Initialize AI services in the background to avoid blocking port bind."""
    print("\n" + "=" * 60)
    print("  AI-Layer Unified Gateway — Background Initialization")
    print("=" * 60 + "\n")

    t0 = time.time()
    for svc in SERVICES:
        name = svc["name"]
        print(f"  Initializing {name}...")
        try:
            # Review Summarizer needs more time to load sentence-transformers model
            timeout_secs = 60.0 if name == "Review Summarizer" else 30.0
            # Run init with timeout to prevent indefinite hanging
            await asyncio.wait_for(asyncio.to_thread(svc["init"]), timeout=timeout_secs)
            _service_status[name] = "ok"
        except asyncio.TimeoutError:
            _service_status[name] = f"timeout ({int(timeout_secs)}s)"
            print(f"  x {name} timeout after {int(timeout_secs)} seconds")
        except Exception as e:
            _service_status[name] = f"error: {e}"
            print(f"  x {name} failed: {e}")

    elapsed = round(time.time() - t0, 1)
    ok_count = sum(1 for v in _service_status.values() if v == "ok")
    total = len(SERVICES)
    print(f"\n{'=' * 60}")
    print(f"  Initialization complete: {ok_count}/{total} services ready ({elapsed}s)")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Lifespan — initialize all services at startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    for svc in SERVICES:
        _service_status[svc["name"]] = "initializing"

    init_task = asyncio.create_task(_initialize_services())
    app.state.init_task = init_task

    print("\n" + "=" * 60)
    print("  AI-Layer Unified Gateway — Starting Up")
    print("=" * 60 + "\n")
    print("  Gateway listening while services initialize in background")

    yield

    if hasattr(app.state, "init_task") and not app.state.init_task.done():
        app.state.init_task.cancel()

    print("\n[gateway] Shutting down...")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI-Layer Unified Gateway",
    description=(
        "Single server exposing all AI microservices for the food delivery platform.\n\n"
        "**Services:** Churn Prediction, Driver Allocation, Dynamic Pricing, "
        "ETA Predictor, Food Assistant, Recommendation Engine, Recovery Agent, "
        "Review Summarizer."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow React frontend and any localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5174",
        "https://steamypot-frontend.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers
for svc in SERVICES:
    app.include_router(svc["router"])


# ---------------------------------------------------------------------------
# Gateway-level endpoints
# ---------------------------------------------------------------------------
@app.get("/", tags=["Gateway"])
async def root():
    """Gateway welcome & navigation."""
    return {
        "service": "AI-Layer Unified Gateway",
        "version": "1.0.0",
        "docs": "/docs",
        "services": "/services",
        "health": "/health",
    }


@app.get("/health", tags=["Gateway"])
async def health():
    """Aggregated health check across all services."""
    ok_count = sum(1 for v in _service_status.values() if v == "ok")
    total = len(SERVICES)
    return {
        "status": "healthy" if ok_count == total else "degraded",
        "services_up": ok_count,
        "services_total": total,
        "details": _service_status,
    }


@app.get("/services", tags=["Gateway"])
async def list_services():
    """Service discovery — list all available AI services and their endpoints."""
    registry = []
    for svc in SERVICES:
        status = _service_status.get(svc["name"], "unknown")
        registry.append({
            "name": svc["name"],
            "prefix": svc["prefix"],
            "status": status,
            "health_endpoint": f"{svc['prefix']}/health",
        })
    return {"services": registry}


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "9001"))
    print(f"\n  Starting AI-Layer Gateway on http://0.0.0.0:{port}\n")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
