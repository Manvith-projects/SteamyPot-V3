"""
recovery_engine.py  --  Autonomous Recovery Decision Engine
============================================================
The core "brain" of the customer recovery agent.

This module implements a **rule-based autonomous agent** that:
  1. Receives a classified problem event.
  2. Evaluates recovery rules against the event context.
  3. Selects and executes the best recovery action.
  4. Returns a structured action report.

AI Concept: Rule-Based Autonomous Agents
-----------------------------------------
An autonomous agent is a system that perceives its environment,
makes decisions, and takes actions — all **without human intervention**.

This recovery agent follows the classic agent loop:

    ┌──────────────────────────────────────────────────┐
    │              AGENT CONTROL LOOP                   │
    │                                                   │
    │  Perceive   →   Decide   →   Act   →   Report    │
    │  (events)      (rules)     (coupon/    (JSON)     │
    │                            reassign)              │
    └──────────────────────────────────────────────────┘

The agent is **reactive** (responds to events as they arrive) and
**goal-directed** (its goal is to minimise customer churn caused
by delivery failures).

Rule Engine vs ML Agent
-----------------------
  * **Rule-based** (this implementation): Deterministic, auditable,
    easy to explain to business stakeholders.  Rules are manually
    curated by domain experts.

  * **ML-based** (future upgrade path): A reinforcement-learning
    agent could learn optimal recovery strategies by maximising a
    reward signal (e.g., customer retention rate).  The RL agent
    would explore different coupon values and messaging strategies,
    learning which actions work best for different customer segments.

  * **Hybrid** (production best practice): Start with rules for
    day-1 coverage, then layer ML on top to personalise and optimise.
    The rules act as a safety net / fallback when the ML model is
    uncertain.

Recovery Rules (Business Logic)
-------------------------------
  ┌─────────────────────┬───────────────────────────────────────┐
  │ Condition           │ Action                                │
  ├─────────────────────┼───────────────────────────────────────┤
  │ delay > 30 min      │ 20% coupon + apology message          │
  │ delay > 15 min      │ 10% coupon                            │
  │ driver cancelled    │ Reassign nearest available driver      │
  │ order cancelled     │ Full refund + 15% coupon              │
  │ negative review     │ Feedback request + 10% discount        │
  └─────────────────────┴───────────────────────────────────────┘

Rules are evaluated in priority order (most severe first) so that
a 35-minute delay triggers the 20% rule, not the 10% rule.
"""

import math
import random
import uuid
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Coupon generator
# ---------------------------------------------------------------------------

def _generate_coupon(percent: int, order_id: str) -> str:
    """
    Generate a unique coupon code.

    AI Concept: Action Execution
    ----------------------------
    In a production autonomous agent, this would call
    the Promotions microservice API.  Here we generate a
    deterministic code for traceability.
    """
    short_id = order_id.split("_")[1][:4] if "_" in order_id else "xxxx"
    return f"RECOVERY{percent}_{short_id}_{uuid.uuid4().hex[:4].upper()}"


# ---------------------------------------------------------------------------
# Driver reassignment
# ---------------------------------------------------------------------------

def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearest_driver(
    drivers: list,
    restaurant_lat: float,
    restaurant_lon: float,
    exclude_driver_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Find the nearest available driver to the restaurant.

    AI Concept: Greedy Nearest-Neighbour Assignment
    ------------------------------------------------
    This is a greedy heuristic: pick the closest available driver.
    In a production system this could be upgraded to:
      * **Hungarian algorithm** for global optimal multi-order assignment.
      * **RL dispatch** that considers future demand predictions.
    The greedy approach is a solid baseline that the rule engine uses.
    """
    available = [
        d for d in drivers
        if d["status"] == "available" and d["driver_id"] != exclude_driver_id
    ]
    if not available:
        return None

    best = min(
        available,
        key=lambda d: _haversine(
            d["lat"], d["lon"],
            restaurant_lat, restaurant_lon,
        ),
    )
    return {
        "driver_id": best["driver_id"],
        "driver_name": best["name"],
        "distance_km": round(
            _haversine(best["lat"], best["lon"], restaurant_lat, restaurant_lon), 2
        ),
        "rating": best["rating"],
    }


# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------

APOLOGY_TEMPLATES = [
    "We're really sorry for the delay, {name}. Your satisfaction matters to us!",
    "Hi {name}, we apologise for the wait. Here's a coupon to make it up to you.",
    "Dear {name}, we know your time is valuable. Please accept our apology.",
]

FEEDBACK_TEMPLATES = [
    "Hi {name}, we noticed your recent experience wasn't great. We'd love your feedback to improve!",
    "Dear {name}, your opinion matters. Could you tell us more about what went wrong?",
    "Hi {name}, we're sorry about your experience. Help us do better — share your thoughts!",
]

CANCELLATION_TEMPLATES = [
    "Hi {name}, we're sorry your order was cancelled. A full refund is on its way!",
    "Dear {name}, we apologise for the inconvenience. Your refund has been processed.",
]

DRIVER_REASSIGN_TEMPLATES = [
    "Hi {name}, your driver had to cancel. Don't worry — a new driver is on the way!",
    "Good news, {name}! We've assigned a new driver who's nearby. Your order is still coming!",
]


# ---------------------------------------------------------------------------
# Core Recovery Engine
# ---------------------------------------------------------------------------

class RecoveryEngine:
    """
    Autonomous Recovery Agent — Rule Evaluation Engine.

    AI Concept: Agent Architecture
    ------------------------------
    This class encapsulates the **decide** and **act** phases of the
    agent loop.  It receives a structured event, evaluates rules in
    priority order, executes the chosen action, and returns a report.

    The engine is stateless per invocation — each event is handled
    independently.  In a production system, a state store (Redis / DB)
    would track cumulative actions per customer to avoid over-recovery
    (e.g., don't send 5 coupons in one day).
    """

    def __init__(self, drivers: list, orders: list):
        self._drivers = drivers
        self._orders_by_id = {o["order_id"]: o for o in orders}

    # ── Public entry point ────────────────────────────────────────────

    def handle_event(self, event: dict) -> dict:
        """
        Process a single problem event and return recovery action.

        AI Concept: Sense → Decide → Act Pattern
        ------------------------------------------
        1. **Sense**: Parse the event type and extract context.
        2. **Decide**: Match against rule table (priority order).
        3. **Act**: Generate coupon / reassign driver / send message.
        4. **Report**: Return structured JSON for audit trail.

        Parameters
        ----------
        event : dict
            A problem event from the event monitor.

        Returns
        -------
        dict
            Recovery action report with keys:
              - action_taken (str)
              - coupon_applied (str or None)
              - new_driver (dict or None)
              - message_sent (str)
              - severity (str)
              - timestamp (str)
        """
        etype = event.get("event_type", "")
        order_id = event.get("order_id", "")
        order = self._orders_by_id.get(order_id, {})
        customer_name = order.get("customer_name", "Customer")
        details = event.get("details", {})

        # ── Rule evaluation (priority order: most severe first) ───

        if etype == "delivery_delay":
            return self._handle_delay(event, order, customer_name, details)

        if etype == "driver_cancelled":
            return self._handle_driver_cancelled(event, order, customer_name, details)

        if etype == "order_cancelled":
            return self._handle_order_cancelled(event, order, customer_name, details)

        if etype == "negative_review":
            return self._handle_negative_review(event, order, customer_name, details)

        # Unknown event — no action
        return self._build_report(
            event=event,
            order=order,
            action="no_action",
            severity="info",
            message=f"Event type '{etype}' does not require recovery.",
            coupon=None,
            new_driver=None,
        )

    # ── Rule handlers ─────────────────────────────────────────────

    def _handle_delay(self, event, order, name, details) -> dict:
        """
        Handle delivery_delay events.

        Rule priority:
          1. delay > 30 min → 20% coupon + apology
          2. delay > 15 min → 10% coupon
        """
        delay_min = details.get("delay_min", 0)

        if delay_min > 30:
            coupon = _generate_coupon(20, event["order_id"])
            msg = random.choice(APOLOGY_TEMPLATES).format(name=name)
            return self._build_report(
                event=event, order=order,
                action=f"applied_20pct_coupon_delay_{delay_min}min",
                severity="high",
                message=msg + f" Use code {coupon} for 20% off your next order.",
                coupon=coupon,
                new_driver=None,
            )

        elif delay_min > 15:
            coupon = _generate_coupon(10, event["order_id"])
            msg = random.choice(APOLOGY_TEMPLATES).format(name=name)
            return self._build_report(
                event=event, order=order,
                action=f"applied_10pct_coupon_delay_{delay_min}min",
                severity="medium",
                message=msg + f" Use code {coupon} for 10% off your next order.",
                coupon=coupon,
                new_driver=None,
            )

        # Delay ≤ 15 min — minor, no coupon
        return self._build_report(
            event=event, order=order,
            action=f"minor_delay_{delay_min}min_no_action",
            severity="low",
            message=f"Hi {name}, your order is slightly delayed. Hang tight!",
            coupon=None,
            new_driver=None,
        )

    def _handle_driver_cancelled(self, event, order, name, details) -> dict:
        """
        Handle driver_cancelled events.

        Rule: Reassign nearest available driver.
        """
        cancelled_driver_id = details.get("cancelled_driver_id")

        # Find restaurant zone coordinates for distance calc
        rest_zone_name = order.get("restaurant_zone", "")
        from data_generator import ZONES
        zone_match = next(
            (z for z in ZONES if z["name"] == rest_zone_name), None,
        )
        rest_lat = zone_match["lat"] if zone_match else 17.44
        rest_lon = zone_match["lon"] if zone_match else 78.39

        new_driver = find_nearest_driver(
            self._drivers, rest_lat, rest_lon,
            exclude_driver_id=cancelled_driver_id,
        )

        if new_driver:
            msg = random.choice(DRIVER_REASSIGN_TEMPLATES).format(name=name)
            return self._build_report(
                event=event, order=order,
                action="driver_reassigned",
                severity="high",
                message=msg + f" Driver {new_driver['driver_name']} is {new_driver['distance_km']} km away.",
                coupon=None,
                new_driver=new_driver,
            )
        else:
            # No drivers available — escalate with coupon
            coupon = _generate_coupon(15, event["order_id"])
            return self._build_report(
                event=event, order=order,
                action="no_driver_available_coupon_issued",
                severity="critical",
                message=f"Hi {name}, we couldn't find a replacement driver. We've issued coupon {coupon} (15% off) and our team is looking into it.",
                coupon=coupon,
                new_driver=None,
            )

    def _handle_order_cancelled(self, event, order, name, details) -> dict:
        """
        Handle order_cancelled events.

        Rule: Full refund + 15% coupon for next order.
        """
        reason = details.get("reason", "unknown")
        coupon = _generate_coupon(15, event["order_id"])
        msg = random.choice(CANCELLATION_TEMPLATES).format(name=name)

        return self._build_report(
            event=event, order=order,
            action=f"order_cancelled_refund_and_coupon_reason_{reason}",
            severity="high",
            message=msg + f" Plus, here's {coupon} for 15% off your next order.",
            coupon=coupon,
            new_driver=None,
        )

    def _handle_negative_review(self, event, order, name, details) -> dict:
        """
        Handle negative_review events.

        Rule: Send feedback request + 10% discount.
        """
        rating = details.get("rating", 0)
        comment = details.get("comment", "")
        coupon = _generate_coupon(10, event["order_id"])
        msg = random.choice(FEEDBACK_TEMPLATES).format(name=name)

        return self._build_report(
            event=event, order=order,
            action=f"negative_review_recovery_rating_{rating}",
            severity="medium",
            message=msg + f" As a gesture, use {coupon} for 10% off. (Review: \"{comment}\")",
            coupon=coupon,
            new_driver=None,
        )

    # ── Report builder ────────────────────────────────────────────

    def _build_report(
        self,
        event: dict,
        order: dict,
        action: str,
        severity: str,
        message: str,
        coupon: Optional[str],
        new_driver: Optional[dict],
    ) -> dict:
        """
        Build a structured recovery action report.

        AI Concept: Audit Trail for Autonomous Actions
        -----------------------------------------------
        Every action taken by an autonomous agent must be logged
        with full context for:
          * **Debugging** — trace why a coupon was issued.
          * **Compliance** — prove the agent acted within its rules.
          * **Analytics** — measure recovery effectiveness.
        """
        return {
            "event_id": event.get("event_id"),
            "order_id": event.get("order_id"),
            "event_type": event.get("event_type"),
            "customer_id": order.get("customer_id"),
            "customer_name": order.get("customer_name"),
            "restaurant": order.get("restaurant"),
            "action_taken": action,
            "coupon_applied": coupon,
            "new_driver": new_driver,
            "message_sent": message,
            "severity": severity,
            "resolved_at": datetime.utcnow().isoformat() + "Z",
        }
