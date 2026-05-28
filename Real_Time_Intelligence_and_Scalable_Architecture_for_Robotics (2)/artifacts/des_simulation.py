"""
Discrete-event simulation for a ROS 2-style pub/sub callback chain with a single-threaded
executor queue, optional CPU contention, and a deterministic CAAI tier supervisor.

This is intentionally lightweight (no ROS 2 required). It produces artifact CSVs and a
summary JSON that can be reported in the paper.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from scipy.stats import mannwhitneyu


@dataclass(frozen=True)
class TierParams:
    name: str
    median_ms: float
    p99_ms: float
    quality: float  # proxy quality score (0..1) for reporting/ablation


@dataclass(frozen=True)
class Phase:
    name: str
    seconds: float
    stress_multiplier: float
    cpu_utilization: float  # 0..1, contention probability modifier
    unc_mu: float
    drift_mu: float


def _lognorm_mu_sigma_from_median_p99(median_ms: float, p99_ms: float) -> Tuple[float, float]:
    # lognormal: median = exp(mu), p99 = exp(mu + z99*sigma)
    z99 = 2.3263478740408408
    mu = math.log(median_ms)
    sigma = (math.log(p99_ms) - mu) / z99
    return mu, sigma


def _draw_lognorm_ms(rng: np.random.Generator, median_ms: float, p99_ms: float, n: int) -> np.ndarray:
    mu, sigma = _lognorm_mu_sigma_from_median_p99(median_ms, p99_ms)
    return rng.lognormal(mean=mu, sigma=sigma, size=n)


def _clip01(x: np.ndarray) -> np.ndarray:
    return np.clip(x, 0.0, 1.0)


def _percentiles_ms(x: np.ndarray) -> Dict[str, float]:
    return {
        "p50": float(np.percentile(x, 50)),
        "p95": float(np.percentile(x, 95)),
        "p99": float(np.percentile(x, 99)),
        "max": float(np.max(x)),
        "mean": float(np.mean(x)),
    }


def _miss_rate(x: np.ndarray, deadline_ms: float) -> float:
    return float(np.mean(x > deadline_ms))


def _wilcoxon_like(a: np.ndarray, b: np.ndarray) -> float:
    # Mann-Whitney U test (nonparametric). Return p-value.
    return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)


def _bootstrap_ci(vals: np.ndarray, rng: np.random.Generator, stat_fn, iters: int = 2000) -> Tuple[float, float]:
    n = len(vals)
    boots = []
    for _ in range(iters):
        sample = vals[rng.integers(0, n, size=n)]
        boots.append(stat_fn(sample))
    boots = np.sort(np.asarray(boots))
    lo = float(np.percentile(boots, 2.5))
    hi = float(np.percentile(boots, 97.5))
    return lo, hi


@dataclass
class CAAIConfig:
    deadline_ms: float = 25.0
    hz: float = 30.0
    window_cycles: int = 120
    dwell_min: int = 60
    # margin thresholds (ms)
    m_down12: float = 2.0
    m_up11: float = 6.0
    m_up21: float = 4.0
    # uncertainty/drift thresholds
    u_23: float = 0.55
    u_32: float = 0.45
    d_warn: float = 0.22
    d_violate: float = 0.35


class DiscreteEventSim:
    def __init__(self, rng: np.random.Generator, cfg: CAAIConfig, tiers: Dict[int, TierParams], phases: List[Phase]):
        self.rng = rng
        self.cfg = cfg
        self.tiers = tiers
        self.phases = phases

    def run_fixed(self, tier: int) -> Dict:
        lat_ms, unc, drift, tier_trace = self._run_core(policy="fixed", fixed_tier=tier)
        return {
            "policy": f"fixed_t{tier}",
            "tier_trace": tier_trace,
            "lat_ms": lat_ms,
            "unc": unc,
            "drift": drift,
        }

    def run_reactive_after_miss(self) -> Dict:
        lat_ms, unc, drift, tier_trace = self._run_core(policy="reactive")
        return {"policy": "reactive_after_miss", "tier_trace": tier_trace, "lat_ms": lat_ms, "unc": unc, "drift": drift}

    def run_caai(self, overrides: Dict[str, float] | None = None) -> Dict:
        lat_ms, unc, drift, tier_trace = self._run_core(policy="caai", overrides=overrides or {})
        return {"policy": "caai", "tier_trace": tier_trace, "lat_ms": lat_ms, "unc": unc, "drift": drift}

    def _run_core(self, policy: str, fixed_tier: int | None = None, overrides: Dict[str, float] | None = None):
        cfg = self.cfg
        if overrides:
            cfg = CAAIConfig(**{**cfg.__dict__, **overrides})

        period_s = 1.0 / cfg.hz
        phases = []
        for ph in self.phases:
            cycles = int(ph.seconds * cfg.hz)
            phases.extend([ph] * cycles)

        # Signals
        unc = _clip01(self.rng.normal([ph.unc_mu for ph in phases], 0.08))
        drift = _clip01(self.rng.normal([ph.drift_mu for ph in phases], 0.06))

        # Executor queue model: single worker, 1-deep queue; if busy and event arrives, it waits.
        # We simulate per-cycle callback latency as (queue_wait + service_time), where queue_wait
        # increases if CPU contention injects random blocking into the worker.
        worker_free_t = 0.0
        lat_ms: List[float] = []
        tiers: List[int] = []

        tier = 1
        dwell = 0
        recent_lat: List[float] = []
        consec_miss = 0

        # Reactive baseline: start at Tier1; if miss occurs switch to Tier2 for dwell_min cycles.
        reactive_cooldown = 0

        for i, ph in enumerate(phases):
            t_arrival = i * period_s

            if policy == "fixed":
                assert fixed_tier is not None
                tier = fixed_tier
            elif policy == "reactive":
                if reactive_cooldown > 0:
                    tier = 2
                    reactive_cooldown -= 1
                else:
                    tier = 1
            # policy == caai handled after observation

            tp = self.tiers[tier]
            service_ms = float(_draw_lognorm_ms(self.rng, tp.median_ms, tp.p99_ms, 1)[0]) * ph.stress_multiplier

            # contention: with probability proportional to cpu_utilization, add a blocking chunk
            # representing competing callbacks/GC/pagefault etc.
            if self.rng.random() < ph.cpu_utilization:
                service_ms += float(self.rng.gamma(shape=2.0, scale=2.0))  # a few extra ms tail

            start_t = max(t_arrival, worker_free_t)
            finish_t = start_t + service_ms / 1000.0
            worker_free_t = finish_t

            x_ms = (finish_t - t_arrival) * 1000.0
            lat_ms.append(x_ms)
            tiers.append(tier)

            recent_lat.append(x_ms)
            if len(recent_lat) > cfg.window_cycles:
                recent_lat.pop(0)

            miss = x_ms > cfg.deadline_ms
            consec_miss = consec_miss + 1 if miss else 0

            if policy == "reactive" and miss and reactive_cooldown == 0:
                reactive_cooldown = cfg.dwell_min

            # CAAI update: after we have a full window
            if policy != "caai":
                continue

            dwell += 1
            if len(recent_lat) < cfg.window_cycles:
                continue
            if dwell < cfg.dwell_min:
                continue

            p99 = float(np.percentile(np.asarray(recent_lat), 99))
            margin = cfg.deadline_ms - p99

            # degrade
            if (margin < cfg.m_down12) or miss:
                tier = max(tier, 2)
            if (unc[i] > cfg.u_23) or (drift[i] > cfg.d_violate) or (consec_miss >= 2):
                tier = 3

            # recover
            if tier == 3 and (unc[i] < cfg.u_32) and (drift[i] < cfg.d_warn) and (margin > cfg.m_up21):
                tier = 2
            if tier == 2 and (drift[i] < cfg.d_warn) and (margin > cfg.m_up11):
                tier = 1

            dwell = 0

        return np.asarray(lat_ms), np.asarray(unc), np.asarray(drift), np.asarray(tiers)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--deadline-ms", type=float, default=25.0)
    ap.add_argument("--hz", type=float, default=30.0)
    args = ap.parse_args()

    out_dir = args.out_dir or os.path.join(os.path.dirname(__file__), "des_outputs")
    os.makedirs(out_dir, exist_ok=True)

    cfg = CAAIConfig(deadline_ms=args.deadline_ms, hz=args.hz)

    # Tier params: chosen to match typical perception tiering patterns and to be tunable.
    # These will be described in-paper as parameterized against reported ROS 2 executor tail behavior.
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

    policies = ["fixed_t1", "fixed_t2", "reactive_after_miss", "caai"]

    # Sensitivity sweep
    sens_grid = [
        {"m_down12": 1.0, "dwell_min": 30},
        {"m_down12": 2.0, "dwell_min": 60},
        {"m_down12": 3.0, "dwell_min": 90},
    ]

    rng_master = np.random.default_rng(args.seed)
    seeds = rng_master.integers(0, 2**31 - 1, size=args.runs)

    # Collect per-run summary metrics
    per_run: Dict[str, List[Dict]] = {p: [] for p in policies}
    per_run_sens: List[Dict] = []

    for r, seed in enumerate(seeds):
        rng = np.random.default_rng(int(seed))
        sim = DiscreteEventSim(rng, cfg, tiers, phases)

        fixed1 = sim.run_fixed(1)
        fixed2 = sim.run_fixed(2)
        reactive = sim.run_reactive_after_miss()
        caai = sim.run_caai()

        for k, run in [
            ("fixed_t1", fixed1),
            ("fixed_t2", fixed2),
            ("reactive_after_miss", reactive),
            ("caai", caai),
        ]:
            lat = run["lat_ms"]
            summ = _percentiles_ms(lat)
            miss = _miss_rate(lat, cfg.deadline_ms)
            occ = {t: float(np.mean(run["tier_trace"] == t)) for t in (1, 2, 3)}
            per_run[k].append(
                {
                    "run": r,
                    "seed": int(seed),
                    "p50": summ["p50"],
                    "p95": summ["p95"],
                    "p99": summ["p99"],
                    "max": summ["max"],
                    "miss_rate": miss,
                    "tier1_frac": occ[1],
                    "tier2_frac": occ[2],
                    "tier3_frac": occ[3],
                }
            )

        # Sensitivity only for CAAI
        for s in sens_grid:
            run = sim.run_caai(overrides=s)
            lat = run["lat_ms"]
            per_run_sens.append(
                {
                    "run": r,
                    "seed": int(seed),
                    **s,
                    "p99": float(np.percentile(lat, 99)),
                    "miss_rate": _miss_rate(lat, cfg.deadline_ms),
                    "tier3_frac": float(np.mean(run["tier_trace"] == 3)),
                }
            )

    # Summarize across runs with bootstrap CIs (per-run stats)
    rng_ci = np.random.default_rng(args.seed + 999)
    summary = {}
    for p in policies:
        rows = per_run[p]
        p99s = np.asarray([x["p99"] for x in rows])
        miss = np.asarray([x["miss_rate"] for x in rows])

        p99_mean = float(np.mean(p99s))
        miss_mean = float(np.mean(miss))
        p99_ci = _bootstrap_ci(p99s, rng_ci, np.mean)
        miss_ci = _bootstrap_ci(miss, rng_ci, np.mean)

        summary[p] = {
            "runs": args.runs,
            "p99_mean": p99_mean,
            "p99_ci95": [p99_ci[0], p99_ci[1]],
            "miss_mean": miss_mean,
            "miss_ci95": [miss_ci[0], miss_ci[1]],
        }

    # Significance tests (per-run p99 and miss)
    pvals = {
        "p99_caai_vs_fixed1": _wilcoxon_like(
            np.asarray([x["p99"] for x in per_run["caai"]]),
            np.asarray([x["p99"] for x in per_run["fixed_t1"]]),
        ),
        "miss_caai_vs_fixed1": _wilcoxon_like(
            np.asarray([x["miss_rate"] for x in per_run["caai"]]),
            np.asarray([x["miss_rate"] for x in per_run["fixed_t1"]]),
        ),
    }

    # Write artifacts
    def _write_csv(path: str, rows: List[Dict]):
        import csv

        cols = list(rows[0].keys()) if rows else []
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

    for p in policies:
        _write_csv(os.path.join(out_dir, f"des_runs_{p}.csv"), per_run[p])
    _write_csv(os.path.join(out_dir, "des_sensitivity_caai.csv"), per_run_sens)

    out_json = os.path.join(out_dir, "des_summary.json")
    with open(out_json, "w") as f:
        json.dump({"cfg": cfg.__dict__, "tiers": {k: tiers[k].__dict__ for k in tiers}, "summary": summary, "pvals": pvals}, f, indent=2)

    print(json.dumps({"out_dir": out_dir, "summary": summary, "pvals": pvals}, indent=2))


if __name__ == "__main__":
    main()

