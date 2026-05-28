from __future__ import annotations

from dataclasses import dataclass

from .models import CAAIConfig, ContractStatus


@dataclass
class CAAIState:
    tier: int = 1
    dwell: int = 0


def step_caai(
    state: CAAIState,
    cfg: CAAIConfig,
    *,
    deadline_ms: float,
    p99_latency_ms: float,
    miss_rate: float,
    uncertainty: float,
    drift: float,
    consecutive_misses: int,
) -> CAAIState:
    """
    Deterministic reference supervisor. Inputs are window summaries.
    """
    margin_ms = deadline_ms - p99_latency_ms
    state.dwell += 1
    if state.dwell < cfg.dwell_min:
        return state

    tier = state.tier

    # Fast degrade path
    if (margin_ms < cfg.m_down12) or (miss_rate > 0):
        tier = max(tier, 2)
    if (uncertainty > cfg.u_23) or (drift > cfg.d_violate) or (consecutive_misses >= 2):
        tier = 3

    # Conservative recovery path
    if tier == 3 and (uncertainty < cfg.u_32) and (drift < cfg.d_warn) and (margin_ms > cfg.m_up21):
        tier = 2
    if tier == 2 and (drift < cfg.d_warn) and (margin_ms > cfg.m_up11):
        tier = 1

    state.tier = tier
    state.dwell = 0
    return state


def status_from_signals(cfg: CAAIConfig, *, miss_rate: float, drift: float, consecutive_misses: int) -> ContractStatus:
    if (drift > cfg.d_violate) or (consecutive_misses >= 2):
        return "VIOLATED"
    if (drift > cfg.d_warn) or (miss_rate > 0):
        return "WARNING"
    return "NOMINAL"

