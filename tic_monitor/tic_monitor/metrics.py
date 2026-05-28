from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def percentiles(x: np.ndarray) -> dict[str, float]:
    x = np.asarray(x, dtype=float)
    return {
        "p50": float(np.percentile(x, 50)),
        "p95": float(np.percentile(x, 95)),
        "p99": float(np.percentile(x, 99)),
        "max": float(np.max(x)),
        "mean": float(np.mean(x)),
    }


def miss_rate(lat_ms: np.ndarray, deadline_ms: float) -> float:
    lat_ms = np.asarray(lat_ms, dtype=float)
    return float(np.mean(lat_ms > deadline_ms))


def consecutive_miss_bursts(lat_ms: np.ndarray, deadline_ms: float) -> dict[str, int]:
    misses = (np.asarray(lat_ms, dtype=float) > deadline_ms).astype(int)
    max_burst = 0
    cur = 0
    bursts_ge_2 = 0
    for m in misses:
        if m:
            cur += 1
            max_burst = max(max_burst, cur)
        else:
            if cur >= 2:
                bursts_ge_2 += 1
            cur = 0
    if cur >= 2:
        bursts_ge_2 += 1
    return {"max_consecutive_misses": int(max_burst), "bursts_ge_2": int(bursts_ge_2)}


def ece_proxy(uncertainty: np.ndarray) -> float:
    """
    Minimal proxy for calibration drift when true labels are unavailable.
    Uses deviation from a mid-confidence baseline as a simple stability statistic.
    (Replace with true ECE when you have predicted probabilities + outcomes.)
    """
    u = np.asarray(uncertainty, dtype=float)
    u = np.clip(u, 0.0, 1.0)
    return float(np.mean(np.abs(u - 0.5)))


def psi_proxy(drift_score: np.ndarray) -> float:
    """
    Proxy for drift: treat drift_score as already-computed 0..1 summary.
    Returns its mean as a window statistic.
    """
    d = np.asarray(drift_score, dtype=float)
    d = np.clip(d, 0.0, 1.0)
    return float(np.mean(d))


@dataclass(frozen=True)
class RTIWeights:
    w_t: float = 0.15
    w_q: float = 0.15
    w_s: float = 0.35
    w_o: float = 0.10
    w_p: float = 0.25


def rti_score(
    timing_compliance: float,
    task_quality: float,
    safety_compliance: float,
    observability: float,
    violation_penalty: float,
    w: RTIWeights = RTIWeights(),
) -> float:
    # Clamp inputs defensively.
    def c01(x: float) -> float:
        return max(0.0, min(1.0, float(x)))

    return (
        w.w_t * c01(timing_compliance)
        + w.w_q * c01(task_quality)
        + w.w_s * c01(safety_compliance)
        + w.w_o * c01(observability)
        - w.w_p * c01(violation_penalty)
    )

