"""
=============================================================================
OpenStreetMap-Based Road Distance & Traffic Estimation
=============================================================================

Uses OSMnx to download the real Hyderabad road network and computes:
    1. Actual road-network shortest-path distance (km)
    2. Estimated travel time based on road type speed limits
    3. Time-of-day traffic multiplier simulation (free alternative to
       Google Maps / HERE real-time traffic APIs)

Design:
-------
- The road graph is downloaded once via the Overpass API and cached in
  ``cache/hyderabad_drive.graphml`` for all subsequent runs.
- If OSMnx is **not installed** (e.g. CI / lightweight environments) the
  module falls back to a purely synthetic "road-distance simulator" that
  multiplies Haversine distance by a realistic detour factor (≈1.3×).
- All public functions accept arrays (numpy) for vectorised enrichment of
  the full 10K-row dataset.

References:
-----------
- OSMnx: Boeing, G. (2017). "OSMnx: New Methods for Acquiring,
  Constructing, Analyzing, and Visualizing Complex Street Networks."
  Computers, Environment and Urban Systems, 65, 126–139.
- Overpass API: https://wiki.openstreetmap.org/wiki/Overpass_API

Exported API
------------
    load_or_download_graph()  → networkx.MultiDiGraph
    road_distance_km(G, lat1, lon1, lat2, lon2)  → float
    travel_time_min(G, lat1, lon1, lat2, lon2, hour, day)  → float
    enrich_dataset(df, G=None)  → pd.DataFrame  (adds two new columns)
    traffic_multiplier(hour, day)  → float
"""

import pickle
import warnings
from pathlib import Path
from functools import lru_cache

import numpy as np
import pandas as pd

# ─── Optional heavy dependency ────────────────────────────────────────────────
try:
    import osmnx as ox
    import networkx as nx
    HAS_OSMNX = True
except ImportError:
    HAS_OSMNX = False
    warnings.warn(
        "[osm_traffic] osmnx not installed — falling back to simulated "
        "road distances.  Install with: pip install osmnx"
    )

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE      = Path(__file__).parent
CACHE_DIR = BASE / "cache"
CACHE_DIR.mkdir(exist_ok=True)
GRAPH_FILE = CACHE_DIR / "hyderabad_drive.graphml"

# ─── Hyderabad bounding box (same as dataset_generator) ──────────────────────
#     OSMnx v2 bbox order: (west, south, east, north)
HYD_NORTH, HYD_SOUTH = 17.50, 17.30
HYD_EAST,  HYD_WEST  = 78.55, 78.35

# Set to True to always use simulation (faster; avoids Overpass API limits)
FORCE_SIMULATION = True

# ─── Speed assumptions per highway tag (km/h) ────────────────────────────────
#     Based on typical Hyderabad conditions (not speed-limit signs).
DEFAULT_SPEED_KPH = {
    "motorway":       55, "motorway_link":   40,
    "trunk":          45, "trunk_link":      35,
    "primary":        35, "primary_link":    30,
    "secondary":      28, "secondary_link":  22,
    "tertiary":       22, "tertiary_link":   18,
    "residential":    15, "living_street":   10,
    "unclassified":   18, "service":         10,
}
FALLBACK_SPEED = 18  # km/h for unknown road types

# ─── Hourly traffic multipliers (free-flow = 1.0) ────────────────────────────
#     Simulates congestion patterns from NCRB / Google typical-traffic bands.
HOURLY_MULTIPLIER = np.array([
    # 00   01   02   03   04   05   06   07   08   09   10   11
    0.80, 0.78, 0.75, 0.75, 0.80, 0.90, 1.10, 1.40, 1.75, 1.80, 1.50, 1.35,
    # 12   13   14   15   16   17   18   19   20   21   22   23
    1.25, 1.25, 1.20, 1.20, 1.30, 1.60, 1.85, 1.75, 1.45, 1.25, 1.05, 0.90,
])

# Weekend discount — Saturday and Sunday have ~15 % less congestion
WEEKEND_DISCOUNT = 0.85


# ═══════════════════════════════════════════════════════════════════════════════
#  HAVERSINE HELPER (duplicated here to keep module self-contained)
# ═══════════════════════════════════════════════════════════════════════════════
def _haversine_km(lat1, lon1, lat2, lon2):
    """Haversine great-circle distance — vectorised."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = (np.radians(x) for x in [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


# ═══════════════════════════════════════════════════════════════════════════════
#  GRAPH LOADING / DOWNLOADING
# ═══════════════════════════════════════════════════════════════════════════════
def load_or_download_graph():
    """
    Return the Hyderabad drivable road graph.

    On first call the graph is downloaded from the Overpass API
    and cached.  Subsequent calls load the cached GraphML file instantly.

    Returns
    -------
    G : networkx.MultiDiGraph   (None if OSMnx unavailable or download fails)
    """
    if not HAS_OSMNX or FORCE_SIMULATION:
        reason = "simulation forced" if FORCE_SIMULATION else "OSMnx not installed"
        print(f"[osm_traffic] {reason} — using simulation mode.")
        return None

    if GRAPH_FILE.exists():
        try:
            print(f"[osm_traffic] Loading cached graph: {GRAPH_FILE.name}")
            G = ox.load_graphml(GRAPH_FILE)
            return G
        except Exception as e:
            print(f"[osm_traffic] Cached graph corrupted ({e}), re-downloading …")
            GRAPH_FILE.unlink(missing_ok=True)

    try:
        print("[osm_traffic] Downloading Hyderabad drive network from OSM …")
        ox.settings.timeout = 120  # seconds
        ox.settings.overpass_rate_limit = False
        G = ox.graph_from_bbox(
            bbox=(HYD_WEST, HYD_SOUTH, HYD_EAST, HYD_NORTH),
            network_type="drive",
            simplify=True,
        )
        # Pre-compute edge travel times using assumed speeds
        _add_travel_times(G)
        ox.save_graphml(G, GRAPH_FILE)
        print(f"[osm_traffic] Saved graph ({G.number_of_nodes()} nodes, "
              f"{G.number_of_edges()} edges) → {GRAPH_FILE}")
        return G
    except Exception as e:
        print(f"[osm_traffic] Download failed ({e}) — using simulation mode.")
        return None


def _add_travel_times(G):
    """
    For every edge, compute ``travel_time_s`` = length / speed.

    The speed is looked up from the ``highway`` tag using
    ``DEFAULT_SPEED_KPH``.  If no match is found the fallback speed
    is used.
    """
    for u, v, data in G.edges(data=True):
        highway = data.get("highway", "unclassified")
        if isinstance(highway, list):
            highway = highway[0]
        speed_kph = DEFAULT_SPEED_KPH.get(highway, FALLBACK_SPEED)
        length_km = data.get("length", 100) / 1000.0
        data["travel_time_s"] = (length_km / speed_kph) * 3600  # seconds
        data["speed_kph"]     = speed_kph


# ═══════════════════════════════════════════════════════════════════════════════
#  TRAFFIC MULTIPLIER
# ═══════════════════════════════════════════════════════════════════════════════
def traffic_multiplier(hour, day_of_week=2):
    """
    Return a scalar ≥ 0.75 that multiplies base travel time.

    Parameters
    ----------
    hour : int or array-like  (0–23)
    day_of_week : int or array-like  (0=Mon … 6=Sun)

    Returns
    -------
    float or np.ndarray
    """
    hour = np.asarray(hour, dtype=int)
    day  = np.asarray(day_of_week, dtype=int)
    mult = HOURLY_MULTIPLIER[hour % 24]
    weekend_mask = day >= 5
    if np.ndim(mult) == 0:
        if weekend_mask:
            mult = float(mult * WEEKEND_DISCOUNT)
    else:
        mult = mult.copy()
        mult[weekend_mask] *= WEEKEND_DISCOUNT
    return mult


# ═══════════════════════════════════════════════════════════════════════════════
#  POINT-TO-POINT QUERIES
# ═══════════════════════════════════════════════════════════════════════════════
def road_distance_km(G, lat1, lon1, lat2, lon2):
    """
    Shortest-path road distance (km) between two lat/lon points.

    Uses Dijkstra on the edge ``length`` attribute.
    Falls back to 1.35 × Haversine if the points are not routable
    or G is None (simulation mode).
    """
    hav = float(_haversine_km(lat1, lon1, lat2, lon2))
    if G is None:
        return round(hav * 1.35, 3)       # simulated detour factor
    try:
        orig = ox.nearest_nodes(G, lon1, lat1)
        dest = ox.nearest_nodes(G, lon2, lat2)
        length_m = nx.shortest_path_length(G, orig, dest, weight="length")
        return round(length_m / 1000, 3)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return round(hav * 1.35, 3)        # fallback


def travel_time_min(G, lat1, lon1, lat2, lon2, hour=12, day=2):
    """
    Estimated travel time (minutes) including traffic multiplier.

    Routing uses the ``travel_time_s`` edge weight (pre-computed from
    road type → speed lookup).  The result is then scaled by the
    hour-of-day traffic multiplier.

    If G is None, uses simulated road distance / 18 km/h × traffic.
    """
    mult = float(traffic_multiplier(hour, day))
    if G is None:
        dist = road_distance_km(None, lat1, lon1, lat2, lon2)
        return round(dist / 18.0 * 60 * mult, 2)
    try:
        orig = ox.nearest_nodes(G, lon1, lat1)
        dest = ox.nearest_nodes(G, lon2, lat2)
        tt_s = nx.shortest_path_length(G, orig, dest, weight="travel_time_s")
        return round(tt_s / 60.0 * mult, 2)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        dist = float(_haversine_km(lat1, lon1, lat2, lon2)) * 1.35
        return round(dist / 18.0 * 60 * mult, 2)


# ═══════════════════════════════════════════════════════════════════════════════
#  BATCH DATASET ENRICHMENT
# ═══════════════════════════════════════════════════════════════════════════════
def enrich_dataset(df: pd.DataFrame, G=None) -> pd.DataFrame:
    """
    Add ``road_distance_km`` and ``osm_travel_time_min`` columns.

    Parameters
    ----------
    df : pd.DataFrame   – raw delivery dataset (must have lat/lon cols)
    G  : networkx graph  (or None → simulation mode)

    Returns
    -------
    df : pd.DataFrame   – same frame with two new columns appended
    """
    df = df.copy()
    n = len(df)

    road_dists  = np.empty(n)
    travel_mins = np.empty(n)

    mode = "OSM graph" if G is not None else "simulated"
    print(f"[osm_traffic] Enriching {n:,} rows ({mode}) …")

    for i in range(n):
        row = df.iloc[i]
        road_dists[i] = road_distance_km(
            G, row["restaurant_lat"], row["restaurant_lon"],
            row["customer_lat"], row["customer_lon"],
        )
        travel_mins[i] = travel_time_min(
            G, row["restaurant_lat"], row["restaurant_lon"],
            row["customer_lat"], row["customer_lon"],
            hour=int(row["order_hour"]),
            day=int(row["day_of_week"]),
        )
        if (i + 1) % 2000 == 0:
            print(f"  … {i+1:,}/{n:,}")

    df["road_distance_km"]     = road_dists.round(3)
    df["osm_travel_time_min"]  = travel_mins.round(2)
    print(f"[osm_traffic] Done. road_dist mean={road_dists.mean():.2f} km, "
          f"travel_time mean={travel_mins.mean():.1f} min")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
#  GRAPH STATISTICS (for the research paper)
# ═══════════════════════════════════════════════════════════════════════════════
def graph_stats(G) -> dict:
    """Return summary statistics of the road graph for the paper."""
    if G is None:
        return {"mode": "simulated", "nodes": 0, "edges": 0}
    stats = {
        "mode":             "osm",
        "nodes":            G.number_of_nodes(),
        "edges":            G.number_of_edges(),
        "avg_degree":       round(2 * G.number_of_edges() / G.number_of_nodes(), 2),
        "strongly_connected": nx.is_strongly_connected(G),
    }
    # Sample edge speeds
    speeds = [d.get("speed_kph", FALLBACK_SPEED) for _, _, d in G.edges(data=True)]
    stats["avg_speed_kph"] = round(np.mean(speeds), 1)
    stats["road_types"] = len(set(
        d.get("highway", "unknown") for _, _, d in G.edges(data=True)
    ))
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
#  VECTORISED SIMULATION (fast fallback – no per-row loop)
# ═══════════════════════════════════════════════════════════════════════════════
def enrich_dataset_simulated(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fast vectorised version that does NOT use OSMnx at all.

    Road distance ≈ Haversine × detour_factor  (random ∈ [1.2, 1.5])
    Travel time   = road_dist / speed × traffic_mult

    This is used when OSMnx is unavailable or for quick benchmarking.
    """
    df = df.copy()
    rng = np.random.default_rng(42)

    hav = _haversine_km(
        df["restaurant_lat"].values, df["restaurant_lon"].values,
        df["customer_lat"].values,   df["customer_lon"].values,
    )
    detour = rng.uniform(1.20, 1.50, size=len(df))
    road_dist = hav * detour

    mult = traffic_multiplier(
        df["order_hour"].values, df["day_of_week"].values,
    )
    speed = rng.uniform(14, 22, size=len(df))  # km/h
    travel_min = (road_dist / speed) * 60 * mult

    df["road_distance_km"]    = road_dist.round(3)
    df["osm_travel_time_min"] = travel_min.round(2)

    print(f"[osm_traffic] Simulated enrichment: {len(df):,} rows")
    return df


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Demo: download graph and test a single query
    G = load_or_download_graph()
    s = graph_stats(G)
    print(f"\nGraph stats: {s}")

    # Test point-to-point
    lat1, lon1 = 17.385, 78.486
    lat2, lon2 = 17.420, 78.510
    d = road_distance_km(G, lat1, lon1, lat2, lon2)
    t = travel_time_min(G, lat1, lon1, lat2, lon2, hour=18, day=1)
    h = float(_haversine_km(lat1, lon1, lat2, lon2))
    print(f"\nHaversine  : {h:.3f} km")
    print(f"Road dist  : {d:.3f} km  (detour factor: {d/h:.2f}×)")
    print(f"Travel time: {t:.1f} min  (18:00 Tuesday)")
