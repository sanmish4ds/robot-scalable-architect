from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import consecutive_miss_bursts, ece_proxy, miss_rate, percentiles, psi_proxy, rti_score
from .models import CAAIConfig, ContractStatus, TICContract


@dataclass(frozen=True)
class WindowResult:
    start_t_s: float
    end_t_s: float
    n: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    miss_rate: float
    max_consecutive_misses: int
    ece_proxy: float
    drift_proxy: float
    status: ContractStatus
    rti_score: float


def load_contract(path: str | Path) -> TICContract:
    p = Path(path)
    data = json.loads(p.read_text())
    return TICContract.model_validate(data)


class TICMonitor:
    def __init__(self, contract: TICContract, caai: CAAIConfig | None = None):
        self.contract = contract
        self.caai = caai or CAAIConfig()

        # Choose a primary deadline.
        if contract.critical_paths:
            self.deadline_ms = float(contract.critical_paths[0].deadline_ms)
        else:
            # Fall back to envelope max if present
            self.deadline_ms = float(contract.latency_envelope_ms.max) if contract.latency_envelope_ms else 25.0

    def compute_windows(self, events: pd.DataFrame) -> list[WindowResult]:
        req = {"t_s", "latency_ms", "uncertainty", "drift"}
        missing = req - set(events.columns)
        if missing:
            raise ValueError(f"events missing required columns: {sorted(missing)}")

        events = events.sort_values("t_s").reset_index(drop=True)
        n = len(events)
        w = int(self.caai.window_cycles)
        if n < w:
            raise ValueError(f"need at least window_cycles={w} events; got {n}")

        out: list[WindowResult] = []
        for i in range(w, n + 1):
            win = events.iloc[i - w : i]
            lat = win["latency_ms"].to_numpy(dtype=float)
            unc = win["uncertainty"].to_numpy(dtype=float)
            drift = win["drift"].to_numpy(dtype=float)

            pct = percentiles(lat)
            miss = miss_rate(lat, self.deadline_ms)
            bursts = consecutive_miss_bursts(lat, self.deadline_ms)
            ece = ece_proxy(unc)
            psi = psi_proxy(drift)

            status: ContractStatus = "NOMINAL"
            if psi > self.contract.uncertainty.drift_violate or bursts["max_consecutive_misses"] >= self.contract.fallback.max_consecutive_deadline_misses:
                status = "VIOLATED"
            elif psi > self.contract.uncertainty.drift_warn or miss > 0.0:
                status = "WARNING"

            # Minimal RTI-score components (quality/safety/observability are placeholders here).
            timing_compliance = 1.0 - miss
            task_quality = 0.85  # placeholder proxy; should be measured in real deployments
            safety_compliance = 1.0 if status != "VIOLATED" else 0.0
            observability = 1.0
            violation_penalty = 1.0 if status == "VIOLATED" else 0.0

            score = rti_score(
                timing_compliance=timing_compliance,
                task_quality=task_quality,
                safety_compliance=safety_compliance,
                observability=observability,
                violation_penalty=violation_penalty,
            )

            out.append(
                WindowResult(
                    start_t_s=float(win["t_s"].iloc[0]),
                    end_t_s=float(win["t_s"].iloc[-1]),
                    n=w,
                    p50_ms=pct["p50"],
                    p95_ms=pct["p95"],
                    p99_ms=pct["p99"],
                    max_ms=pct["max"],
                    miss_rate=miss,
                    max_consecutive_misses=int(bursts["max_consecutive_misses"]),
                    ece_proxy=ece,
                    drift_proxy=psi,
                    status=status,
                    rti_score=float(score),
                )
            )
        return out


def load_events_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df

