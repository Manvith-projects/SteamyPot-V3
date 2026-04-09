"""
Recovery Agent Service Router
===============================
Wraps the Recovery-Agent project as a FastAPI APIRouter.

Endpoints:
  POST /api/recovery/agent
  POST /api/recovery/agent/batch
  GET  /api/recovery/agent/stats
  GET  /api/recovery/agent/orders
  GET  /api/recovery/agent/events
"""
import os
import json
import time
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import get_service_dir, safe_import

router = APIRouter(prefix="/api/recovery", tags=["Recovery Agent"])

SERVICE_DIR = get_service_dir("Recovery-Agent")
DATA_DIR = os.path.join(SERVICE_DIR, "data")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_monitor = None
_engine = None
_orders = []
_drivers = []
_problem_events_list = None
_initialized = False
_error = None


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
def init():
    global _monitor, _engine, _orders, _drivers, _problem_events_list
    global _initialized, _error

    try:
        _cwd = os.getcwd()
        os.chdir(SERVICE_DIR)

        # Generate data if not present
        if not os.path.exists(os.path.join(DATA_DIR, "events.json")):
            dg = safe_import(SERVICE_DIR, "data_generator")
            dg.save_data(DATA_DIR)

        with open(os.path.join(DATA_DIR, "orders.json")) as f:
            _orders = json.load(f)
        with open(os.path.join(DATA_DIR, "drivers.json")) as f:
            _drivers = json.load(f)

        em_mod = safe_import(SERVICE_DIR, "event_monitor")
        re_mod = safe_import(SERVICE_DIR, "recovery_engine")

        _monitor = em_mod.EventMonitor(DATA_DIR)
        _monitor.load()
        _engine = re_mod.RecoveryEngine(drivers=_drivers, orders=_orders)
        _problem_events_list = getattr(em_mod, "PROBLEM_EVENTS", set())

        _initialized = True
        os.chdir(_cwd)
        print(f"  [recovery] Loaded: {_monitor.total_events} events, "
              f"{len(_orders)} orders, {len(_drivers)} drivers")
    except Exception as e:
        _error = str(e)
        try:
            os.chdir(_cwd)
        except Exception:
            pass
        print(f"  [recovery] FAILED: {e}")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class RecoveryEventRequest(BaseModel):
    event_type: str = Field(
        ..., description="delivery_delay | driver_cancelled | order_cancelled | negative_review"
    )
    order_id: str
    details: dict = {}


class NewDriverInfo(BaseModel):
    driver_id: str
    driver_name: str
    distance_km: float
    rating: float


class RecoveryActionResponse(BaseModel):
    event_id: Optional[str] = None
    order_id: str
    event_type: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    restaurant: Optional[str] = None
    action_taken: str
    coupon_applied: Optional[str] = None
    new_driver: Optional[NewDriverInfo] = None
    message_sent: str
    severity: str
    resolved_at: str


class BatchResponse(BaseModel):
    total_events_in_stream: int
    problem_events_found: int
    actions_taken: int
    actions_by_severity: dict
    actions_by_type: dict
    sample_actions: List[dict]
    processing_time_sec: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/agent", response_model=RecoveryActionResponse)
async def process_event(req: RecoveryEventRequest):
    """Process a single delivery event and return recovery action."""
    if not _initialized:
        raise HTTPException(503, f"Recovery agent unavailable: {_error}")

    event = _monitor.simulate_single_event({
        "event_type": req.event_type,
        "order_id": req.order_id,
        "details": req.details,
    })
    result = _engine.handle_event(event)
    return result


@router.post("/agent/batch", response_model=BatchResponse)
async def process_all_events():
    """Run the agent on ALL problem events in the dataset."""
    if not _initialized:
        raise HTTPException(503, f"Recovery agent unavailable: {_error}")

    t0 = time.time()
    problem_events = _monitor.get_problem_events()
    actions = []
    for event in problem_events:
        action = _engine.handle_event(event)
        actions.append(action)

    elapsed = round(time.time() - t0, 3)

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


@router.get("/agent/stats")
async def get_stats():
    """Return event stream statistics."""
    if not _initialized:
        raise HTTPException(503, f"Recovery agent unavailable: {_error}")

    stats = _monitor.get_event_stats()
    problem_count = sum(v for k, v in stats.items() if k in _problem_events_list)

    return {
        "total_events": _monitor.total_events,
        "events_by_type": stats,
        "problem_events_count": problem_count,
        "problem_event_types": sorted(_problem_events_list) if _problem_events_list else [],
    }


@router.get("/agent/orders")
async def list_orders(limit: int = 20):
    """List orders from the dataset."""
    return {"orders": _orders[:limit], "total": len(_orders)}


@router.get("/agent/events")
async def list_problem_events(limit: int = 20):
    """List problem events from the dataset."""
    if not _initialized:
        raise HTTPException(503, f"Recovery agent unavailable: {_error}")
    problems = _monitor.get_problem_events()
    return {"problem_events": problems[:limit], "total": len(problems)}


@router.get("/health")
async def health():
    return {
        "status": "ok" if _initialized else "unavailable",
        "service": "recovery-agent",
        "events_loaded": _monitor.total_events if _monitor else 0,
        "orders_loaded": len(_orders),
        "drivers_loaded": len(_drivers),
        "error": _error,
    }
