"""
safety_layer.py
===============
Rule-based safety guardrails applied *after* the ML model predicts a
raw surge multiplier.

Business reasoning
------------------
ML models can produce extreme or undesirable outputs -- a predicted
surge of 4.2x during a data glitch would anger customers and invite
regulatory scrutiny.  The safety layer enforces hard business rules:

  1. **Surge cap at 2.5x** -- no order ever costs more than 2.5x the
     base fee, regardless of what the model predicts.
  2. **Surge floor at 1.0x** -- delivery fee never drops below base.
  3. **Discount cap at 30 %** -- during low demand the system may
     recommend a discount to stimulate orders, but never more than 30 %.
  4. **Discount only when surge <= 1.05x** -- offering a discount
     during a surge would be contradictory.
  5. **Pricing reason** -- every API response includes a human-readable
     explanation of *why* the price was set, supporting transparency.

These rules are intentionally kept outside the ML model so that:
  * Business teams can adjust caps without re-training.
  * Auditors can inspect the rule set independently.
  * The API always behaves predictably at the boundaries.
"""

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration (easily adjustable by business)
# ---------------------------------------------------------------------------
SURGE_CAP = 2.5
SURGE_FLOOR = 1.0
DISCOUNT_CAP = 0.30          # 30 % maximum discount
DISCOUNT_SURGE_THRESHOLD = 1.05  # only offer discounts below this surge
BASE_FEE_DEFAULT = 40.0      # fallback base delivery fee (INR)


# ---------------------------------------------------------------------------
# Output data class
# ---------------------------------------------------------------------------

@dataclass
class PricingDecision:
    """Immutable pricing response returned to the API layer."""
    surge_multiplier: float
    final_delivery_fee: float
    recommended_discount: float     # 0.0 - 0.30  (fraction, not %)
    pricing_reason: str
    raw_model_surge: float          # before safety clamp (for logging)
    is_peak_hour: bool


# ---------------------------------------------------------------------------
# Core safety function
# ---------------------------------------------------------------------------

def apply_safety_rules(
    raw_surge: float,
    is_peak: int,
    base_fee: float = BASE_FEE_DEFAULT,
    demand_supply_ratio: Optional[float] = None,
    distance_km: Optional[float] = None,
) -> PricingDecision:
    """
    Apply business guardrails to the raw ML prediction.

    Parameters
    ----------
    raw_surge : float
        Model's raw surge multiplier prediction.
    is_peak : int
        1 if the classification model flagged this as a peak period.
    base_fee : float
        Zone-specific base delivery fee (already distance-adjusted).
    demand_supply_ratio : float, optional
        If provided, used to calibrate the discount recommendation.
    distance_km : float, optional
        Delivery distance -- used for pricing-reason annotation.

    Returns
    -------
    PricingDecision
    """
    reasons = []

    # --- 1. Clamp surge to [SURGE_FLOOR, SURGE_CAP] -----------------------
    surge = max(SURGE_FLOOR, min(SURGE_CAP, raw_surge))
    if raw_surge > SURGE_CAP:
        reasons.append(f"Surge capped from {raw_surge:.2f}x to {SURGE_CAP}x (safety limit)")
    elif raw_surge < SURGE_FLOOR:
        reasons.append(f"Surge floored from {raw_surge:.2f}x to {SURGE_FLOOR}x")

    # --- 2. Calculate final delivery fee -----------------------------------
    final_fee = round(base_fee * surge, 2)

    # --- 3. Discount recommendation ----------------------------------------
    discount = 0.0
    if surge <= DISCOUNT_SURGE_THRESHOLD:
        # Low demand -- stimulate orders with a discount
        # Discount strength proportional to how far below threshold we are
        slack = DISCOUNT_SURGE_THRESHOLD - surge  # 0.0 - 0.05
        discount = min(DISCOUNT_CAP, round(slack * 6.0, 2))  # scale up
        # Also factor in demand/supply ratio if available
        if demand_supply_ratio is not None and demand_supply_ratio < 0.5:
            # Very low demand -- bump discount
            discount = min(DISCOUNT_CAP, discount + 0.10)
        if discount > 0:
            reasons.append(f"Low demand: {discount*100:.0f}% discount recommended")
    else:
        reasons.append("No discount (demand is elevated)")

    # --- 4. Surge explanation ----------------------------------------------
    if surge >= 2.0:
        reasons.insert(0, "Very high demand -- maximum surge pricing active")
    elif surge >= 1.5:
        reasons.insert(0, "High demand in your area -- moderate surge applied")
    elif surge >= 1.2:
        reasons.insert(0, "Slightly elevated demand -- minor surge applied")
    else:
        reasons.insert(0, "Normal demand -- standard pricing")

    if is_peak:
        reasons.append("Peak hour detected")

    # Distance annotation for transparency
    if distance_km is not None:
        if distance_km >= 12.0:
            reasons.append(f"Long-distance delivery ({distance_km:.1f} km) -- higher base fee applied")
        elif distance_km >= 6.0:
            reasons.append(f"Medium distance ({distance_km:.1f} km)")

    pricing_reason = "; ".join(reasons)

    return PricingDecision(
        surge_multiplier=round(surge, 3),
        final_delivery_fee=final_fee,
        recommended_discount=round(discount, 3),
        pricing_reason=pricing_reason,
        raw_model_surge=round(raw_surge, 4),
        is_peak_hour=bool(is_peak),
    )


# ---------------------------------------------------------------------------
# Batch application (for dataset-level evaluation)
# ---------------------------------------------------------------------------

def apply_safety_batch(df, surge_col="pred_surge", peak_col="pred_peak",
                       base_fee_col="base_delivery_fee"):
    """Apply safety rules to every row and return enriched DataFrame."""
    import pandas as pd
    decisions = []
    for _, row in df.iterrows():
        d = apply_safety_rules(
            raw_surge=row[surge_col],
            is_peak=int(row[peak_col]),
            base_fee=row.get(base_fee_col, BASE_FEE_DEFAULT),
            demand_supply_ratio=row.get("demand_supply_ratio"),
        )
        decisions.append({
            "safe_surge": d.surge_multiplier,
            "safe_fee": d.final_delivery_fee,
            "discount": d.recommended_discount,
            "reason": d.pricing_reason,
        })
    return pd.DataFrame(decisions)
