from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class HomeStation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    station_id: str
    count: int = Field(ge=1)
    segment: Optional[str] = None
    office_days_per_week_override: Optional[float] = Field(None, ge=0, le=5)


class OfficeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    office_id: str
    name: str
    nearest_station_id: str
    last_mile_minutes: float = Field(ge=0, le=60)
    lat: Optional[float] = None
    lon: Optional[float] = None
    rent_jpy_month: Optional[int] = Field(None, ge=0)


class PolicyAsIs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    office_days_per_week: float = Field(ge=0, le=5)


class RoutingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    graph_id: Optional[str] = "tokyo_core_v1"
    transfer_penalty_minutes: float = Field(0, ge=0, le=60)


class RankingWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access: float = Field(ge=0, le=1)
    financial: float = Field(ge=0, le=1)
    environmental: float = Field(ge=0, le=1)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_office_id: Optional[str] = None
    thresholds_trip_minutes: List[float] = Field(default=[60, 90])
    percentiles: List[int] = Field(default=[50, 95])
    ranking_weights: RankingWeights
    bench_trip_p95_minutes: float = Field(90, ge=1)
    bench_rent_jpy_month: float = Field(10_000_000, ge=1)
    robust_flip_rate_threshold: float = Field(0.10, ge=0, le=1)
    routing: RoutingSettings = Field(default_factory=RoutingSettings)


class EvaluateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home_station_distribution: List[HomeStation] = Field(min_length=1)
    office_candidates: List[OfficeCandidate] = Field(min_length=2, max_length=5)
    policy_as_is: PolicyAsIs
    settings: Settings


class EvaluateRequest(BaseModel):
    """Top-level request body for POST /evaluate."""
    model_config = ConfigDict(extra="forbid")
    inputs: EvaluateInput
