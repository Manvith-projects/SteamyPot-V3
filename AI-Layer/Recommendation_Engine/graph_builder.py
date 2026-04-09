"""
graph_builder.py — Trust-Aware Social Graph Construction (Optimised)

Provides multiple trust computation strategies for a user–user social graph:

    1. BASIC:   Trust(u,v) = |common restaurants|
    2. COSINE:  Trust(u,v) = alpha * common + beta * cosine_similarity(u,v)
    3. FULL:    Same as COSINE, but computed on a temporally-decayed
                user–restaurant interaction matrix.
    4. LOCATION: Same as FULL + gamma * geographic_proximity(u,v)

Performance optimisations (AMD Ryzen 7 PRO 2700U — 4C/8T, 16 GB):
    - Sparse matrix dot-product replaces O(R × U_r²) inverted-index loop.
    - SparseGraph replaces NetworkX (avoids 25M+ edge Python objects).
    - triu + threshold in CSR before COO to avoid full-matrix materialisation.
    - Interaction matrices stay sparse (CSR) to cut memory & compute.
    - Cosine similarity computed via sparse dot + norm vectors.
"""

import numpy as np
import pandas as pd
import networkx as nx
from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
from scipy.sparse import csr_matrix, coo_matrix, triu
import multiprocessing as mp
import os


# ---------------------------------------------------------------------------
# Lightweight sparse graph that replaces NetworkX for large user counts.
# Implements the dict-of-dict interface the recommender expects:
#   graph[user_id]  → {neighbour_id: {"weight": w}, ...}
#   graph.degree(uid)
#   user_id in graph
#   graph.number_of_nodes() / number_of_edges()
# ---------------------------------------------------------------------------

class SparseGraph:
    """CSR-backed graph with NetworkX-compatible API for the recommender."""

    def __init__(self, users: np.ndarray, co_upper: csr_matrix):
        """
        Parameters
        ----------
        users : sorted array of user IDs
        co_upper : CSR matrix (upper triangle, already thresholded)
        """
        self._users = users
        self._uid_to_idx = {int(u): i for i, u in enumerate(users)}
        # Make symmetric so row lookup gives ALL neighbours
        self._sym = (co_upper + co_upper.T).tocsr()
        self._n_edges = co_upper.nnz  # count before symmetrisation

    # -- dict-of-dict interface ------------------------------------------
    def __contains__(self, user_id: int) -> bool:
        return int(user_id) in self._uid_to_idx

    def __getitem__(self, user_id: int) -> dict:
        idx = self._uid_to_idx.get(int(user_id))
        if idx is None:
            return {}
        row = self._sym.getrow(idx)
        return {
            int(self._users[j]): {"weight": float(w)}
            for j, w in zip(row.indices, row.data)
        }

    # -- degree ----------------------------------------------------------
    def degree(self, user_id: int) -> int:
        idx = self._uid_to_idx.get(int(user_id))
        if idx is None:
            return 0
        return int(self._sym.indptr[idx + 1] - self._sym.indptr[idx])

    # -- stats -----------------------------------------------------------
    def number_of_nodes(self) -> int:
        return len(self._users)

    def number_of_edges(self) -> int:
        return self._n_edges


# ---------------------------------------------------------------------------
# User–restaurant interaction matrices (vectorised)
# ---------------------------------------------------------------------------

def build_interaction_matrix(orders_df: pd.DataFrame,
                             user_ids: np.ndarray,
                             restaurant_ids: np.ndarray) -> csr_matrix:
    """
    Build a sparse binary user×restaurant interaction matrix (vectorised).
    Returns CSR sparse matrix to save memory and speed up cosine/dot ops.
    """
    uid_to_idx = {int(u): i for i, u in enumerate(user_ids)}
    rid_to_idx = {int(r): j for j, r in enumerate(restaurant_ids)}

    uids = orders_df["user_id"].values
    rids = orders_df["restaurant_id"].values

    ui = np.array([uid_to_idx.get(int(u), -1) for u in uids])
    rj = np.array([rid_to_idx.get(int(r), -1) for r in rids])
    valid = (ui >= 0) & (rj >= 0)
    ui, rj = ui[valid], rj[valid]

    data = np.ones(len(ui), dtype=np.float32)
    M = csr_matrix((data, (ui, rj)),
                   shape=(len(user_ids), len(restaurant_ids)))
    # Binary: clip duplicates
    M.data[:] = 1.0
    M.eliminate_zeros()
    return M


def build_decayed_interaction_matrix(orders_df: pd.DataFrame,
                                     user_ids: np.ndarray,
                                     restaurant_ids: np.ndarray,
                                     decay_lambda: float = 0.05,
                                     reference_date: pd.Timestamp = None
                                     ) -> csr_matrix:
    """
    Build a temporally-decayed user×restaurant interaction matrix (sparse).
    Weights are summed for repeated (user, restaurant) pairs.
    """
    uid_to_idx = {int(u): i for i, u in enumerate(user_ids)}
    rid_to_idx = {int(r): j for j, r in enumerate(restaurant_ids)}

    timestamps = pd.to_datetime(orders_df["timestamp"])
    if reference_date is None:
        reference_date = timestamps.max()

    days_ago = (reference_date - timestamps).dt.total_seconds().values / 86400.0
    weights = np.exp(-decay_lambda * days_ago).astype(np.float32)

    uids = orders_df["user_id"].values
    rids = orders_df["restaurant_id"].values

    ui = np.array([uid_to_idx.get(int(u), -1) for u in uids])
    rj = np.array([rid_to_idx.get(int(r), -1) for r in rids])
    valid = (ui >= 0) & (rj >= 0)
    ui, rj, weights = ui[valid], rj[valid], weights[valid]

    M = csr_matrix(
        (weights, (ui, rj)),
        shape=(len(user_ids), len(restaurant_ids)),
    )
    return M


# ---------------------------------------------------------------------------
# Cosine similarity computation
# ---------------------------------------------------------------------------

def compute_cosine_similarity(M) -> csr_matrix:
    """
    Compute pairwise cosine similarity from a sparse interaction matrix.
    Returns a sparse matrix (only stores non-zero similarities).
    Uses sklearn's cosine_similarity which handles sparse input efficiently.
    """
    return cosine_similarity(M, dense_output=False)


# ---------------------------------------------------------------------------
# Location proximity computation
# ---------------------------------------------------------------------------

def compute_location_proximity(users_df: pd.DataFrame,
                               user_ids: np.ndarray,
                               sigma: float = 0.02) -> np.ndarray:
    """
    Compute pairwise location proximity between users (vectorised).
    proximity(u, v) = exp(-euclidean_distance(coords_u, coords_v) / sigma)
    """
    uid_to_idx = {int(u): i for i, u in enumerate(user_ids)}
    n = len(user_ids)
    coords = np.zeros((n, 2), dtype=np.float32)

    # Vectorised coordinate lookup
    udf_uids = users_df["user_id"].values
    udf_lats = users_df["latitude"].values
    udf_lons = users_df["longitude"].values
    for i in range(len(udf_uids)):
        idx = uid_to_idx.get(int(udf_uids[i]))
        if idx is not None:
            coords[idx] = [udf_lats[i], udf_lons[i]]

    dist = euclidean_distances(coords)
    return np.exp(-dist / sigma)


# ---------------------------------------------------------------------------
# Social graph construction
# ---------------------------------------------------------------------------

def build_social_graph(orders_df: pd.DataFrame,
                       min_common: int = 5) -> SparseGraph:
    """
    Build the basic social graph.  Edge weight = number of common restaurants.

    Returns a SparseGraph (CSR-backed, NetworkX-compatible API) instead of
    a full nx.Graph, avoiding the creation of 25M+ Python edge objects.
    """
    import time
    t0 = time.time()

    users = np.sort(orders_df["user_id"].unique())
    restaurants = np.sort(orders_df["restaurant_id"].unique())

    uid_to_idx = {int(u): i for i, u in enumerate(users)}
    rid_to_idx = {int(r): j for j, r in enumerate(restaurants)}

    print(f"    [graph] Building interaction matrix ({len(users)} users × {len(restaurants)} restaurants)...")

    # Build sparse binary interaction matrix
    uids = orders_df["user_id"].values
    rids = orders_df["restaurant_id"].values
    ui = np.array([uid_to_idx[int(u)] for u in uids])
    rj = np.array([rid_to_idx[int(r)] for r in rids])
    data = np.ones(len(ui), dtype=np.float32)
    M = csr_matrix((data, (ui, rj)), shape=(len(users), len(restaurants)))
    M.data[:] = 1.0  # binary

    t1 = time.time()
    print(f"    [graph] Interaction matrix built ({t1-t0:.1f}s). Computing co-occurrence M @ M.T ...")

    # Sparse M @ M.T gives pairwise shared-restaurant counts
    co = M.dot(M.T)  # sparse × sparse → sparse (CSR)

    t2 = time.time()
    print(f"    [graph] Co-occurrence computed ({t2-t1:.1f}s, nnz={co.nnz:,}). Filtering edges...")

    # Upper triangle only (skip diagonal / self-loops), stay in CSR
    co = triu(co, k=1, format='csr')
    # Threshold: zero out entries below min_common BEFORE symmetrisation
    co.data[co.data < min_common] = 0
    co.eliminate_zeros()

    t3 = time.time()
    print(f"    [graph] After triu+threshold: {co.nnz:,} edges ({t3-t2:.1f}s). Wrapping SparseGraph...")

    G = SparseGraph(users, co)

    t4 = time.time()
    print(f"    [graph] Done: {G.number_of_nodes()} nodes, {G.number_of_edges():,} edges ({t4-t0:.1f}s total)")
    return G


def build_trust_graph(orders_df: pd.DataFrame,
                      restaurants_df: pd.DataFrame,
                      strategy: str = "trust_basic",
                      alpha: float = 1.0,
                      beta: float = 1.0,
                      gamma: float = 0.5,
                      decay_lambda: float = 0.05,
                      min_common: int = 5,
                      users_df: pd.DataFrame = None) -> dict:
    """
    Master builder: constructs the social graph and all auxiliary data
    structures needed by the evaluator and recommender.

    Returns dict with graph, matrices, pair_shared, etc.
    """
    import time as _t
    t0 = _t.time()

    users = np.sort(orders_df["user_id"].unique())
    restaurants = np.sort(restaurants_df["restaurant_id"].unique())
    uid_to_idx = {int(u): i for i, u in enumerate(users)}
    rid_to_idx = {int(r): j for j, r in enumerate(restaurants)}

    # ---- Sparse co-occurrence via M @ M.T ----
    uids = orders_df["user_id"].values
    rids = orders_df["restaurant_id"].values
    ui = np.array([uid_to_idx[int(u)] for u in uids])
    rj = np.array([rid_to_idx[int(r)] for r in rids])
    data_ones = np.ones(len(ui), dtype=np.float32)
    M = csr_matrix((data_ones, (ui, rj)), shape=(len(users), len(restaurants)))
    M.data[:] = 1.0  # binary

    t1 = _t.time()
    print(f"    [trust] Interaction matrix ({len(users)} × {len(restaurants)}) in {t1-t0:.1f}s")

    co = M.dot(M.T)  # sparse co-occurrence counts

    t2 = _t.time()
    print(f"    [trust] Co-occurrence M@M.T in {t2-t1:.1f}s (nnz={co.nnz:,})")

    # Upper triangle + threshold in CSR BEFORE COO conversion
    co = triu(co, k=1, format='csr')
    co.data[co.data < min_common] = 0
    co.eliminate_zeros()
    co_coo = co.tocoo()

    edge_rows = co_coo.row
    edge_cols = co_coo.col
    edge_common = co_coo.data

    print(f"    [trust] {len(edge_rows):,} candidate edges (min_common={min_common})")

    # ---- Compute cosine similarity matrix if needed ----
    cosine_mat = None
    interaction_M = None

    if strategy in ("trust_cosine", "trust_full", "trust_location"):
        if strategy in ("trust_full", "trust_location"):
            interaction_M = build_decayed_interaction_matrix(
                orders_df, users, restaurants, decay_lambda=decay_lambda
            )
        else:
            interaction_M = build_interaction_matrix(
                orders_df, users, restaurants
            )
        cosine_mat = compute_cosine_similarity(interaction_M)

    # ---- Compute location proximity if needed ----
    proximity_mat = None
    if strategy == "trust_location":
        if users_df is None:
            raise ValueError("trust_location strategy requires users_df")
        proximity_mat = compute_location_proximity(users_df, users)

    # ---- Build graph ----
    if strategy == "trust_basic":
        # Use SparseGraph directly — co already has the right weights
        G = SparseGraph(users, co)
    else:
        # For cosine/location strategies, we need to reweight edges
        # Use COO to iterate (still 25M+ but only for advanced strategies)
        co_coo = co.tocoo()
        edge_rows = co_coo.row
        edge_cols = co_coo.col
        edge_common = co_coo.data

        if strategy in ("trust_cosine", "trust_full"):
            cos_vals = np.array([cosine_mat[edge_rows[i], edge_cols[i]]
                                 for i in range(len(edge_rows))], dtype=np.float64)
            weights = alpha * edge_common + beta * cos_vals
        elif strategy == "trust_location":
            cos_vals = np.array([cosine_mat[edge_rows[i], edge_cols[i]]
                                 for i in range(len(edge_rows))], dtype=np.float64)
            prox_vals = np.array([proximity_mat[edge_rows[i], edge_cols[i]]
                                  for i in range(len(edge_rows))], dtype=np.float64)
            weights = alpha * edge_common + beta * cos_vals + gamma * prox_vals
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        # Build a new CSR with the reweighted values
        reweighted = csr_matrix(
            (weights, (edge_rows, edge_cols)),
            shape=(len(users), len(users))
        )
        G = SparseGraph(users, reweighted)

    # Build pair_shared dict for evaluator compatibility (from COO of co)
    co_coo2 = co.tocoo()
    pair_shared = {
        (int(users[co_coo2.row[i]]), int(users[co_coo2.col[i]])): int(co_coo2.data[i])
        for i in range(co_coo2.nnz)
    }

    t3 = _t.time()
    print(f"    [trust] Done: {G.number_of_nodes()} nodes, {G.number_of_edges():,} edges ({t3-t0:.1f}s total)")

    return {
        "graph": G,
        "user_ids": users,
        "restaurant_ids": restaurants,
        "uid_to_idx": uid_to_idx,
        "cosine_matrix": cosine_mat,
        "interaction_M": interaction_M,
        "proximity_matrix": proximity_mat,
        "pair_shared": pair_shared,
        "strategy": strategy,
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "decay_lambda": decay_lambda,
    }