"""
Driver Allocation Service Router
==================================
Wraps the Driver-Allocation project as a FastAPI APIRouter.

Endpoints:
  POST /api/driver/allocate
  GET  /api/driver/drivers
  GET  /api/driver/optimization-logic
"""
import os
import sys
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from services import get_service_dir, safe_import

router = APIRouter(prefix="/api/driver", tags=["Driver Allocation"])

SERVICE_DIR = get_service_dir("Driver-Allocation")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_allocator = None
_OrderInfo = None
_initialized = False
_error = None


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
def init():
    global _allocator, _OrderInfo, _initialized, _error
    try:
        _cwd = os.getcwd()
        os.chdir(SERVICE_DIR)

        dg = safe_import(SERVICE_DIR, "data_generator")
        dg.save_drivers()

        da = safe_import(SERVICE_DIR, "driver_allocator")
        _OrderInfo = da.OrderInfo
        _allocator = da.DriverAllocator()
        _initialized = True

        os.chdir(_cwd)
        print(f"  [driver] Loaded {len(_allocator.drivers)} drivers")
    except Exception as e:
        _error = str(e)
        try:
            os.chdir(_cwd)
        except Exception:
            pass
        print(f"  [driver] FAILED: {e}")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class Location(BaseModel):
    lat: float
    lon: float


class AllocateRequest(BaseModel):
    restaurant_location: Location
    customer_location: Location
    estimated_prep_time: float = 15
    order_size: int = 2


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/allocate")
async def allocate_driver(req: AllocateRequest):
    """Allocate the optimal driver for an order."""
    if not _initialized:
        raise HTTPException(503, f"Driver service unavailable: {_error}")

    start = time.time()
    order = _OrderInfo(
        restaurant_lat=req.restaurant_location.lat,
        restaurant_lon=req.restaurant_location.lon,
        customer_lat=req.customer_location.lat,
        customer_lon=req.customer_location.lon,
        estimated_prep_time=req.estimated_prep_time,
        order_size=req.order_size,
    )
    result = _allocator.allocate(order)
    result["processing_time_ms"] = round((time.time() - start) * 1000, 2)
    return result


@router.get("/drivers")
async def list_drivers():
    """Return the full driver fleet with current status."""
    if not _initialized:
        raise HTTPException(503, f"Driver service unavailable: {_error}")

    fleet = []
    for d in _allocator.drivers:
        fleet.append({
            "driver_id": d.driver_id,
            "driver_name": d.driver_name,
            "location": {"lat": d.lat, "lon": d.lon},
            "zone": d.zone,
            "driver_rating": d.driver_rating,
            "current_active_orders": d.current_active_orders,
            "average_delivery_time": d.average_delivery_time,
            "delivery_success_rate": d.delivery_success_rate,
        })
    return {"drivers": fleet, "count": len(fleet)}


@router.get("/optimization-logic")
async def optimization_logic():
    """Return a detailed explanation of the scoring algorithm."""
    return {
        "algorithm": "Weighted Multi-Criteria Scoring",
        "formula": "score = 0.4×distance + 0.2×rating + 0.2×success_rate + 0.2×workload",
        "weights": {
            "distance_score": 0.40,
            "driver_rating_score": 0.20,
            "success_rate_score": 0.20,
            "workload_score": 0.20,
        },
        "tie_breaker": "Lower predicted ETA (GradientBoosted regression model)",
    }


@router.get("/health")
async def health():
    return {
        "status": "ok" if _initialized else "unavailable",
        "service": "driver-allocation",
        "drivers_loaded": len(_allocator.drivers) if _allocator else 0,
        "error": _error,
    }
