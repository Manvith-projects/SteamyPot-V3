"""
=============================================================================
Graph Neural Network – City Road Network Spatial Embedding
=============================================================================

Builds a Graph Convolutional Network (GCN) that operates on the city road
network graph.  Intersections are nodes; road segments are edges.  The GCN
learns *spatial embeddings* that capture local topology, connectivity, and
road-type composition — features that flat tabular models cannot represent.

Architecture
------------
    Input  :  node features  (lat, lon, degree, n_road_types)
    Layer 1:  GCNConv → ReLU → Dropout
    Layer 2:  GCNConv → ReLU → Dropout
    Layer 3:  GCNConv  (output embedding)
    Readout:  for a lat/lon query, find nearest graph node and return
              its learned embedding vector.

Training Objective  (self-supervised)
-------------------------------------
We train on an **edge regression** task: given two adjacent nodes, predict
the travel time of the connecting edge.  This forces the GCN to learn
representations that encode spatial-routing information.

Dependencies
------------
- **torch**   (required)  – ``pip install torch``
- **scipy**   (for sparse adjacency)
- Falls back to **Laplacian spectral embedding** (numpy-only) if torch
  is not installed.

Exported API
------------
    build_graph_data(G)                → node_features, edge_index, edge_attr
    GCN(in_dim, hidden, out_dim)       – PyTorch GCN model
    train_gnn(G, epochs=200)           → model, embeddings (numpy)
    get_spatial_embedding(lat, lon)    → np.ndarray of shape (embed_dim,)
    run_gnn_pipeline(df)               → summary dict
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse as sp

# ─── Optional PyTorch ─────────────────────────────────────────────────────────
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    warnings.warn(
        "[gnn_model] PyTorch not installed — using spectral embedding fallback. "
        "Install: pip install torch"
    )

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE    = Path(__file__).parent
OUT_DIR = BASE / "outputs"
FIG_DIR = OUT_DIR / "figures"
OUT_DIR.mkdir(exist_ok=True)
FIG_DIR.mkdir(exist_ok=True)

SEED = 42
EMBED_DIM = 16  # default GNN output dimension


# ═══════════════════════════════════════════════════════════════════════════════
#  GRAPH CONSTRUCTION FROM OSM (or synthetic)
# ═══════════════════════════════════════════════════════════════════════════════
def build_road_graph_data(G_osm=None, n_synth=500):
    """
    Build GNN-ready tensors from an OSMnx graph **or** from a synthetic
    grid graph (when OSMnx / real graph unavailable).

    Returns
    -------
    node_feats  : np.ndarray  (N, feat_dim)      – [lat, lon, degree, ...]
    edge_index  : np.ndarray  (2, E)              – COO format
    edge_attr   : np.ndarray  (E, edge_feat_dim)  – [distance_km, speed_kph]
    node_coords : np.ndarray  (N, 2)              – [lat, lon] for NN lookup
    """
    if G_osm is not None:
        return _from_osm_graph(G_osm)
    else:
        print("[GNN] No OSM graph provided — generating synthetic road grid.")
        return _synthetic_grid(n_synth)


def _from_osm_graph(G):
    """Extract arrays from a real OSMnx MultiDiGraph."""
    import networkx as nx

    nodes = list(G.nodes(data=True))
    node_id_map = {nid: i for i, (nid, _) in enumerate(nodes)}
    N = len(nodes)

    lats = np.array([d.get("y", 0.0) for _, d in nodes])
    lons = np.array([d.get("x", 0.0) for _, d in nodes])

    # Normalise coordinates to [0, 1]
    lat_norm = (lats - lats.min()) / max(lats.max() - lats.min(), 1e-6)
    lon_norm = (lons - lons.min()) / max(lons.max() - lons.min(), 1e-6)

    degrees = np.array([G.degree(nid) for nid, _ in nodes], dtype=float)
    deg_norm = degrees / max(degrees.max(), 1)

    node_feats = np.column_stack([lat_norm, lon_norm, deg_norm])
    node_coords = np.column_stack([lats, lons])

    src, dst, dist_list, speed_list = [], [], [], []
    for u, v, data in G.edges(data=True):
        if u in node_id_map and v in node_id_map:
            src.append(node_id_map[u])
            dst.append(node_id_map[v])
            dist_list.append(data.get("length", 100) / 1000)
            speed_list.append(data.get("speed_kph", 18))

    edge_index = np.array([src, dst], dtype=np.int64)
    edge_attr  = np.column_stack([dist_list, speed_list]).astype(np.float32)

    print(f"[GNN] OSM graph: {N} nodes, {len(src)} edges, "
          f"feat_dim={node_feats.shape[1]}")
    return node_feats, edge_index, edge_attr, node_coords


def _synthetic_grid(n_nodes=500):
    """
    Generate a synthetic Hyderabad-like road grid for testing.

    Creates a random geometric graph where nodes within a threshold
    distance are connected (simulates a road network).
    """
    rng = np.random.default_rng(SEED)

    # Random points in Hyderabad bbox
    lats = rng.uniform(17.30, 17.50, n_nodes)
    lons = rng.uniform(78.35, 78.55, n_nodes)

    lat_norm = (lats - lats.min()) / max(lats.max() - lats.min(), 1e-6)
    lon_norm = (lons - lons.min()) / max(lons.max() - lons.min(), 1e-6)

    # Connect nodes within ~1.5 km of each other
    from feature_engineering import haversine_km
    src, dst, dist_list = [], [], []
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            d = float(haversine_km(lats[i], lons[i], lats[j], lons[j]))
            if d < 1.5:  # km threshold
                src.extend([i, j])
                dst.extend([j, i])
                dist_list.extend([d, d])

    if not src:
        # Fallback: connect each node to its 4 nearest
        from scipy.spatial import cKDTree
        coords = np.column_stack([lat_norm, lon_norm])
        tree = cKDTree(coords)
        for i in range(n_nodes):
            _, idxs = tree.query(coords[i], k=5)
            for j in idxs[1:]:
                d = float(haversine_km(lats[i], lons[i], lats[j], lons[j]))
                src.extend([i, j])
                dst.extend([j, i])
                dist_list.extend([d, d])

    degrees = np.zeros(n_nodes)
    for s in src:
        degrees[s] += 1
    deg_norm = degrees / max(degrees.max(), 1)

    node_feats  = np.column_stack([lat_norm, lon_norm, deg_norm])
    node_coords = np.column_stack([lats, lons])
    edge_index  = np.array([src, dst], dtype=np.int64)
    speeds      = rng.uniform(12, 35, size=len(dist_list))
    edge_attr   = np.column_stack([dist_list, speeds]).astype(np.float32)

    print(f"[GNN] Synthetic graph: {n_nodes} nodes, {len(src)} edges")
    return node_feats, edge_index, edge_attr, node_coords


# ═══════════════════════════════════════════════════════════════════════════════
#  GCN MODEL (PyTorch)
# ═══════════════════════════════════════════════════════════════════════════════
if HAS_TORCH:

    class GCNConv(nn.Module):
        """
        Single Graph Convolutional layer (Kipf & Welling, 2017).

        Implements:  H' = σ( D̃⁻½ Ã D̃⁻½ · H · W )

        where Ã = A + I  (self-loops) and D̃ is the degree matrix of Ã.
        """

        def __init__(self, in_features: int, out_features: int):
            super().__init__()
            self.weight = nn.Parameter(torch.empty(in_features, out_features))
            self.bias   = nn.Parameter(torch.zeros(out_features))
            nn.init.xavier_uniform_(self.weight)

        def forward(self, x: torch.Tensor, adj_norm: torch.Tensor):
            """
            Parameters
            ----------
            x        : (N, in_features)
            adj_norm : (N, N) normalised adjacency (sparse or dense)
            """
            support = x @ self.weight          # (N, out)
            out = torch.sparse.mm(adj_norm, support) if adj_norm.is_sparse else adj_norm @ support
            return out + self.bias

    class RoadGCN(nn.Module):
        """
        3-layer GCN for road-network node embedding.

        Architecture:
            in → hidden → hidden → embed_dim
        Each layer: GCNConv → ReLU → Dropout (except last).
        """

        def __init__(self, in_dim, hidden_dim=64, embed_dim=EMBED_DIM,
                     dropout=0.2):
            super().__init__()
            self.conv1 = GCNConv(in_dim, hidden_dim)
            self.conv2 = GCNConv(hidden_dim, hidden_dim)
            self.conv3 = GCNConv(hidden_dim, embed_dim)
            self.dropout = dropout

        def forward(self, x, adj_norm):
            h = F.relu(self.conv1(x, adj_norm))
            h = F.dropout(h, p=self.dropout, training=self.training)
            h = F.relu(self.conv2(h, adj_norm))
            h = F.dropout(h, p=self.dropout, training=self.training)
            h = self.conv3(h, adj_norm)
            return h   # (N, embed_dim)

    class EdgePredictor(nn.Module):
        """Predict edge travel-time from node embeddings (for training)."""

        def __init__(self, embed_dim):
            super().__init__()
            self.mlp = nn.Sequential(
                nn.Linear(2 * embed_dim, 64),
                nn.ReLU(),
                nn.Linear(64, 1),
            )

        def forward(self, z_src, z_dst):
            """z_src, z_dst: (E, embed_dim) → travel_time: (E, 1)."""
            cat = torch.cat([z_src, z_dst], dim=-1)
            return self.mlp(cat).squeeze(-1)


# ═══════════════════════════════════════════════════════════════════════════════
#  ADJACENCY NORMALISATION
# ═══════════════════════════════════════════════════════════════════════════════
def _build_adj_norm(edge_index, n_nodes):
    """Build D̃⁻½ Ã D̃⁻½ as a sparse torch tensor."""
    row, col = edge_index[0], edge_index[1]

    # Add self-loops
    self_loops = np.arange(n_nodes)
    row = np.concatenate([row, self_loops])
    col = np.concatenate([col, self_loops])
    vals = np.ones(len(row), dtype=np.float32)

    A = sp.coo_matrix((vals, (row, col)), shape=(n_nodes, n_nodes))

    # Degree matrix
    deg = np.array(A.sum(axis=1)).flatten()
    deg_inv_sqrt = np.power(deg, -0.5)
    deg_inv_sqrt[np.isinf(deg_inv_sqrt)] = 0.0
    D = sp.diags(deg_inv_sqrt)

    # Normalised adjacency
    A_norm = D @ A @ D
    A_norm = A_norm.tocoo()

    if HAS_TORCH:
        indices = torch.LongTensor(np.vstack([A_norm.row, A_norm.col]))
        values  = torch.FloatTensor(A_norm.data)
        return torch.sparse_coo_tensor(indices, values,
                                       torch.Size([n_nodes, n_nodes]))
    return A_norm


# ═══════════════════════════════════════════════════════════════════════════════
#  TRAINING
# ═══════════════════════════════════════════════════════════════════════════════
def train_gnn(G_osm=None, epochs=200, lr=0.005, hidden=64,
              embed_dim=EMBED_DIM, verbose=True):
    """
    Train the GCN on edge travel-time regression.

    Parameters
    ----------
    G_osm     : OSMnx graph (or None → synthetic)
    epochs    : training epochs
    lr        : learning rate
    hidden    : hidden-layer width
    embed_dim : output embedding dimension

    Returns
    -------
    embeddings : np.ndarray (N, embed_dim)
    node_coords: np.ndarray (N, 2)  [lat, lon]
    losses     : list of per-epoch MSE losses
    """
    node_feats, edge_index, edge_attr, node_coords = \
        build_road_graph_data(G_osm)

    n_nodes = node_feats.shape[0]
    in_dim  = node_feats.shape[1]

    # Compute target: travel time per edge (min) = dist_km / speed_kph * 60
    edge_times = (edge_attr[:, 0] / np.maximum(edge_attr[:, 1], 1)) * 60
    # Normalise
    time_mean = edge_times.mean()
    time_std  = max(edge_times.std(), 1e-6)
    edge_times_norm = (edge_times - time_mean) / time_std

    adj_norm = _build_adj_norm(edge_index, n_nodes)

    if not HAS_TORCH:
        print("[GNN] No PyTorch — using spectral embedding fallback.")
        return _spectral_fallback(node_feats, edge_index, n_nodes,
                                  node_coords, embed_dim)

    # Convert to tensors
    X = torch.FloatTensor(node_feats)
    y_edge = torch.FloatTensor(edge_times_norm)
    src_idx = torch.LongTensor(edge_index[0])
    dst_idx = torch.LongTensor(edge_index[1])

    model     = RoadGCN(in_dim, hidden, embed_dim)
    predictor = EdgePredictor(embed_dim)
    optimizer = torch.optim.Adam(
        list(model.parameters()) + list(predictor.parameters()), lr=lr
    )

    losses = []
    if verbose:
        print(f"[GNN] Training: {n_nodes} nodes, {edge_index.shape[1]} edges, "
              f"embed_dim={embed_dim}, epochs={epochs}")

    for epoch in range(1, epochs + 1):
        model.train()
        predictor.train()

        z = model(X, adj_norm)                    # (N, embed_dim)
        z_src = z[src_idx]                         # (E, embed_dim)
        z_dst = z[dst_idx]
        pred  = predictor(z_src, z_dst)            # (E,)
        loss  = F.mse_loss(pred, y_edge)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        losses.append(float(loss.item()))
        if verbose and epoch % 50 == 0:
            print(f"  Epoch {epoch:>4}/{epochs}  MSE={loss.item():.6f}")

    # Extract embeddings
    model.eval()
    with torch.no_grad():
        embeddings = model(X, adj_norm).numpy()

    # Save
    np.savez(OUT_DIR / "gnn_embeddings.npz",
             embeddings=embeddings, node_coords=node_coords)
    torch.save(model.state_dict(), OUT_DIR / "gnn_model.pth")

    if verbose:
        print(f"[GNN] Final MSE: {losses[-1]:.6f}")
        print(f"[GNN] Embeddings shape: {embeddings.shape}")
        print(f"[GNN] Saved → {OUT_DIR}")

    return embeddings, node_coords, losses


# ═══════════════════════════════════════════════════════════════════════════════
#  SPECTRAL EMBEDDING FALLBACK (numpy-only, no torch)
# ═══════════════════════════════════════════════════════════════════════════════
def _spectral_fallback(node_feats, edge_index, n_nodes, node_coords,
                       embed_dim):
    """
    Compute Laplacian eigenvector embeddings as a torch-free alternative.

    Uses the k smallest non-trivial eigenvectors of the normalised
    graph Laplacian as spatial embeddings.
    """
    from scipy.sparse.linalg import eigsh

    row, col = edge_index[0], edge_index[1]
    vals = np.ones(len(row), dtype=float)
    A = sp.coo_matrix((vals, (row, col)), shape=(n_nodes, n_nodes)).tocsr()

    deg = np.array(A.sum(axis=1)).flatten()
    deg_inv = np.power(deg, -0.5, where=deg > 0)
    deg_inv[deg == 0] = 0
    D_inv = sp.diags(deg_inv)
    L_norm = sp.eye(n_nodes) - D_inv @ A @ D_inv

    k = min(embed_dim + 1, n_nodes - 2)
    try:
        eigenvalues, eigenvectors = eigsh(L_norm, k=k, which="SM")
        embeddings = eigenvectors[:, 1:embed_dim + 1]  # skip trivial eigenvector
    except Exception:
        embeddings = node_feats[:, :embed_dim]  # ultimate fallback

    # Pad if needed
    if embeddings.shape[1] < embed_dim:
        pad = np.zeros((n_nodes, embed_dim - embeddings.shape[1]))
        embeddings = np.hstack([embeddings, pad])

    np.savez(OUT_DIR / "gnn_embeddings.npz",
             embeddings=embeddings, node_coords=node_coords)
    print(f"[GNN] Spectral embeddings shape: {embeddings.shape}")
    return embeddings, node_coords, []


# ═══════════════════════════════════════════════════════════════════════════════
#  NEAREST-NODE LOOKUP (for feature enrichment)
# ═══════════════════════════════════════════════════════════════════════════════
class SpatialEmbeddingLookup:
    """
    Given pre-computed node embeddings + coordinates, look up the
    embedding for any (lat, lon) query by nearest-neighbour in
    coordinate space.
    """

    def __init__(self, embeddings=None, node_coords=None):
        if embeddings is None:
            data = np.load(OUT_DIR / "gnn_embeddings.npz")
            embeddings  = data["embeddings"]
            node_coords = data["node_coords"]
        self.embeddings  = embeddings
        self.node_coords = node_coords
        # Build KD-tree for fast lookup
        from scipy.spatial import cKDTree
        self.tree = cKDTree(self.node_coords)

    def query(self, lat, lon):
        """Return the embedding of the nearest graph node."""
        _, idx = self.tree.query([lat, lon])
        return self.embeddings[idx]

    def query_pair(self, lat1, lon1, lat2, lon2):
        """
        Return concatenated embeddings for restaurant + customer nodes.
        Shape: (2 * embed_dim,)
        """
        e1 = self.query(lat1, lon1)
        e2 = self.query(lat2, lon2)
        return np.concatenate([e1, e2])

    def enrich_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add GNN embedding columns to dataframe.

        Adds columns:  gnn_rest_0, gnn_rest_1, … gnn_cust_0, gnn_cust_1, …
        """
        df = df.copy()
        embed_dim = self.embeddings.shape[1]
        rest_embs = np.zeros((len(df), embed_dim))
        cust_embs = np.zeros((len(df), embed_dim))

        for i in range(len(df)):
            row = df.iloc[i]
            rest_embs[i] = self.query(row["restaurant_lat"], row["restaurant_lon"])
            cust_embs[i] = self.query(row["customer_lat"],   row["customer_lon"])

        for j in range(embed_dim):
            df[f"gnn_rest_{j}"] = rest_embs[:, j].round(6)
            df[f"gnn_cust_{j}"] = cust_embs[:, j].round(6)

        print(f"[GNN] Enriched dataset with {2 * embed_dim} GNN embedding columns.")
        return df


# ═══════════════════════════════════════════════════════════════════════════════
#  VISUALISATION
# ═══════════════════════════════════════════════════════════════════════════════
def plot_gnn_training(losses):
    """Plot GNN training loss curve."""
    if not losses:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(losses, color="#4C72B0", lw=1.2)
    ax.set_xlabel("Epoch", fontsize=12)
    ax.set_ylabel("MSE Loss", fontsize=12)
    ax.set_title("GNN Training – Edge Travel-Time Regression",
                 fontsize=14, weight="bold")
    ax.set_yscale("log")
    plt.tight_layout()
    fig.savefig(FIG_DIR / "gnn_training_loss.png", dpi=300)
    plt.close(fig)
    print("[GNN] gnn_training_loss.png")


def plot_embeddings_tsne(embeddings, node_coords):
    """2D t-SNE visualisation of learned node embeddings, coloured by lat."""
    try:
        from sklearn.manifold import TSNE
    except ImportError:
        return

    if len(embeddings) > 2000:
        idx = np.random.default_rng(SEED).choice(len(embeddings), 2000, replace=False)
        embeddings  = embeddings[idx]
        node_coords = node_coords[idx]

    tsne = TSNE(n_components=2, random_state=SEED, perplexity=30)
    proj = tsne.fit_transform(embeddings)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: t-SNE coloured by latitude
    sc = axes[0].scatter(proj[:, 0], proj[:, 1], c=node_coords[:, 0],
                         cmap="viridis", s=5, alpha=0.6)
    axes[0].set_title("t-SNE of GNN Embeddings (colour = latitude)",
                      fontsize=12, weight="bold")
    plt.colorbar(sc, ax=axes[0], label="Latitude")

    # Right: geographic positions coloured by 1st embedding component
    sc2 = axes[1].scatter(node_coords[:, 1], node_coords[:, 0],
                          c=embeddings[:, 0], cmap="coolwarm", s=5, alpha=0.6)
    axes[1].set_title("Road Nodes (colour = GNN dim-0)",
                      fontsize=12, weight="bold")
    axes[1].set_xlabel("Longitude")
    axes[1].set_ylabel("Latitude")
    plt.colorbar(sc2, ax=axes[1], label="Embedding[0]")

    plt.tight_layout()
    fig.savefig(FIG_DIR / "gnn_embeddings_tsne.png", dpi=300)
    plt.close(fig)
    print("[GNN] gnn_embeddings_tsne.png")


# ═══════════════════════════════════════════════════════════════════════════════
#  RUN-ALL ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════════
def run_gnn_pipeline(G_osm=None, epochs=200):
    """
    Full GNN pipeline: build graph → train → embed → visualise.

    Returns summary dict for paper.tex.
    """
    embeddings, node_coords, losses = train_gnn(G_osm, epochs=epochs)
    plot_gnn_training(losses)
    plot_embeddings_tsne(embeddings, node_coords)

    summary = {
        "n_nodes":     int(node_coords.shape[0]),
        "embed_dim":   int(embeddings.shape[1]),
        "epochs":      epochs,
        "final_loss":  round(float(losses[-1]), 6) if losses else None,
        "backend":     "pytorch_gcn" if HAS_TORCH else "spectral_laplacian",
    }
    with open(OUT_DIR / "gnn_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[GNN] Summary: {json.dumps(summary, indent=2)}")
    return summary


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_gnn_pipeline()
