"""
evaluator.py — Publication-Level Ablation Study for Trust-Aware Social Recommendation

Runs Leave-One-Out evaluation across five recommendation strategies:

    1. Popularity        — non-personalised baseline (globally popular items)
    2. Trust Basic       — Trust(u,v) = |common restaurants|
    3. Trust + Cosine    — Trust(u,v) = alpha * common + beta * cos_sim (binary)
    4. Trust + Cos+Decay — Trust(u,v) = alpha * common + beta * cos_sim (decayed)
    5. Trust + Location  — Trust(u,v) = alpha * common + beta * cos_sim + gamma * prox

Metrics:
    - Precision@K, Recall@K, NDCG@K (per-user, then averaged)
    - Paired t-test for statistical significance

Experiments:
    - Full ablation study across all 5 strategies
    - Hyperparameter sensitivity analysis (alpha, beta, gamma, lambda)
    - Cold-start experiment (users with 3-5 orders)
    - Cross-zone mobility experiment

Architecture & Scalability:
    - Shared data structures computed ONCE in __init__.
    - Incremental graph patching for LOO (O(U_r) per user).
    - Zero DataFrame operations inside evaluation loops.
"""

import time
import math
import pandas as pd
import numpy as np
import networkx as nx
from collections import defaultdict
from scipy import stats

from graph_builder import build_trust_graph
from recommender import (
    recommend_popularity,
    recommend_trust,
    recommend_trust_full,
)


# ---------------------------------------------------------------------------
# Strategy registry — (strategy_key, display_label)
# ---------------------------------------------------------------------------

STRATEGIES = [
    ("popularity",      "Popularity"),
    ("trust_basic",     "Trust Basic"),
    ("trust_cosine",    "Trust + Cosine"),
    ("trust_full",      "Trust + Cosine + Decay"),
    ("trust_location",  "Trust + Full + Location"),
]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def precision_at_k(recommended: list, actual: list, k: int = 5) -> float:
    """Proportion of top-K recommendations that appear in the actual set."""
    top_k = recommended[:k]
    hits = len(set(top_k) & set(actual))
    return hits / k


def recall_at_k(recommended: list, actual: list, k: int = 5) -> float:
    """
    Proportion of relevant items found in top-K.
    In LOO (single held-out item): 1.0 if hit, 0.0 if miss.
    """
    if not actual:
        return 0.0
    top_k = recommended[:k]
    hits = len(set(top_k) & set(actual))
    return hits / len(actual)


def ndcg_at_k(recommended: list, actual: list, k: int = 5) -> float:
    """
    Normalised Discounted Cumulative Gain at K.

    In LOO (single held-out item), IDCG = 1.0, so:
        NDCG@K = 1/log2(rank+1) if hit at position rank (1-indexed)
        NDCG@K = 0.0 if no hit in top-K.

    For multi-item actual sets, computes full DCG/IDCG.
    """
    top_k = recommended[:k]
    actual_set = set(actual)

    # DCG
    dcg = 0.0
    for i, item in enumerate(top_k):
        if item in actual_set:
            dcg += 1.0 / math.log2(i + 2)  # i+2 because rank is 1-indexed

    # IDCG (ideal: all relevant items at top positions)
    n_relevant = min(len(actual_set), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_relevant))

    return dcg / idcg if idcg > 0 else 0.0


# ---------------------------------------------------------------------------
# Ablation Evaluator
# ---------------------------------------------------------------------------

class AblationEvaluator:
    """
    Leave-One-Out evaluator that runs an ablation study across all four
    recommendation strategies.

    Heavy data structures are shared; each strategy only builds its own
    trust graph and (optionally) cosine / decay matrices once.  The LOO
    loop uses incremental graph patching — the same O(U_r)-per-user
    technique from the previous evaluator, generalised to support
    strategy-specific edge-weight formulas.
    """

    # ------------------------------------------------------------------
    # Initialisation: build all SHARED data structures once
    # ------------------------------------------------------------------

    def __init__(self, orders_df: pd.DataFrame,
                 restaurants_df: pd.DataFrame,
                 users_df: pd.DataFrame = None,
                 k: int = 5,
                 min_orders: int = 3,
                 alpha: float = 1.0,
                 beta: float = 1.0,
                 gamma: float = 0.5,
                 decay_lambda: float = 0.05):
        """
        Parameters
        ----------
        alpha : float   Weight for common-visit component in trust formula.
        beta  : float   Weight for cosine-similarity component.
        gamma : float   Weight for location-proximity component.
        decay_lambda : float  Temporal decay rate  (trust_full only).
        """
        self.k = k
        self.min_orders = min_orders
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.decay_lambda = decay_lambda
        self.restaurants_df = restaurants_df
        self.users_df = users_df

        # ---- 1. Sort orders chronologically (deterministic splits) ----
        self.orders = orders_df.copy()
        self.orders["timestamp"] = pd.to_datetime(self.orders["timestamp"])
        self.orders.sort_values("timestamp", inplace=True)
        self.orders.reset_index(drop=True, inplace=True)

        self.users = self.orders["user_id"].unique()

        # ---- 2. Shared lookup structures (one-time cost) ----

        # user → set of distinct restaurants
        self.user_restaurants: dict[int, set] = (
            self.orders.groupby("user_id")["restaurant_id"]
            .apply(set).to_dict()
        )

        # user → list of restaurants WITH duplicates (count-based scoring)
        self.user_order_list: dict[int, list] = (
            self.orders.groupby("user_id")["restaurant_id"]
            .apply(list).to_dict()
        )

        # (user, restaurant) → order count
        self.user_rest_counts: dict[tuple, int] = (
            self.orders.groupby(["user_id", "restaurant_id"])
            .size().to_dict()
        )

        # restaurant → set of users  (inverted index)
        self.restaurant_users: dict[int, set] = (
            self.orders.groupby("restaurant_id")["user_id"]
            .apply(set).to_dict()
        )

        # ---- 3. Pairwise shared-restaurant counts (inverted index) ----
        self.pair_shared: dict[tuple, int] = defaultdict(int)
        for _rest, visitors in self.restaurant_users.items():
            vlist = sorted(visitors)
            for i in range(len(vlist)):
                for j in range(i + 1, len(vlist)):
                    self.pair_shared[(vlist[i], vlist[j])] += 1

        # ---- 4. Global popularity ranking ----
        self.global_popularity: list[int] = (
            self.orders["restaurant_id"]
            .value_counts()
            .index.tolist()
        )

        # ---- 5. Identify each user's held-out test item ----
        self.test_items: dict[int, int] = {}
        for user in self.users:
            user_orders = self.orders[self.orders["user_id"] == user]
            if len(user_orders) >= self.min_orders:
                self.test_items[user] = int(user_orders.iloc[-1]["restaurant_id"])

    # ------------------------------------------------------------------
    # Build per-strategy graph + auxiliary data
    # ------------------------------------------------------------------

    def _build_strategy(self, strategy: str) -> dict | None:
        """
        Build the trust graph and any auxiliary structures for a strategy.

        Returns None for 'popularity' (no graph needed).
        For trust strategies, returns the dict from build_trust_graph plus
        an optional 'user_order_weighted' mapping for trust_full.
        """
        if strategy == "popularity":
            return None

        graph_data = build_trust_graph(
            self.orders, self.restaurants_df,
            strategy=strategy,
            alpha=self.alpha,
            beta=self.beta,
            gamma=self.gamma,
            decay_lambda=self.decay_lambda,
            users_df=self.users_df,
        )

        # For trust_full / trust_location: pre-compute per-user decayed
        # restaurant weights from the interaction matrix.
        if strategy in ("trust_full", "trust_location") and graph_data["interaction_M"] is not None:
            M = graph_data["interaction_M"]
            uids = graph_data["user_ids"]
            rids = graph_data["restaurant_ids"]
            uid_to_idx = graph_data["uid_to_idx"]

            user_order_weighted: dict[int, dict[int, float]] = {}
            for uid in uids:
                uid_int = int(uid)
                row = M[uid_to_idx[uid_int]]
                d = {}
                for j, w in enumerate(row):
                    if w > 0.0:
                        d[int(rids[j])] = float(w)
                user_order_weighted[uid_int] = d

            graph_data["user_order_weighted"] = user_order_weighted
        else:
            graph_data["user_order_weighted"] = None

        return graph_data

    # ------------------------------------------------------------------
    # Strategy-aware edge-weight computation
    # ------------------------------------------------------------------

    def _compute_edge_weight(self, strategy: str, common_count: int,
                             u1: int, u2: int,
                             graph_data: dict) -> float:
        """
        Compute the trust edge weight for a (u1, u2) pair under the
        given strategy, using the current common_count.

        For trust_basic : weight = common_count
        For trust_cosine / trust_full :
            weight = alpha * common_count + beta * cosine_sim(u1, u2)

        The cosine_matrix is read from graph_data (pre-computed once).
        """
        if strategy == "trust_basic":
            return float(common_count)

        i1 = graph_data["uid_to_idx"][int(u1)]
        i2 = graph_data["uid_to_idx"][int(u2)]
        cos_sim = graph_data["cosine_matrix"][i1, i2]

        if strategy in ("trust_cosine", "trust_full"):
            return self.alpha * common_count + self.beta * cos_sim

        if strategy == "trust_location":
            prox = graph_data["proximity_matrix"][i1, i2]
            return self.alpha * common_count + self.beta * cos_sim + self.gamma * prox

        return self.alpha * common_count + self.beta * cos_sim

    # ------------------------------------------------------------------
    # Incremental graph patch / restore (strategy-aware)
    # ------------------------------------------------------------------

    def _patch_graph(self, user: int, test_restaurant: int,
                     G: nx.Graph, strategy: str,
                     graph_data: dict) -> list[tuple]:
        """
        Temporarily remove the effect of one held-out order from the graph.

        If the user has multiple orders at the test restaurant, their
        restaurant set is unchanged → no graph modification needed.

        Otherwise, for each co-visitor v of the test restaurant:
            - Decrement pair_shared[(user, v)] by 1
            - If the count drops from >= 3 to < 3 → remove the edge
            - If the count stays >= 3 → update the edge weight using
              the strategy-specific formula

        Returns a changelist for _restore_graph.
        """
        changes: list[tuple] = []

        # Multiple orders at this restaurant → removing one doesn't change
        # the user's restaurant set → graph stays the same.
        if self.user_rest_counts.get((user, test_restaurant), 0) > 1:
            return changes

        affected = self.restaurant_users.get(test_restaurant, set()) - {user}

        for v in affected:
            pair = (min(user, v), max(user, v))
            old_shared = self.pair_shared[pair]
            new_shared = old_shared - 1
            self.pair_shared[pair] = new_shared

            had_edge = old_shared > 2       # >= 3 common restaurants
            keeps_edge = new_shared > 2

            if had_edge and not keeps_edge:
                # Edge threshold crossed → remove edge entirely
                if G.has_edge(user, v):
                    old_weight = G[user][v]["weight"]
                    changes.append(("remove", user, v, old_weight))
                    G.remove_edge(user, v)

            elif had_edge and keeps_edge:
                # Edge persists but weight must be recomputed
                if G.has_edge(user, v):
                    old_weight = G[user][v]["weight"]
                    new_weight = self._compute_edge_weight(
                        strategy, new_shared, user, v, graph_data
                    )
                    changes.append(("decrease", user, v, old_weight))
                    G[user][v]["weight"] = new_weight

        return changes

    def _restore_graph(self, user: int, test_restaurant: int,
                       G: nx.Graph, changes: list[tuple]) -> None:
        """Undo all modifications made by _patch_graph."""
        if self.user_rest_counts.get((user, test_restaurant), 0) > 1:
            return

        # Restore pair_shared counts
        affected = self.restaurant_users.get(test_restaurant, set()) - {user}
        for v in affected:
            pair = (min(user, v), max(user, v))
            self.pair_shared[pair] += 1

        # Restore graph edges / weights
        for action, u, v, old_weight in changes:
            if action == "remove":
                G.add_edge(u, v, weight=old_weight)
            elif action == "decrease":
                G[u][v]["weight"] = old_weight

    # ------------------------------------------------------------------
    # Per-user recommendation dispatch (zero DataFrame ops)
    # ------------------------------------------------------------------

    def _get_training_visited(self, user: int,
                              test_restaurant: int) -> set[int]:
        """
        Return the set of restaurants this user visited in training data
        (i.e., excluding the test restaurant if it was their only order).
        """
        visited = set(self.user_restaurants.get(user, set()))
        if self.user_rest_counts.get((user, test_restaurant), 0) == 1:
            visited.discard(test_restaurant)
        return visited

    def _recommend(self, user: int, strategy: str,
                   G: nx.Graph | None, graph_data: dict | None,
                   visited: set[int]) -> list[int]:
        """Dispatch to the correct recommendation function."""
        if strategy == "popularity":
            return recommend_popularity(
                user, self.global_popularity, visited, self.k
            )

        elif strategy in ("trust_basic", "trust_cosine"):
            return recommend_trust(
                user, G, self.user_order_list, self.k
            )

        elif strategy in ("trust_full", "trust_location"):
            return recommend_trust_full(
                user, G, graph_data["user_order_weighted"], self.k
            )

        return []

    # ------------------------------------------------------------------
    # LOO evaluation for a single strategy
    # ------------------------------------------------------------------

    def _evaluate_strategy(self, strategy: str,
                           graph_data: dict | None,
                           user_subset: set | None = None) -> dict:
        """
        Run Leave-One-Out for one strategy.

        For trust strategies, applies incremental graph patching.
        For popularity, just filters already-visited restaurants.

        Parameters
        ----------
        user_subset : set or None
            If provided, only evaluate users in this set (for cold-start etc.).

        Returns dict with 'precision_at_k', 'recall_at_k', 'ndcg_at_k',
        per-user score arrays, 'num_evaluated', 'num_skipped'.
        """
        G = graph_data["graph"] if graph_data else None
        precisions: list[float] = []
        recalls: list[float] = []
        ndcgs: list[float] = []
        skipped = 0

        eval_users = self.users if user_subset is None else [
            u for u in self.users if u in user_subset
        ]

        for user in eval_users:
            if user not in self.test_items:
                skipped += 1
                continue

            test_restaurant = self.test_items[user]
            actual = [test_restaurant]
            visited = self._get_training_visited(user, test_restaurant)

            # --- Patch graph (trust strategies only) ---
            changes = []
            if G is not None:
                changes = self._patch_graph(
                    user, test_restaurant, G, strategy, graph_data
                )

            # --- Generate recommendations ---
            recs = self._recommend(user, strategy, G, graph_data, visited)

            # --- Restore graph ---
            if G is not None:
                self._restore_graph(user, test_restaurant, G, changes)

            # --- Record all metrics ---
            precisions.append(precision_at_k(recs, actual, self.k))
            recalls.append(recall_at_k(recs, actual, self.k))
            ndcgs.append(ndcg_at_k(recs, actual, self.k))

        n = len(precisions)
        return {
            "precision_at_k": float(np.mean(precisions)) if n else 0.0,
            "recall_at_k": float(np.mean(recalls)) if n else 0.0,
            "ndcg_at_k": float(np.mean(ndcgs)) if n else 0.0,
            "precisions": np.array(precisions),
            "recalls": np.array(recalls),
            "ndcgs": np.array(ndcgs),
            "num_evaluated": n,
            "num_skipped": skipped,
        }

    # ------------------------------------------------------------------
    # Full ablation study
    # ------------------------------------------------------------------

    def run_ablation(self, verbose: bool = True,
                     user_subset: set | None = None) -> dict[str, dict]:
        """
        Run Leave-One-Out evaluation for every strategy in STRATEGIES.

        Returns
        -------
        dict  strategy_key → {precision_at_k, recall_at_k, ndcg_at_k,
                               precisions, recalls, ndcgs,
                               num_evaluated, num_skipped,
                               build_time, eval_time}
        """
        results: dict[str, dict] = {}

        for strategy, label in STRATEGIES:
            # ---- Build phase ----
            if verbose:
                print(f"  [{label}] Building ...", end=" ", flush=True)

            t0 = time.time()
            graph_data = self._build_strategy(strategy)
            build_t = time.time() - t0

            if verbose:
                print(f"({build_t:.2f}s)  Evaluating ...", end=" ", flush=True)

            # ---- Evaluation phase ----
            t1 = time.time()
            result = self._evaluate_strategy(strategy, graph_data,
                                             user_subset=user_subset)
            eval_t = time.time() - t1

            result["build_time"] = build_t
            result["eval_time"] = eval_t
            results[strategy] = result

            if verbose:
                print(f"({eval_t:.2f}s)  "
                      f"P@{self.k}={result['precision_at_k']:.4f}  "
                      f"R@{self.k}={result['recall_at_k']:.4f}  "
                      f"NDCG@{self.k}={result['ndcg_at_k']:.4f}")

        return results

    # ------------------------------------------------------------------
    # Paired t-test for statistical significance
    # ------------------------------------------------------------------

    def run_significance_tests(self, results: dict[str, dict],
                               verbose: bool = True) -> dict:
        """
        Run paired t-tests between the best model (trust_location) and
        all other strategies, on NDCG per-user scores.

        Returns dict of (strategy_a, strategy_b) → {t_stat, p_value, significant}
        """
        sig_results = {}
        best_key = "trust_location"
        best_ndcgs = results[best_key]["ndcgs"]

        if verbose:
            print("\n  Paired t-test (vs Trust + Full + Location):")
            print("  " + "-" * 60)
            print(f"  {'Strategy':<28} {'t-stat':>8} {'p-value':>10} {'Sig?':>6}")
            print("  " + "-" * 60)

        for strategy, label in STRATEGIES:
            if strategy == best_key:
                continue

            other_ndcgs = results[strategy]["ndcgs"]

            # Ensure same length (should be unless user_subset differs)
            n = min(len(best_ndcgs), len(other_ndcgs))
            if n < 2:
                continue

            t_stat, p_value = stats.ttest_rel(
                best_ndcgs[:n], other_ndcgs[:n]
            )
            significant = p_value < 0.05

            pair_key = (best_key, strategy)
            sig_results[pair_key] = {
                "t_stat": t_stat,
                "p_value": p_value,
                "significant": significant,
            }

            if verbose:
                sig_mark = "YES" if significant else "no"
                print(f"  {label:<28} {t_stat:>8.3f} {p_value:>10.4e} {sig_mark:>6}")

        if verbose:
            print("  " + "-" * 60)
            print("  (p < 0.05 considered significant)\n")

        return sig_results


# ---------------------------------------------------------------------------
# Hyperparameter Sensitivity Analysis
# ---------------------------------------------------------------------------

def run_sensitivity_analysis(orders_df, restaurants_df, users_df,
                             k=5, min_orders=3, verbose=True):
    """
    Sweep one hyperparameter at a time (holding others at defaults)
    and report NDCG@K for trust_location strategy.

    Sweeps:
        alpha  ∈ [0.0, 0.5, 1.0, 1.5, 2.0]
        beta   ∈ [0.0, 0.5, 1.0, 1.5, 2.0]
        gamma  ∈ [0.0, 0.25, 0.5, 0.75, 1.0]
        lambda ∈ [0.01, 0.03, 0.05, 0.07, 0.10]

    Returns dict of param_name → list of (value, ndcg) tuples.
    """
    defaults = {"alpha": 1.0, "beta": 1.0, "gamma": 0.5, "decay_lambda": 0.05}

    sweeps = {
        "alpha":        [0.0, 0.5, 1.0, 1.5, 2.0],
        "beta":         [0.0, 0.5, 1.0, 1.5, 2.0],
        "gamma":        [0.0, 0.25, 0.5, 0.75, 1.0],
        "decay_lambda": [0.01, 0.03, 0.05, 0.07, 0.10],
    }

    sensitivity_results = {}

    for param_name, values in sweeps.items():
        if verbose:
            print(f"\n  Sweeping {param_name}:")
            print(f"  {'Value':>8} {'P@'+str(k):>10} {'NDCG@'+str(k):>10}")
            print("  " + "-" * 32)

        param_results = []
        for val in values:
            params = dict(defaults)
            params[param_name] = val

            evaluator = AblationEvaluator(
                orders_df, restaurants_df,
                users_df=users_df,
                k=k, min_orders=min_orders,
                alpha=params["alpha"],
                beta=params["beta"],
                gamma=params["gamma"],
                decay_lambda=params["decay_lambda"],
            )

            # Only build and evaluate trust_location
            graph_data = evaluator._build_strategy("trust_location")
            result = evaluator._evaluate_strategy("trust_location", graph_data)

            param_results.append((val, result["precision_at_k"],
                                  result["ndcg_at_k"]))

            if verbose:
                print(f"  {val:>8.3f} {result['precision_at_k']:>10.4f} "
                      f"{result['ndcg_at_k']:>10.4f}")

        sensitivity_results[param_name] = param_results

    return sensitivity_results


# ---------------------------------------------------------------------------
# Cold-Start Experiment
# ---------------------------------------------------------------------------

def run_cold_start_experiment(orders_df, restaurants_df, users_df,
                              k=5, alpha=1.0, beta=1.0, gamma=0.5,
                              decay_lambda=0.05, verbose=True):
    """
    Evaluate recommendation quality for cold-start users (3-5 orders)
    vs warm users (>5 orders).

    Returns dict with 'cold' and 'warm' ablation results.
    """
    # Count orders per user
    user_order_counts = orders_df.groupby("user_id").size()
    cold_users = set(user_order_counts[
        (user_order_counts >= 3) & (user_order_counts <= 5)
    ].index)
    warm_users = set(user_order_counts[user_order_counts > 5].index)

    if verbose:
        print(f"\n  Cold-start users (3-5 orders): {len(cold_users)}")
        print(f"  Warm users (>5 orders):        {len(warm_users)}")

    evaluator = AblationEvaluator(
        orders_df, restaurants_df,
        users_df=users_df,
        k=k, min_orders=3,
        alpha=alpha, beta=beta, gamma=gamma,
        decay_lambda=decay_lambda,
    )

    results = {}

    for group_name, user_set in [("cold", cold_users), ("warm", warm_users)]:
        if verbose:
            print(f"\n  --- {group_name.upper()} users ({len(user_set)}) ---")
        ablation = evaluator.run_ablation(verbose=verbose, user_subset=user_set)
        results[group_name] = ablation

    return results


# ---------------------------------------------------------------------------
# Cross-Zone Mobility Experiment
# ---------------------------------------------------------------------------

def run_cross_zone_experiment(orders_df, restaurants_df, users_df,
                              k=5, alpha=1.0, beta=1.0, gamma=0.5,
                              decay_lambda=0.05, verbose=True):
    """
    Simulate user mobility: move 20% of users to a different zone and
    compare performance of location-aware vs non-location strategies.

    This tests whether the trust+location model degrades gracefully when
    users' physical locations shift (e.g., someone moves from Downtown
    to Brooklyn but still has Downtown ordering history).
    """
    from dataset_generator import ZONES

    np.random.seed(42)
    all_users = users_df["user_id"].values
    n_move = max(1, int(0.2 * len(all_users)))
    movers = np.random.choice(all_users, size=n_move, replace=False)

    # Create modified users_df with relocated users
    users_modified = users_df.copy()
    zone_names = [z[0] for z in ZONES]
    zone_map = {z[0]: (z[1], z[2]) for z in ZONES}

    moved_count = 0
    for uid in movers:
        mask = users_modified["user_id"] == uid
        current_zone = users_modified.loc[mask, "zone"].values[0]
        # Pick a different zone
        other_zones = [z for z in zone_names if z != current_zone]
        new_zone = np.random.choice(other_zones)
        new_lat, new_lon = zone_map[new_zone]
        users_modified.loc[mask, "zone"] = new_zone
        users_modified.loc[mask, "latitude"] = new_lat + np.random.normal(0, 0.005)
        users_modified.loc[mask, "longitude"] = new_lon + np.random.normal(0, 0.005)
        moved_count += 1

    if verbose:
        print(f"\n  Cross-zone experiment: relocated {moved_count} users")

    mover_set = set(movers)

    # Original evaluation on movers
    evaluator_orig = AblationEvaluator(
        orders_df, restaurants_df,
        users_df=users_df,
        k=k, min_orders=3,
        alpha=alpha, beta=beta, gamma=gamma,
        decay_lambda=decay_lambda,
    )

    # Modified evaluation on movers (with new locations)
    evaluator_moved = AblationEvaluator(
        orders_df, restaurants_df,
        users_df=users_modified,
        k=k, min_orders=3,
        alpha=alpha, beta=beta, gamma=gamma,
        decay_lambda=decay_lambda,
    )

    if verbose:
        print("\n  --- ORIGINAL locations (movers only) ---")
    results_orig = evaluator_orig.run_ablation(verbose=verbose,
                                                user_subset=mover_set)

    if verbose:
        print("\n  --- RELOCATED locations (movers only) ---")
    results_moved = evaluator_moved.run_ablation(verbose=verbose,
                                                  user_subset=mover_set)

    # Print comparison
    if verbose:
        print("\n  Cross-Zone Comparison (relocated users):")
        print("  " + "-" * 72)
        hdr = (f"  {'Strategy':<28} {'Orig NDCG':>10} {'Moved NDCG':>10} "
               f"{'Delta':>8} {'%Change':>8}")
        print(hdr)
        print("  " + "-" * 72)

        for strategy, label in STRATEGIES:
            orig_ndcg = results_orig[strategy]["ndcg_at_k"]
            moved_ndcg = results_moved[strategy]["ndcg_at_k"]
            delta = moved_ndcg - orig_ndcg
            pct = (delta / orig_ndcg * 100) if orig_ndcg > 0 else 0.0
            print(f"  {label:<28} {orig_ndcg:>10.4f} {moved_ndcg:>10.4f} "
                  f"{delta:>8.4f} {pct:>7.1f}%")

        print("  " + "-" * 72)

    return {"original": results_orig, "relocated": results_moved}


# ---------------------------------------------------------------------------
# Pretty-print ablation table (updated for 3 metrics)
# ---------------------------------------------------------------------------

def print_ablation_table(results: dict[str, dict],
                         k: int = 5,
                         total_time: float = 0.0) -> None:
    """Print a clean, publication-ready comparison table with all metrics."""
    sample = next(iter(results.values()))
    n_eval = sample["num_evaluated"]
    n_skip = sample["num_skipped"]

    sep = "=" * 80
    dash = "-" * 80

    print(f"\n{sep}")
    print(f"  ABLATION STUDY  —  LEAVE-ONE-OUT EVALUATION  (K={k})")
    print(sep)
    print(f"  Evaluated users : {n_eval}")
    print(f"  Skipped users   : {n_skip}  (< min_orders)")
    if total_time:
        print(f"  Total wall time : {total_time:.2f}s")
    print(dash)
    hdr = (f"  {'Model':<27} {'P@'+str(k):>8} {'R@'+str(k):>8} "
           f"{'NDCG@'+str(k):>8}  {'Build':>6} {'Eval':>6}")
    print(hdr)
    print(dash)

    best_key = max(results, key=lambda s: results[s]["ndcg_at_k"])

    for strategy, label in STRATEGIES:
        r = results[strategy]
        marker = " *" if strategy == best_key else ""
        print(f"  {label:<27} {r['precision_at_k']:>8.4f} "
              f"{r['recall_at_k']:>8.4f} {r['ndcg_at_k']:>8.4f}  "
              f"{r['build_time']:>5.2f}s {r['eval_time']:>5.2f}s{marker}")

    print(sep)
    print(f"  * = best model (by NDCG@{k})")

    # Improvement summary
    pop_ndcg = results["popularity"]["ndcg_at_k"]
    best_ndcg = results[best_key]["ndcg_at_k"]
    best_label = dict(STRATEGIES)[best_key]
    if pop_ndcg > 0:
        pct = (best_ndcg - pop_ndcg) / pop_ndcg * 100
        print(f"  {best_label} improves over Popularity by "
              f"{best_ndcg - pop_ndcg:.4f} NDCG  (+{pct:.1f}%)")
    print()


# ---------------------------------------------------------------------------
# Hyperparameter summary
# ---------------------------------------------------------------------------

def print_hyperparams(k, alpha, beta, gamma, decay_lambda, min_orders):
    """Print the hyperparameter configuration for reproducibility."""
    print("  Hyperparameters:")
    print(f"    K (top-K)       = {k}")
    print(f"    alpha           = {alpha}")
    print(f"    beta            = {beta}")
    print(f"    gamma           = {gamma}")
    print(f"    decay_lambda    = {decay_lambda}")
    print(f"    min_orders      = {min_orders}")
    print()


# ---------------------------------------------------------------------------
# Main entry point — Full experiment suite
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # ---- Load datasets ----
    orders_df = pd.read_csv("orders.csv")
    restaurants_df = pd.read_csv("restaurants.csv")
    users_df = pd.read_csv("users.csv")

    # ---- Configurable hyperparameters ----
    K             = 5       # Top-K recommendations
    ALPHA         = 1.0     # Weight for common-visit trust component
    BETA          = 1.0     # Weight for cosine-similarity component
    GAMMA         = 0.5     # Weight for location-proximity component
    DECAY_LAMBDA  = 0.05    # Temporal decay rate  (half-life ~ 14 days)
    MIN_ORDERS    = 3       # Minimum orders to include a user
    EVAL_SAMPLE   = 5000    # Sample N users for evaluation (None = all)

    # ---- Print experiment configuration ----
    full_n_users = orders_df["user_id"].nunique()
    full_n_orders = len(orders_df)
    full_n_restaurants = restaurants_df["restaurant_id"].nunique()

    print("=" * 80)
    print("  Trust-Aware Social Recommendation — Full Experiment Suite")
    print("=" * 80)
    print(f"  Full dataset: {full_n_orders:,} orders, "
          f"{full_n_users:,} users, "
          f"{full_n_restaurants:,} restaurants")

    # ---- Sample users for tractable evaluation on large datasets ----
    if EVAL_SAMPLE is not None and full_n_users > EVAL_SAMPLE:
        rng = np.random.default_rng(42)
        all_uids = orders_df["user_id"].unique()
        sampled_uids = set(rng.choice(all_uids, size=EVAL_SAMPLE, replace=False).tolist())
        orders_df = orders_df[orders_df["user_id"].isin(sampled_uids)].reset_index(drop=True)
        users_df = users_df[users_df["user_id"].isin(sampled_uids)].reset_index(drop=True)
        # Keep all restaurants (some may have zero orders — that's fine)
        print(f"  Sampled {EVAL_SAMPLE:,} users → "
              f"{len(orders_df):,} orders for evaluation")
    else:
        print("  Using full dataset for evaluation")

    print()
    print_hyperparams(K, ALPHA, BETA, GAMMA, DECAY_LAMBDA, MIN_ORDERS)

    # ==================================================================
    # EXPERIMENT 1: Full Ablation Study
    # ==================================================================
    print("\n" + "=" * 80)
    print("  EXPERIMENT 1: ABLATION STUDY")
    print("=" * 80)

    t_total = time.time()

    evaluator = AblationEvaluator(
        orders_df, restaurants_df,
        users_df=users_df,
        k=K,
        min_orders=MIN_ORDERS,
        alpha=ALPHA,
        beta=BETA,
        gamma=GAMMA,
        decay_lambda=DECAY_LAMBDA,
    )

    results = evaluator.run_ablation(verbose=True)
    total_time = time.time() - t_total

    print_ablation_table(results, k=K, total_time=total_time)

    # ==================================================================
    # EXPERIMENT 2: Statistical Significance
    # ==================================================================
    print("=" * 80)
    print("  EXPERIMENT 2: STATISTICAL SIGNIFICANCE (Paired t-test)")
    print("=" * 80)

    sig_results = evaluator.run_significance_tests(results, verbose=True)

    # ==================================================================
    # EXPERIMENT 3: Hyperparameter Sensitivity
    # ==================================================================
    print("=" * 80)
    print("  EXPERIMENT 3: HYPERPARAMETER SENSITIVITY ANALYSIS")
    print("=" * 80)

    sensitivity = run_sensitivity_analysis(
        orders_df, restaurants_df, users_df,
        k=K, min_orders=MIN_ORDERS, verbose=True,
    )

    # ==================================================================
    # EXPERIMENT 4: Cold-Start Analysis
    # ==================================================================
    print("\n" + "=" * 80)
    print("  EXPERIMENT 4: COLD-START ANALYSIS")
    print("=" * 80)

    cold_results = run_cold_start_experiment(
        orders_df, restaurants_df, users_df,
        k=K, alpha=ALPHA, beta=BETA, gamma=GAMMA,
        decay_lambda=DECAY_LAMBDA, verbose=True,
    )

    # Print cold-start comparison
    print("\n  Cold-Start vs Warm Comparison:")
    print("  " + "-" * 72)
    hdr = (f"  {'Strategy':<27} {'Cold NDCG':>10} {'Warm NDCG':>10} "
           f"{'Improvement':>12}")
    print(hdr)
    print("  " + "-" * 72)
    for strategy, label in STRATEGIES:
        cold_n = cold_results["cold"][strategy]["ndcg_at_k"]
        warm_n = cold_results["warm"][strategy]["ndcg_at_k"]
        imp = warm_n - cold_n
        print(f"  {label:<27} {cold_n:>10.4f} {warm_n:>10.4f} {imp:>+11.4f}")
    print("  " + "-" * 72)

    # ==================================================================
    # EXPERIMENT 5: Cross-Zone Mobility
    # ==================================================================
    print("\n" + "=" * 80)
    print("  EXPERIMENT 5: CROSS-ZONE MOBILITY")
    print("=" * 80)

    cross_zone = run_cross_zone_experiment(
        orders_df, restaurants_df, users_df,
        k=K, alpha=ALPHA, beta=BETA, gamma=GAMMA,
        decay_lambda=DECAY_LAMBDA, verbose=True,
    )

    # ==================================================================
    # Summary
    # ==================================================================
    total_elapsed = time.time() - t_total
    print("\n" + "=" * 80)
    print(f"  ALL EXPERIMENTS COMPLETE  (total: {total_elapsed:.1f}s)")
    print("=" * 80)