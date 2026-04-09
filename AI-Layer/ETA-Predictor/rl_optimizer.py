"""
=============================================================================
Reinforcement Learning – Multi-Stop Delivery Route Optimizer
=============================================================================

Models the rider's multi-delivery routing problem as a Markov Decision
Process (MDP) and solves it with **Tabular Q-Learning** (no deep-learning
dependency – pure NumPy).

Problem Formulation
-------------------
State  :  (current_node_index, frozenset_of_remaining_deliveries)
Action :  pick the next delivery to serve from the remaining set
Reward :  −travel_time(current → next)  (minimise total route time)
Terminal: all deliveries served (remaining set = ∅)

The agent learns an ε-greedy Q-table over many randomly sampled delivery
batches.  After training, the learned policy is compared against two
baselines:
    1. **Nearest-neighbour** (greedy by distance)
    2. **Random ordering**

Outputs
-------
- ``outputs/rl_policy.pkl``         – trained Q-table
- ``outputs/rl_convergence.json``   – episode reward history
- ``outputs/figures/rl_convergence.png``  – learning curve
- ``outputs/figures/rl_route_example.png`` – example route visualisation

References
----------
-  Sutton & Barto (2018). *Reinforcement Learning: An Introduction*, 2nd ed.
-  Bello et al. (2017). "Neural Combinatorial Optimization with RL", ICLR.

Exported API
------------
    DeliveryEnv(locations, distance_matrix)
    QLearningAgent(n_actions, …)
    train_rl_agent(df, n_episodes, batch_size)  → agent, history
    optimise_route(agent, rider_lat, rider_lon, deliveries)  → ordered list
"""

import json
import pickle
import time
import warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

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
RNG  = np.random.default_rng(SEED)


# ═══════════════════════════════════════════════════════════════════════════════
#  HAVERSINE (self-contained)
# ═══════════════════════════════════════════════════════════════════════════════
def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = (np.radians(x) for x in [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2)**2
    return 2 * R * np.arcsin(np.sqrt(a))


# ═══════════════════════════════════════════════════════════════════════════════
#  DELIVERY ENVIRONMENT  (MDP)
# ═══════════════════════════════════════════════════════════════════════════════
class DeliveryEnv:
    """
    Multi-stop delivery routing environment.

    Node 0 is the rider's starting position.
    Nodes 1..N are delivery destinations.

    State : (current_node, tuple_of_remaining)
    Action: index into ``remaining`` list → next destination
    Reward: −travel_time (minutes) to reach that destination
    Done  : when remaining == ()
    """

    def __init__(self, lats, lons, speed_kph=18.0):
        """
        Parameters
        ----------
        lats, lons : array-like, shape (N+1,)
            First element is the rider start position;
            remaining N are delivery destinations.
        speed_kph  : average city speed (km/h)
        """
        self.lats = np.asarray(lats, dtype=float)
        self.lons = np.asarray(lons, dtype=float)
        self.n_nodes = len(lats)
        self.speed = speed_kph

        # Pre-compute pairwise distance matrix (km)
        self.dist = np.zeros((self.n_nodes, self.n_nodes))
        for i in range(self.n_nodes):
            for j in range(i + 1, self.n_nodes):
                d = float(_haversine_km(
                    self.lats[i], self.lons[i], self.lats[j], self.lons[j]
                ))
                self.dist[i, j] = d
                self.dist[j, i] = d

        # Travel-time matrix (minutes)
        self.time_mat = (self.dist / self.speed) * 60.0

        self.reset()

    def reset(self):
        """Reset to start: rider at node 0, all deliveries remaining."""
        self.current = 0
        self.remaining = tuple(range(1, self.n_nodes))
        return self._state()

    def _state(self):
        return (self.current, self.remaining)

    def step(self, action_idx):
        """
        Execute action: move to remaining[action_idx].

        Returns
        -------
        next_state, reward, done, info
        """
        if action_idx >= len(self.remaining):
            raise ValueError(f"Invalid action {action_idx}, only "
                             f"{len(self.remaining)} remaining.")
        next_node = self.remaining[action_idx]
        travel = self.time_mat[self.current, next_node]
        reward = -travel  # negative travel time → minimise

        self.current = next_node
        self.remaining = tuple(r for r in self.remaining if r != next_node)
        done = len(self.remaining) == 0
        return self._state(), reward, done, {"travel_min": travel}

    def total_time(self, order):
        """Compute total route time for a given ordering of nodes 1..N."""
        t = 0.0
        cur = 0
        for nxt in order:
            t += self.time_mat[cur, nxt]
            cur = nxt
        return t


# ═══════════════════════════════════════════════════════════════════════════════
#  Q-LEARNING AGENT
# ═══════════════════════════════════════════════════════════════════════════════
class QLearningAgent:
    """
    Tabular Q-learning agent for the delivery routing MDP.

    Because the state space is combinatorial (current_node × remaining_set),
    we use a dictionary-based Q-table: ``Q[state][action_idx] = value``.

    Hyper-parameters
    ----------------
    alpha  : learning rate (default 0.1)
    gamma  : discount factor (default 0.99)
    eps0   : initial exploration rate (default 1.0)
    eps_min: minimum exploration (default 0.05)
    decay  : multiplicative decay per episode (default 0.995)
    """

    def __init__(self, alpha=0.1, gamma=0.99,
                 eps0=1.0, eps_min=0.05, decay=0.995):
        self.alpha   = alpha
        self.gamma   = gamma
        self.epsilon = eps0
        self.eps_min = eps_min
        self.decay   = decay
        self.Q = defaultdict(lambda: defaultdict(float))

    def choose_action(self, state, n_actions):
        """ε-greedy action selection."""
        if RNG.random() < self.epsilon:
            return int(RNG.integers(0, n_actions))
        q_vals = self.Q[state]
        if not q_vals:
            return int(RNG.integers(0, n_actions))
        best_a = max(range(n_actions), key=lambda a: q_vals.get(a, 0.0))
        return best_a

    def greedy_action(self, state, n_actions):
        """Deterministic greedy action (for evaluation)."""
        q_vals = self.Q[state]
        if not q_vals:
            return 0
        return max(range(n_actions), key=lambda a: q_vals.get(a, 0.0))

    def update(self, state, action, reward, next_state, done, n_next_actions):
        """Standard Q-learning update rule."""
        old_q = self.Q[state][action]
        if done:
            target = reward
        else:
            next_q = max(
                (self.Q[next_state].get(a, 0.0) for a in range(n_next_actions)),
                default=0.0,
            )
            target = reward + self.gamma * next_q
        self.Q[state][action] = old_q + self.alpha * (target - old_q)

    def decay_epsilon(self):
        self.epsilon = max(self.eps_min, self.epsilon * self.decay)


# ═══════════════════════════════════════════════════════════════════════════════
#  BASELINE POLICIES
# ═══════════════════════════════════════════════════════════════════════════════
def nearest_neighbour_route(env):
    """Greedy nearest-neighbour heuristic."""
    order = []
    cur = 0
    remaining = list(range(1, env.n_nodes))
    while remaining:
        dists = [env.dist[cur, r] for r in remaining]
        idx = int(np.argmin(dists))
        nxt = remaining.pop(idx)
        order.append(nxt)
        cur = nxt
    return order


def random_route(env):
    """Random permutation baseline."""
    perm = list(range(1, env.n_nodes))
    RNG.shuffle(perm)
    return perm


# ═══════════════════════════════════════════════════════════════════════════════
#  TRAINING LOOP
# ═══════════════════════════════════════════════════════════════════════════════
def train_rl_agent(
    df: pd.DataFrame,
    n_episodes: int = 3000,
    batch_size: int = 6,
    speed_kph: float = 18.0,
    verbose: bool = True,
):
    """
    Train a Q-learning agent on randomly sampled delivery batches.

    Parameters
    ----------
    df          : delivery dataset (needs customer_lat/lon columns)
    n_episodes  : number of training episodes
    batch_size  : number of deliveries per episode (excluding rider start)
    speed_kph   : assumed city-average speed
    verbose     : print progress

    Returns
    -------
    agent   : QLearningAgent (trained)
    history : dict with per-episode metrics
    """
    agent = QLearningAgent()
    episode_rewards = []
    episode_times   = []
    nn_times        = []         # nearest-neighbour baseline
    rand_times      = []         # random baseline

    all_lats = df["customer_lat"].values
    all_lons = df["customer_lon"].values
    n_total  = len(df)

    if verbose:
        print(f"[RL] Training Q-learning agent: {n_episodes} episodes, "
              f"batch={batch_size}")

    for ep in range(n_episodes):
        # Sample a random batch of deliveries + a random rider start
        idxs = RNG.choice(n_total, size=batch_size, replace=False)
        rider_idx = RNG.integers(0, n_total)

        lats = np.concatenate([[all_lats[rider_idx]], all_lats[idxs]])
        lons = np.concatenate([[all_lons[rider_idx]], all_lons[idxs]])
        env = DeliveryEnv(lats, lons, speed_kph=speed_kph)

        # --- Q-learning episode ---
        state = env.reset()
        total_reward = 0.0
        while env.remaining:
            n_act = len(env.remaining)
            action = agent.choose_action(state, n_act)
            next_state, reward, done, _ = env.step(action)
            agent.update(state, action, reward, next_state, done,
                         len(env.remaining))
            state = next_state
            total_reward += reward

        episode_rewards.append(total_reward)
        episode_times.append(-total_reward)  # total route time (positive)

        # --- Baselines (for comparison) ---
        nn_route = nearest_neighbour_route(env)
        nn_times.append(env.total_time(nn_route))
        rand_route = random_route(env)
        rand_times.append(env.total_time(rand_route))

        agent.decay_epsilon()

        if verbose and (ep + 1) % 500 == 0:
            recent = episode_times[max(0, ep - 99):ep + 1]
            print(f"  Episode {ep+1:>5}/{n_episodes}  "
                  f"ε={agent.epsilon:.3f}  "
                  f"route_time={np.mean(recent):.2f}min  "
                  f"Q-table size={sum(len(v) for v in agent.Q.values())}")

    history = {
        "episode_rewards":   episode_rewards,
        "rl_route_times":    episode_times,
        "nn_route_times":    nn_times,
        "random_route_times": rand_times,
    }

    if verbose:
        rl_avg  = np.mean(episode_times[-200:])
        nn_avg  = np.mean(nn_times[-200:])
        rnd_avg = np.mean(rand_times[-200:])
        print(f"\n[RL] Last-200 avg route time:  "
              f"RL={rl_avg:.2f}  NN={nn_avg:.2f}  Random={rnd_avg:.2f} min")
        if nn_avg > 0:
            print(f"[RL] RL improvement over NN: "
                  f"{(1 - rl_avg / nn_avg) * 100:.1f}%")

    return agent, history


# ═══════════════════════════════════════════════════════════════════════════════
#  INFERENCE – OPTIMISE A NEW ROUTE
# ═══════════════════════════════════════════════════════════════════════════════
def optimise_route(agent, rider_lat, rider_lon, delivery_lats, delivery_lons,
                   speed_kph=18.0):
    """
    Use the trained agent to decide delivery order for a new batch.

    Parameters
    ----------
    agent          : trained QLearningAgent
    rider_lat/lon  : rider's current position
    delivery_lats  : array of N customer latitudes
    delivery_lons  : array of N customer longitudes

    Returns
    -------
    dict with keys:
        route_order  : list of indices (0-based into delivery arrays)
        total_time   : estimated total route time (min)
        nn_time      : nearest-neighbour baseline time
        random_time  : random-order baseline time
    """
    lats = np.concatenate([[rider_lat], delivery_lats])
    lons = np.concatenate([[rider_lon], delivery_lons])
    env  = DeliveryEnv(lats, lons, speed_kph=speed_kph)

    # Agent rollout (greedy)
    state = env.reset()
    order = []
    while env.remaining:
        n_act = len(env.remaining)
        action = agent.greedy_action(state, n_act)
        order.append(env.remaining[action])
        state, _, _, _ = env.step(action)
    rl_time = env.total_time(order)

    # Offset node indices back to 0-based delivery indices
    delivery_order = [n - 1 for n in order]

    nn_route = nearest_neighbour_route(
        DeliveryEnv(lats, lons, speed_kph=speed_kph)
    )
    nn_time = DeliveryEnv(lats, lons, speed_kph=speed_kph).total_time(nn_route)

    rnd_route = random_route(
        DeliveryEnv(lats, lons, speed_kph=speed_kph)
    )
    rnd_time = DeliveryEnv(lats, lons, speed_kph=speed_kph).total_time(rnd_route)

    return {
        "route_order":  delivery_order,
        "total_time":   round(float(rl_time), 2),
        "nn_time":      round(float(nn_time), 2),
        "random_time":  round(float(rnd_time), 2),
        "improvement_over_nn": round(float((1 - rl_time / nn_time) * 100), 1)
                               if nn_time > 0 else 0.0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  VISUALISATION
# ═══════════════════════════════════════════════════════════════════════════════
def plot_convergence(history):
    """Plot RL training convergence vs baselines."""
    window = 100
    rl  = pd.Series(history["rl_route_times"]).rolling(window).mean()
    nn  = pd.Series(history["nn_route_times"]).rolling(window).mean()
    rnd = pd.Series(history["random_route_times"]).rolling(window).mean()

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(rl,  label="Q-Learning", color="#4C72B0", lw=1.5)
    ax.plot(nn,  label="Nearest Neighbour", color="#55A868", ls="--", lw=1.2)
    ax.plot(rnd, label="Random", color="#C44E52", ls=":", lw=1.2)
    ax.set_xlabel("Episode", fontsize=12)
    ax.set_ylabel(f"Route Time (min, {window}-ep MA)", fontsize=12)
    ax.set_title("RL Agent Convergence – Multi-Stop Delivery Routing",
                 fontsize=14, weight="bold")
    ax.legend(fontsize=10)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "rl_convergence.png", dpi=300)
    plt.close(fig)
    print("[RL] rl_convergence.png")


def plot_route_example(lats, lons, order, title="Optimised Route"):
    """
    Plot a single route on a lat/lon scatter.

    lats[0], lons[0] = rider start.
    order = sequence of node indices (1-based).
    """
    fig, ax = plt.subplots(figsize=(8, 8))

    # Plot all delivery points
    ax.scatter(lons[1:], lats[1:], c="#4C72B0", s=60, zorder=5,
               label="Deliveries")
    ax.scatter(lons[0], lats[0], c="red", s=120, marker="*", zorder=6,
               label="Rider Start")

    # Draw route lines
    path = [0] + list(order)
    for i in range(len(path) - 1):
        ax.annotate(
            "", xy=(lons[path[i + 1]], lats[path[i + 1]]),
            xytext=(lons[path[i]], lats[path[i]]),
            arrowprops=dict(arrowstyle="->", color="#555", lw=1.5),
        )
    # Number the stops
    for seq, node in enumerate(order, 1):
        ax.annotate(str(seq), (lons[node], lats[node]),
                    fontsize=9, weight="bold", ha="center", va="bottom",
                    xytext=(0, 8), textcoords="offset points")

    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    ax.set_title(title, fontsize=14, weight="bold")
    ax.legend(fontsize=10)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "rl_route_example.png", dpi=300)
    plt.close(fig)
    print("[RL] rl_route_example.png")


# ═══════════════════════════════════════════════════════════════════════════════
#  SAVE / LOAD
# ═══════════════════════════════════════════════════════════════════════════════
def save_agent(agent, history):
    with open(OUT_DIR / "rl_policy.pkl", "wb") as f:
        pickle.dump(dict(agent.Q), f)
    with open(OUT_DIR / "rl_convergence.json", "w") as f:
        json.dump({
            k: [round(float(v), 4) for v in vals]
            for k, vals in history.items()
        }, f)
    print(f"[RL] Saved policy + history -> {OUT_DIR}")


def load_agent(path=None):
    path = path or OUT_DIR / "rl_policy.pkl"
    agent = QLearningAgent()
    with open(path, "rb") as f:
        raw = pickle.load(f)
    for s, actions in raw.items():
        for a, q in actions.items():
            agent.Q[s][a] = q
    agent.epsilon = 0.0  # fully greedy for inference
    return agent


# ═══════════════════════════════════════════════════════════════════════════════
#  RUN-ALL ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════════
def run_rl_pipeline(df: pd.DataFrame = None):
    """
    Full RL pipeline: train → save → visualise → return summary.
    """
    if df is None:
        csv = BASE / "data" / "delivery_dataset.csv"
        df = pd.read_csv(csv)

    agent, history = train_rl_agent(df, n_episodes=3000, batch_size=6)
    save_agent(agent, history)
    plot_convergence(history)

    # Generate an example route visualisation
    sample = df.sample(6, random_state=42)
    rider_lat = df["restaurant_lat"].iloc[0]
    rider_lon = df["restaurant_lon"].iloc[0]
    lats = np.concatenate([[rider_lat], sample["customer_lat"].values])
    lons = np.concatenate([[rider_lon], sample["customer_lon"].values])

    result = optimise_route(
        agent, rider_lat, rider_lon,
        sample["customer_lat"].values, sample["customer_lon"].values,
    )
    plot_route_example(lats, lons, [n + 1 for n in result["route_order"]],
                       title=f"RL Route (time={result['total_time']:.1f}min)")

    summary = {
        "episodes":              3000,
        "batch_size":            6,
        "final_avg_rl_time":     round(float(np.mean(history["rl_route_times"][-200:])), 2),
        "final_avg_nn_time":     round(float(np.mean(history["nn_route_times"][-200:])), 2),
        "final_avg_random_time": round(float(np.mean(history["random_route_times"][-200:])), 2),
        "q_table_states":        len(agent.Q),
        "improvement_over_nn":   result["improvement_over_nn"],
    }
    print(f"\n[RL] Summary: {json.dumps(summary, indent=2)}")
    return summary


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_rl_pipeline()
