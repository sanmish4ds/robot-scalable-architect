#!/usr/bin/env python3
"""Generate evaluation figures from discrete-event simulation (seed=17, same as paper)."""

from __future__ import annotations

import csv
import math
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

# Import DES model from sibling module
sys.path.insert(0, os.path.dirname(__file__))
from des_simulation import (  # noqa: E402
    CAAIConfig,
    DiscreteEventSim,
    Phase,
    TierParams,
    _lognorm_mu_sigma_from_median_p99,
)

PAPER_DIR = os.path.dirname(os.path.dirname(__file__))
SEED = 17
DEADLINE_MS = 25.0


def _tier_setup():
    tiers = {
        1: TierParams("Tier1_full", median_ms=8.0, p99_ms=20.0, quality=0.90),
        2: TierParams("Tier2_compressed", median_ms=6.5, p99_ms=15.5, quality=0.80),
        3: TierParams("Tier3_emergency", median_ms=3.0, p99_ms=6.0, quality=0.30),
    }
    phases = [
        Phase("nominal", seconds=120, stress_multiplier=1.0, cpu_utilization=0.05, unc_mu=0.25, drift_mu=0.10),
        Phase("stress", seconds=120, stress_multiplier=1.35, cpu_utilization=0.45, unc_mu=0.42, drift_mu=0.32),
        Phase("recovery", seconds=60, stress_multiplier=1.0, cpu_utilization=0.10, unc_mu=0.28, drift_mu=0.14),
    ]
    return tiers, phases


def _run_policies():
    rng = np.random.default_rng(SEED)
    cfg = CAAIConfig(deadline_ms=DEADLINE_MS, hz=30.0)
    tiers, phases = _tier_setup()
    sim = DiscreteEventSim(rng, cfg, tiers, phases)
    return {
        "fixed_t1": sim.run_fixed(1),
        "fixed_t2": sim.run_fixed(2),
        "caai": sim.run_caai(),
    }


def _empirical_cdf(x: np.ndarray):
    xs = np.sort(x)
    ys = np.arange(1, len(xs) + 1) / len(xs)
    return xs, ys


def plot_cdf(runs: dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    styles = {
        "fixed_t1": ("Fixed Tier~1", "#c0392b"),
        "fixed_t2": ("Fixed Tier~2", "#2980b9"),
        "caai": ("CAAI", "#27ae60"),
    }
    for key, (label, color) in styles.items():
        x = runs[key]["lat_ms"]
        xs, ys = _empirical_cdf(x)
        ax.step(xs, ys, where="post", label=label, color=color, linewidth=1.6)
    ax.axvline(DEADLINE_MS, color="black", linestyle="--", linewidth=1.0, label=f"Deadline ({DEADLINE_MS:.0f} ms)")
    ax.set_xlabel("End-to-end latency (ms)")
    ax.set_ylabel("CDF")
    ax.set_xlim(0, max(55, float(np.percentile(runs["fixed_t1"]["lat_ms"], 99.9)) + 5))
    ax.set_ylim(0, 1.02)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(True, alpha=0.25)
    ax.set_title("DES: latency CDF (30 Hz, $D=25$ ms, seed=17)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_bars_from_runs_csv(out_dir: str, out_path: str) -> None:
    """Bar chart of mean p50/p95/p99/max across 30 runs (matches Table tab:sim_results)."""
    policies = [
        ("fixed_t1", "Fixed Tier~1"),
        ("fixed_t2", "Fixed Tier~2"),
        ("caai", "CAAI"),
    ]
    stats = ["p50", "p95", "p99", "max"]
    data = {p: {s: [] for s in stats} for p, _ in policies}

    for policy, _ in policies:
        path = os.path.join(out_dir, f"des_runs_{policy}.csv")
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                for s in stats:
                    data[policy][s].append(float(row[s]))

    means = {p: {s: float(np.mean(data[p][s])) for s in stats} for p, _ in policies}
    labels = [lbl for _, lbl in policies]
    x = np.arange(len(labels))
    width = 0.18
    colors = ["#3498db", "#9b59b6", "#e67e22", "#2c3e50"]

    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    for i, s in enumerate(stats):
        vals = [means[p][s] for p, _ in policies]
        ax.bar(x + (i - 1.5) * width, vals, width, label=s, color=colors[i])
    ax.axhline(DEADLINE_MS, color="black", linestyle="--", linewidth=1.0, label="Deadline")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Latency (ms)")
    ax.set_title("DES: latency summary (mean over 30 runs)")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_tiertrace(caai_run: dict, hz: float, out_path: str) -> None:
    tiers = caai_run["tier_trace"]
    n = len(tiers)
    t_s = np.arange(n) / hz

    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    # Step plot: tier 1 top, 3 bottom
    ax.step(t_s, tiers, where="post", color="#2c3e50", linewidth=1.2)
    ax.set_yticks([1, 2, 3])
    ax.set_yticklabels(["Tier 1 (full)", "Tier 2 (reduced)", "Tier 3 (fallback)"])
    ax.set_xlabel("Elapsed time (s)")
    ax.set_ylabel("Active tier")
    ax.set_ylim(0.6, 3.4)
    ax.set_xlim(0, t_s[-1])
    # Phase markers (nominal 120s, stress 120s, recovery 60s)
    ax.axvspan(0, 120, alpha=0.08, color="green", label="nominal")
    ax.axvspan(120, 240, alpha=0.10, color="red", label="stress")
    ax.axvspan(240, 300, alpha=0.08, color="blue", label="recovery")
    ax.legend(loc="upper right", fontsize=7, ncol=3)
    ax.set_title("DES: CAAI supervisor tier trace (seed=17)")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def export_samples(runs: dict, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "des_plot_samples.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["policy", "cycle", "latency_ms", "tier"])
        hz = 30.0
        for policy, run in runs.items():
            for i, lat in enumerate(run["lat_ms"]):
                tier = int(run["tier_trace"][i]) if "tier_trace" in run else ""
                w.writerow([policy, i, f"{lat:.6f}", tier])


def main() -> None:
    runs = _run_policies()
    out_samples = os.path.join(os.path.dirname(__file__), "des_outputs")
    export_samples(runs, out_samples)

    plot_cdf(runs, os.path.join(PAPER_DIR, "fig_pilot_latency_cdf.png"))
    plot_bars_from_runs_csv(out_samples, os.path.join(PAPER_DIR, "fig_pilot_latency_bars.png"))
    plot_tiertrace(runs["caai"], hz=30.0, out_path=os.path.join(PAPER_DIR, "fig_tiertrace.png"))

    # Print lognormal params for paper text
    for tier_id, median, p99 in [(1, 8.0, 20.0), (2, 6.5, 15.5), (3, 3.0, 6.0)]:
        mu, sigma = _lognorm_mu_sigma_from_median_p99(median, p99)
        print(f"Tier {tier_id}: median={median} p99={p99} -> mu={mu:.4f} sigma={sigma:.4f}")


if __name__ == "__main__":
    main()
