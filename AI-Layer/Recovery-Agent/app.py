"""
app.py  --  FastAPI Server for Autonomous Customer Recovery Agent
==================================================================
Serves the recovery agent as a REST API for a food delivery platform.

Endpoints
---------
  POST /recovery-agent       — Process a single delivery event and return recovery action
  POST /recovery-agent/batch — Run the agent on ALL problem events in the dataset
  GET  /recovery-agent/stats — Event stream statistics
  GET  /health               — Liveness check

Architecture
------------
  ┌────────────┐     ┌───────────────┐     ┌────────────────┐     ┌──────────────┐
  │  Client /  │────▶│   FastAPI      │────▶│  Event Monitor  │────▶│  Recovery    │
  │  Webhook   │     │   /recovery-   │     │  (classify)     │     │  Engine      │
  │            │     │    agent       │     └────────────────┘     │  (decide+act)│
  └────────────┘     └───────────────┘                             └──────┬───────┘
                                                                          │
                              ┌────────────────────────────────────────────┘
                              ▼
                     ┌─────────────────────────────────────────┐
                     │  Actions:                                │
                     │  • Generate coupon (10% / 15% / 20%)     │
                     │  • Reassign nearest driver               │
                     │  • Send apology / feedback message       │
                     │  • Issue refund                          │
                     └─────────────────────────────────────────┘

AI Concept: Autonomous Agents — How They Monitor & Execute
-----------------------------------------------------------
An **autonomous agent** is software that:
  1. **Perceives** its environment through sensors / event streams.
  2. **Decides** what to do using rules, heuristics, or ML models.
  3. **Acts** on the environment (issue coupons, reassign drivers).
  4. **Learns** (optionally) from outcomes to improve future decisions.

This recovery agent implements steps 1-3:

  ┌──────────────────────────────────────────────────────────────┐
  │                   AGENT CONTROL LOOP                         │
  │                                                              │
  │   ┌─────────┐   ┌──────────┐   ┌────────┐   ┌───────────┐  │
  │   │ PERCEIVE│──▶│  DECIDE  │──▶│  ACT   │──▶│  REPORT   │  │
  │   │         │   │          │   │        │   │           │  │
  │   │ Event   │   │ Rule     │   │ Coupon │   │ JSON log  │  │
  │   │ Monitor │   │ Engine   │   │ Driver │   │ Audit     │  │
  │   │         │   │          │   │ Message│   │ trail     │  │
  │   └─────────┘   └──────────┘   └────────┘   └───────────┘  │
  │                                                              │
  │   In production this loop runs continuously on a             │
  │   Kafka / RabbitMQ consumer.  Here it's triggered            │
  │   per HTTP request for demonstration.                        │
  └──────────────────────────────────────────────────────────────┘

How Event Monitoring Works in Production
-----------------------------------------
  1. **Event Sources**: Order service, driver service, review service
     each emit events to a message broker (Kafka topic).

  2. **Consumer Group**: The recovery agent runs as a consumer group.
     Multiple instances can process events in parallel for scalability.

  3. **Exactly-Once Processing**: Each event has a unique event_id.
     The agent uses idempotency keys to avoid duplicate actions
     (e.g., issuing two coupons for the same delay).

  4. **Dead Letter Queue**: Events that fail processing are routed
     to a DLQ for manual review — the agent never silently drops events.

  5. **Action Execution**: After deciding on an action, the agent
     calls downstream APIs:
       - Promotions API → create coupon
       - Dispatch API   → reassign driver
       - Notification API → send message to customer

CORS is enabled for the React frontend at localhost:5173.
"""

import os
import json
import time
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Internal modules
from data_generator import save_data
from event_monitor import EventMonitor
from recovery_engine import RecoveryEngine

# ---------------------------------------------------------------------------
# Data directory
# ---------------------------------------------------------------------------
DATA_DIR = "data"

# ---------------------------------------------------------------------------
# Pydantic models — Request / Response schemas
# ---------------------------------------------------------------------------

class RecoveryEventRequest(BaseModel):
    """
    Request body for POST /recovery-agent.

    Accepts a single delivery event for the agent to process.
    In production, this would come from a webhook or message queue.
    """
    event_type: str = Field(
        ...,
        description="Type of delivery event",
        examples=["delivery_delay", "driver_cancelled", "order_cancelled", "negative_review"],
    )
    order_id: str = Field(
        ...,
        description="Order identifier",
        examples=["ord_a1b2c3d4"],
    )
    details: dict = Field(
        default={},
        description=(
            "Event-specific details. Examples:\n"
            "  delivery_delay:  {\"delay_min\": 25}\n"
            "  driver_cancelled: {\"cancelled_driver_id\": \"drv_007\", \"reason\": \"vehicle_breakdown\"}\n"
            "  order_cancelled: {\"reason\": \"restaurant_closed\"}\n"
            "  negative_review: {\"rating\": 1, \"comment\": \"Food was cold\"}"
        ),
    )


class NewDriverInfo(BaseModel):
    """Details of the newly assigned driver (if applicable)."""
    driver_id: str
    driver_name: str
    distance_km: float
    rating: float


class RecoveryActionResponse(BaseModel):
    """
    Response from the recovery agent after processing an event.

    AI Concept: Structured Action Report
    ------------------------------------
    Every autonomous action is logged with full context.
    This enables:
      * Audit trails for compliance
      * Effectiveness analytics (which actions reduce churn?)
      * Debugging when something goes wrong
    """
    event_id: Optional[str] = None
    order_id: str
    event_type: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    restaurant: Optional[str] = None
    action_taken: str = Field(..., description="Description of the recovery action executed")
    coupon_applied: Optional[str] = Field(None, description="Coupon code if one was generated")
    new_driver: Optional[NewDriverInfo] = Field(None, description="New driver info if reassigned")
    message_sent: str = Field(..., description="Message sent to the customer")
    severity: str = Field(..., description="Severity level: low, medium, high, critical")
    resolved_at: str = Field(..., description="ISO timestamp of when the action was taken")


class BatchResponse(BaseModel):
    """Response from batch processing all problem events."""
    total_events_in_stream: int
    problem_events_found: int
    actions_taken: int
    actions_by_severity: dict
    actions_by_type: dict
    sample_actions: List[dict]
    processing_time_sec: float


class StatsResponse(BaseModel):
    """Event stream statistics."""
    total_events: int
    events_by_type: dict
    problem_events_count: int
    problem_event_types: List[str]


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------
_monitor: Optional[EventMonitor] = None
_engine: Optional[RecoveryEngine] = None
_orders: list = []
_drivers: list = []


def _init_system():
    """Initialise data, monitor, and engine."""
    global _monitor, _engine, _orders, _drivers

    # Generate data if not present
    if not os.path.exists(os.path.join(DATA_DIR, "events.json")):
        print("[recovery-agent] Generating synthetic event data...")
        save_data(DATA_DIR)

    # Load orders & drivers
    with open(os.path.join(DATA_DIR, "orders.json"), "r") as f:
        _orders = json.load(f)
    with open(os.path.join(DATA_DIR, "drivers.json"), "r") as f:
        _drivers = json.load(f)

    # Initialise monitor & engine
    _monitor = EventMonitor(DATA_DIR)
    _monitor.load()
    _engine = RecoveryEngine(drivers=_drivers, orders=_orders)

    print(f"[recovery-agent] Loaded {_monitor.total_events} events, "
          f"{len(_orders)} orders, {len(_drivers)} drivers")


# ---------------------------------------------------------------------------
# FastAPI app with lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown lifecycle.

    AI Concept: Agent Initialization
    --------------------------------
    On startup the agent:
      1. Generates synthetic data (if first run).
      2. Loads event stream into memory.
      3. Instantiates the recovery engine.

    In production this would connect to Kafka, load ML models,
    and start the consumer loop.
    """
    print("=" * 60)
    print(" Autonomous Customer Recovery Agent")
    print(" Starting up...")
    print("=" * 60)
    _init_system()
    print("[recovery-agent] Agent ready. Listening for events.")
    print("=" * 60)
    yield
    print("[recovery-agent] Shutting down.")


app = FastAPI(
    title="Autonomous Customer Recovery Agent",
    description=(
        "AI-powered agent that automatically detects delivery problems "
        "and executes recovery actions (coupons, driver reassignment, "
        "apology messages) without human intervention."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Liveness check."""
    return {
        "status": "healthy",
        "service": "recovery-agent",
        "events_loaded": _monitor.total_events if _monitor else 0,
        "orders_loaded": len(_orders),
        "drivers_loaded": len(_drivers),
    }


@app.post("/recovery-agent", response_model=RecoveryActionResponse)
async def process_event(req: RecoveryEventRequest):
    """
    Process a single delivery event and return the recovery action.

    **This is the core autonomous agent endpoint.**

    AI Concept: Request-Driven Agent Invocation
    --------------------------------------------
    In this demo, the agent is invoked per HTTP request.
    In production, it would run as a continuous consumer:

        while True:
            event = kafka_consumer.poll()
            action = engine.handle_event(event)
            action_api.execute(action)
            kafka_consumer.commit()

    The logic is identical — only the transport layer changes.

    **Example requests:**

    *Delivery delay (25 min):*
    ```json
    {
      "event_type": "delivery_delay",
      "order_id": "<order_id_from_data>",
      "details": {"delay_min": 25}
    }
    ```

    *Driver cancelled:*
    ```json
    {
      "event_type": "driver_cancelled",
      "order_id": "<order_id_from_data>",
      "details": {"cancelled_driver_id": "drv_007", "reason": "vehicle_breakdown"}
    }
    ```
    """
    if not _engine or not _monitor:
        raise HTTPException(status_code=503, detail="Agent not initialised yet")

    # Build event dict from request
    event = _monitor.simulate_single_event({
        "event_type": req.event_type,
        "order_id": req.order_id,
        "details": req.details,
    })

    # Run the agent
    result = _engine.handle_event(event)
    return result


@app.post("/recovery-agent/batch", response_model=BatchResponse)
async def process_all_events():
    """
    Run the agent on ALL problem events in the dataset.

    AI Concept: Batch Agent Execution
    ---------------------------------
    Useful for:
      * Backtesting the agent against historical events.
      * Measuring recovery coverage and action distribution.
      * Generating dashboards and analytics.

    Returns a summary with action counts by severity and type,
    plus a sample of individual actions.
    """
    if not _engine or not _monitor:
        raise HTTPException(status_code=503, detail="Agent not initialised yet")

    t0 = time.time()
    problem_events = _monitor.get_problem_events()
    actions = []

    for event in problem_events:
        action = _engine.handle_event(event)
        actions.append(action)

    elapsed = round(time.time() - t0, 3)

    # Aggregate stats
    severity_counts = {}
    type_counts = {}
    for a in actions:
        sev = a.get("severity", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        etype = a.get("event_type", "unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1

    return BatchResponse(
        total_events_in_stream=_monitor.total_events,
        problem_events_found=len(problem_events),
        actions_taken=len(actions),
        actions_by_severity=severity_counts,
        actions_by_type=type_counts,
        sample_actions=actions[:10],
        processing_time_sec=elapsed,
    )


@app.get("/recovery-agent/stats", response_model=StatsResponse)
async def get_stats():
    """
    Return event stream statistics.

    AI Concept: Agent Observability
    -------------------------------
    Autonomous agents need monitoring dashboards that show:
      * How many events are being processed.
      * Distribution of event types.
      * How many require agent intervention.
    This endpoint powers such a dashboard.
    """
    if not _monitor:
        raise HTTPException(status_code=503, detail="Agent not initialised yet")

    stats = _monitor.get_event_stats()
    from event_monitor import PROBLEM_EVENTS
    problem_count = sum(
        v for k, v in stats.items() if k in PROBLEM_EVENTS
    )

    return StatsResponse(
        total_events=_monitor.total_events,
        events_by_type=stats,
        problem_events_count=problem_count,
        problem_event_types=sorted(PROBLEM_EVENTS),
    )


@app.get("/recovery-agent/orders")
async def list_orders(limit: int = 20):
    """List orders from the dataset (for finding order_ids to test with)."""
    return {"orders": _orders[:limit], "total": len(_orders)}


@app.get("/recovery-agent/events")
async def list_problem_events(limit: int = 20):
    """List problem events from the dataset (for finding events to test with)."""
    if not _monitor:
        raise HTTPException(status_code=503, detail="Agent not initialised yet")
    problems = _monitor.get_problem_events()
    return {"problem_events": problems[:limit], "total": len(problems)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
