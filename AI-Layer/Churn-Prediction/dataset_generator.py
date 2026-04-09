"""
dataset_generator.py  --  Churn Prediction Synthetic Data
=========================================================
Generates a realistic synthetic dataset of 15,000 food-delivery platform
users, each labelled as churned (1) or active (0).

Business context
----------------
Customer churn is the single largest revenue leak for delivery platforms.
Acquiring a new customer costs 5-7x more than retaining an existing one.
By predicting churn *before* it happens, the platform can intervene with
personalised discounts, loyalty rewards, or re-engagement campaigns.

The generator encodes known churn signals:
  * Recency   -- users who haven't ordered recently are more likely to leave.
  * Frequency -- infrequent orderers have weaker platform attachment.
  * Monetary  -- low spenders have less switching cost.
  * Experience -- high delivery delays / complaints erode satisfaction.
  * Engagement -- low app usage signals disengagement.

All dynamics are deterministic given SEED = 42 for reproducibility.
"""

import os
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED = 42
N_USERS = 15_000
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "churn_dataset.csv")

# ---------------------------------------------------------------------------
# Main generation routine
# ---------------------------------------------------------------------------

def generate_dataset(n_users: int = N_USERS,
                     seed: int = SEED,
                     save: bool = True) -> pd.DataFrame:
    """
    Generate a synthetic user-level churn dataset.

    Feature descriptions (with business rationale)
    -----------------------------------------------
    user_id                : int    unique identifier
    orders_last_30d        : int    orders in the last 30 days (recency signal)
    orders_last_90d        : int    orders in the last 90 days (frequency signal)
    avg_order_value        : float  mean spend per order in INR (monetary signal)
    days_since_last_order  : int    recency -- the #1 churn predictor
    order_frequency        : float  orders per month over lifetime
    cancellation_rate      : float  fraction of orders cancelled [0, 1]
    avg_delivery_delay_min : float  mean delay experienced (minutes > ETA)
    avg_user_rating        : float  mean rating the user gives restaurants [1-5]
    num_complaints         : int    total complaints filed
    discount_usage_rate    : float  fraction of orders using a discount [0, 1]
    app_sessions_per_week  : float  weekly app opens (engagement proxy)
    preferred_order_hour   : int    most frequent ordering hour [0-23]
    account_age_days       : int    how long the user has been on the platform
    churn                  : int    TARGET -- 1 = churned, 0 = active

    Returns
    -------
    pd.DataFrame with ``n_users`` rows.
    """
    rng = np.random.default_rng(seed)

    user_id = np.arange(1, n_users + 1)

    # -----------------------------------------------------------------------
    # 1. Account age (days) -- uniform 30-730 (1 month to 2 years)
    #    Newer users churn more (haven't formed a habit yet).
    # -----------------------------------------------------------------------
    account_age_days = rng.integers(30, 731, size=n_users)

    # -----------------------------------------------------------------------
    # 2. Order frequency (orders per month, lifetime average)
    #    Heavy users ~8-12/mo, light users ~0.5-2/mo.
    #    Drawn from a gamma to get a right-skewed distribution.
    # -----------------------------------------------------------------------
    order_frequency = np.round(rng.gamma(shape=2.0, scale=1.5, size=n_users), 2)
    order_frequency = np.clip(order_frequency, 0.1, 15.0)

    # -----------------------------------------------------------------------
    # 3. Orders in last 30 / 90 days -- derived from frequency + noise
    #    A drop-off (90d >> 30d*3) signals disengagement.
    # -----------------------------------------------------------------------
    orders_last_30d = rng.poisson(lam=order_frequency)
    orders_last_30d = np.clip(orders_last_30d, 0, 40)

    # 90-day count should be roughly 3x the 30-day rate, but with variance
    orders_last_90d = rng.poisson(lam=order_frequency * 3.2)
    orders_last_90d = np.maximum(orders_last_90d, orders_last_30d)
    orders_last_90d = np.clip(orders_last_90d, 0, 120)

    # -----------------------------------------------------------------------
    # 4. Days since last order  (recency)
    #    Active users: 0-10 days.   Disengaged: 20-90+ days.
    # -----------------------------------------------------------------------
    # Start with an exponential decay anchored to frequency
    days_since_last_order = rng.exponential(
        scale=15.0 / (order_frequency + 0.1), size=n_users
    ).astype(int)
    days_since_last_order = np.clip(days_since_last_order, 0, 120)

    # -----------------------------------------------------------------------
    # 5. Average order value (INR)  -- monetary signal
    #    Higher spenders are harder to lose (they value the platform).
    # -----------------------------------------------------------------------
    avg_order_value = np.round(
        rng.lognormal(mean=5.5, sigma=0.4, size=n_users), 2
    )
    avg_order_value = np.clip(avg_order_value, 80.0, 1500.0)

    # -----------------------------------------------------------------------
    # 6. Cancellation rate  [0, 1]
    #    High cancellation -> frustration -> churn.
    # -----------------------------------------------------------------------
    cancellation_rate = np.round(rng.beta(1.5, 15, size=n_users), 4)

    # -----------------------------------------------------------------------
    # 7. Average delivery delay experienced (minutes above ETA)
    #    Chronic delays destroy trust.  Most users see 0-5 min; some 10-25.
    # -----------------------------------------------------------------------
    avg_delivery_delay_min = np.round(
        rng.exponential(scale=4.0, size=n_users), 1
    )
    avg_delivery_delay_min = np.clip(avg_delivery_delay_min, 0.0, 30.0)

    # -----------------------------------------------------------------------
    # 8. Average user rating given to restaurants [1.0 - 5.0]
    #    Unhappy users rate lower AND are more likely to churn.
    # -----------------------------------------------------------------------
    avg_user_rating = np.round(
        rng.normal(loc=3.8, scale=0.6, size=n_users), 1
    )
    avg_user_rating = np.clip(avg_user_rating, 1.0, 5.0)

    # -----------------------------------------------------------------------
    # 9. Number of complaints filed (lifetime)
    #    Each complaint doubles churn risk in our formula.
    # -----------------------------------------------------------------------
    num_complaints = rng.poisson(lam=1.2, size=n_users)
    num_complaints = np.clip(num_complaints, 0, 15)

    # -----------------------------------------------------------------------
    # 10. Discount usage rate  [0, 1]
    #     Heavy discount users are price-sensitive -- they churn when
    #     discounts dry up.  But moderate usage signals engagement.
    # -----------------------------------------------------------------------
    discount_usage_rate = np.round(rng.beta(2, 5, size=n_users), 4)

    # -----------------------------------------------------------------------
    # 11. App sessions per week  (engagement)
    #     More sessions = stickier user.
    # -----------------------------------------------------------------------
    app_sessions_per_week = np.round(
        rng.gamma(shape=2.5, scale=1.8, size=n_users), 1
    )
    app_sessions_per_week = np.clip(app_sessions_per_week, 0.0, 30.0)

    # -----------------------------------------------------------------------
    # 12. Preferred ordering hour [0-23]
    #     Captures time-of-day pattern (lunch / dinner peaks).
    # -----------------------------------------------------------------------
    preferred_order_hour = rng.choice(
        range(24), size=n_users,
        p=_hour_prior()
    )

    # ===================================================================
    # TARGET: churn label
    # ===================================================================
    # Logistic model: P(churn) = sigmoid(z)
    #   z combines all risk factors with business-calibrated weights.
    z = (
        + 0.06 * days_since_last_order        # recency (strongest signal)
        - 0.30 * order_frequency              # frequency protects
        - 0.002 * avg_order_value             # monetary value protects
        + 3.00 * cancellation_rate            # cancellations are toxic
        + 0.08 * avg_delivery_delay_min       # chronic delays push users away
        - 0.40 * (avg_user_rating - 3.0)     # low satisfaction -> churn
        + 0.25 * num_complaints               # complaints signal frustration
        - 0.10 * app_sessions_per_week        # engagement protects
        - 0.005 * account_age_days            # tenure builds habit
        + 0.80 * (discount_usage_rate > 0.5).astype(float)  # discount-dependent
        + 0.8                                 # intercept (tuned for ~25 % churn)
    )
    # Add noise so the label isn't perfectly deterministic
    z += rng.normal(0, 0.5, size=n_users)
    churn_prob = 1.0 / (1.0 + np.exp(-z))
    churn = (rng.random(n_users) < churn_prob).astype(int)

    # -----------------------------------------------------------------------
    # Assemble DataFrame
    # -----------------------------------------------------------------------
    df = pd.DataFrame({
        "user_id":                user_id,
        "orders_last_30d":        orders_last_30d,
        "orders_last_90d":        orders_last_90d,
        "avg_order_value":        avg_order_value,
        "days_since_last_order":  days_since_last_order,
        "order_frequency":        order_frequency,
        "cancellation_rate":      cancellation_rate,
        "avg_delivery_delay_min": avg_delivery_delay_min,
        "avg_user_rating":        avg_user_rating,
        "num_complaints":         num_complaints,
        "discount_usage_rate":    discount_usage_rate,
        "app_sessions_per_week":  app_sessions_per_week,
        "preferred_order_hour":   preferred_order_hour,
        "account_age_days":       account_age_days,
        "churn":                  churn,
    })

    # Inject ~3 % missing values in select columns (realistic data quality)
    _inject_missing(df, rng, frac=0.03, cols=[
        "avg_order_value", "avg_delivery_delay_min",
        "avg_user_rating", "app_sessions_per_week",
    ])

    if save:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"[dataset_generator] Saved {len(df)} users -> {OUTPUT_FILE}")

    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hour_prior():
    """Return a 24-element probability vector mimicking ordering patterns."""
    # Peaks at lunch (12-13) and dinner (19-21)
    p = np.array([
        0.005, 0.003, 0.002, 0.002, 0.003, 0.005,   # 0-5
        0.010, 0.020, 0.035, 0.040, 0.045, 0.060,   # 6-11
        0.080, 0.070, 0.050, 0.040, 0.045, 0.055,   # 12-17
        0.070, 0.090, 0.095, 0.080, 0.050, 0.020,   # 18-23
    ])
    return p / p.sum()


def _inject_missing(df, rng, frac, cols):
    """Set ~frac of values to NaN in selected columns."""
    n = len(df)
    for col in cols:
        mask = rng.random(n) < frac
        df.loc[mask, col] = np.nan


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    df = generate_dataset()
    print(df.describe().round(3))
    print(f"\nChurn distribution:\n{df['churn'].value_counts()}")
    print(f"Churn rate: {df['churn'].mean()*100:.1f}%")
    print(f"Missing values:\n{df.isnull().sum()}")
