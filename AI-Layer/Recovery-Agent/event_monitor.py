"""
event_monitor.py  --  Event Stream Monitor & Classifier
========================================================
Watches the event stream and filters for problem events that
require the recovery agent's attention.

AI Concept: Event-Driven Autonomous Agents
-------------------------------------------
In production, autonomous agents subscribe to message queues
(Kafka, RabbitMQ, Redis Streams) and react in real-time:

    ┌──────────┐     ┌──────────────┐     ┌────────────────┐
    │ Order    │────▶│  Message      │────▶│ Recovery Agent  │
    │ Service  │     │  Queue        │     │ (consumer)      │
    └──────────┘     │  (Kafka)      │     └───────┬────────┘
                     └──────────────┘             │
    ┌──────────┐                                   │  action
    │ Driver   │────▶  ───────────▶  ─────────────▶│
    │ Service  │                                   ▼
    └──────────┘                            ┌─────────────┐
                                            │ Promotions  │
    ┌──────────┐                            │ / Dispatch  │
    │ Review   │────▶  ───────────▶         └─────────────┘
    │ Service  │
    └──────────┘

This module simulates that pattern by:
  1. Loading events from the synthetic dataset.
  2. Filtering for problem event types.
  3. Feeding them one-by-one to the RecoveryEngine.
  4. Collecting all action reports.

In production, replace `load_events()` with a Kafka consumer
and the recovery engine runs as an always-on microservice.

Event Classification
--------------------
Events are classified into severity tiers so the agent can
prioritise its response queue:

  Critical : order_cancelled, driver_cancelled (no driver available)
  High     : delivery_delay > 30 min, driver_cancelled (reassigned)
  Medium   : delivery_delay 15-30 min, negative_review
  Low      : delivery_delay ≤ 15 min
  Info     : order_placed, delivered (no action needed)
"""

import json
import os
from typing import List, Optional
from datetime import datetime


# Problem event types the agent cares about
PROBLEM_EVENTS = {
    "delivery_delay",
    "driver_cancelled",
    "order_cancelled",
    "negative_review",
}


class EventMonitor:
    """
    Monitors the event stream and yields problem events.

    AI Concept: Perception Layer
    ----------------------------
    In the agent architecture, the monitor is the *perception* layer.
    It observes raw events, classifies them, and passes only
    actionable signals to the decision engine.  This separation
    keeps the decision engine clean and testable.
    """

    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir
        self._events: List[dict] = []
        self._loaded = False

    def load(self) -> int:
        """Load events from JSON file. Returns total event count."""
        path = os.path.join(self._data_dir, "events.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Events file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            self._events = json.load(f)
        self._loaded = True
        return len(self._events)

    @property
    def total_events(self) -> int:
        return len(self._events)

    def get_problem_events(self) -> List[dict]:
        """
        Filter and return only problem events.

        AI Concept: Signal vs Noise
        ---------------------------
        The monitor acts as a filter, discarding normal events
        (order_placed, delivered) and forwarding only anomalous /
        problem events to the agent.  This is analogous to an
        anomaly detector in ML pipelines.
        """
        if not self._loaded:
            self.load()
        return [
            e for e in self._events
            if e.get("event_type") in PROBLEM_EVENTS
        ]

    def get_events_by_type(self, event_type: str) -> List[dict]:
        """Get all events of a specific type."""
        if not self._loaded:
            self.load()
        return [
            e for e in self._events
            if e.get("event_type") == event_type
        ]

    def get_event_by_order(self, order_id: str) -> List[dict]:
        """Get all events for a specific order."""
        if not self._loaded:
            self.load()
        return [
            e for e in self._events
            if e.get("order_id") == order_id
        ]

    def get_event_stats(self) -> dict:
        """
        Return counts per event type.

        Useful for the /stats endpoint and dashboards.
        """
        if not self._loaded:
            self.load()
        stats = {}
        for e in self._events:
            t = e.get("event_type", "unknown")
            stats[t] = stats.get(t, 0) + 1
        return stats

    def simulate_single_event(self, event: dict) -> dict:
        """
        Accept a manually crafted event (e.g., from the API)
        and validate its structure.

        AI Concept: Real-Time Event Injection
        -------------------------------------
        In production, new events arrive continuously.  This method
        lets the API endpoint inject a single event for immediate
        processing, simulating real-time behaviour.
        """
        required_fields = {"event_type", "order_id"}
        missing = required_fields - set(event.keys())
        if missing:
            raise ValueError(f"Event missing required fields: {missing}")

        if "event_id" not in event:
            import uuid
            event["event_id"] = f"evt_{uuid.uuid4().hex[:8]}"
        if "timestamp" not in event:
            event["timestamp"] = datetime.utcnow().isoformat() + "Z"
        if "details" not in event:
            event["details"] = {}

        return event
