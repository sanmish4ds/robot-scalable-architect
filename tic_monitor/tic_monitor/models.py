from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CriticalPath(BaseModel):
    path_id: str
    deadline_ms: float = Field(gt=0)
    period_ms: float | None = Field(default=None, gt=0)


class LatencyEnvelope(BaseModel):
    p50: float = Field(gt=0)
    p95: float = Field(gt=0)
    p99: float = Field(gt=0)
    max: float = Field(gt=0)


class UncertaintySpec(BaseModel):
    calibration_metric: str = "ECE_proxy"
    ece_max: float = Field(default=0.10, ge=0)
    drift_metric: str = "PSI_proxy"
    drift_warn: float = Field(default=0.20, ge=0)
    drift_violate: float = Field(default=0.35, ge=0)


class FallbackSpec(BaseModel):
    state_machine: str = "TIER_DOWN_OR_STOP"
    max_consecutive_deadline_misses: int = Field(default=2, ge=1)


class ObservabilitySpec(BaseModel):
    required_metrics: list[str] = Field(default_factory=list)
    min_emit_hz: float = Field(default=1.0, gt=0)


class ScalabilitySpec(BaseModel):
    publish_rate_hz_max: float | None = Field(default=None, gt=0)
    queue_depth_max: int | None = Field(default=None, ge=1)
    backpressure_policy: str | None = None


class Component(BaseModel):
    name: str
    build: str | None = None


class TICContract(BaseModel):
    tic_version: str = "1.0"
    component: Component
    time_base: str | None = None

    # Minimal schema: allow multiple paths, but we monitor one by default.
    critical_paths: list[CriticalPath] = Field(default_factory=list)
    latency_envelope_ms: LatencyEnvelope | None = None

    uncertainty: UncertaintySpec = Field(default_factory=UncertaintySpec)
    fallback: FallbackSpec = Field(default_factory=FallbackSpec)
    observability: ObservabilitySpec = Field(default_factory=ObservabilitySpec)
    scalability: ScalabilitySpec = Field(default_factory=ScalabilitySpec)


ContractStatus = Literal["NOMINAL", "WARNING", "VIOLATED"]


class CAAIConfig(BaseModel):
    window_cycles: int = Field(default=120, ge=10)
    dwell_min: int = Field(default=60, ge=0)
    m_down12: float = 2.0
    m_up11: float = 6.0
    m_up21: float = 4.0
    u_23: float = 0.55
    u_32: float = 0.45
    d_warn: float = 0.22
    d_violate: float = 0.35

