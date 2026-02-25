from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class HomeStation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    station_id: str
    count: int = Field(ge=1)
    segment: Optional[str] = None
    group: Optional[str] = None
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
    # 収容人数: 直接指定するか floor_area_sqm から推定
    capacity_people: Optional[int] = Field(None, ge=0)
    # v0.3: 床面積（㎡）。sqm_per_person で推定収容人数に変換
    floor_area_sqm: Optional[float] = Field(None, ge=0)


class PolicyAsIs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    office_days_per_week: float = Field(ge=0, le=5)


class RoutingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    graph_id: Optional[str] = "tokyo_core_v1"
    transfer_penalty_minutes: float = Field(0, ge=0, le=60)


class FixedAssignmentItem(BaseModel):
    """部署をオフィスに固定する制約の1エントリ。"""
    model_config = ConfigDict(extra="forbid")
    group: str
    office_id: str


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 拠点数パターン（例: [1,2,3]）
    num_offices: List[int] = Field(default_factory=lambda: [1])
    # 必ず採用するオフィスID
    fixed_offices: List[str] = Field(default_factory=list)
    # v0.3: 部署→オフィス固定（リスト形式）
    fixed_assignment: List[FixedAssignmentItem] = Field(default_factory=list)
    # v0.3: 同じ拠点に配置する部署グループ
    group_together: List[List[str]] = Field(default_factory=list)
    # v0.3: 通勤上限（p95片道分）
    max_p95_trip_minutes: Optional[int] = Field(None, ge=1)
    # v0.3: 平均通勤上限（片道分）
    max_avg_trip_minutes: Optional[float] = Field(None, ge=1)
    # v0.3: 一人あたり面積（㎡）。デフォルト3.3（国交省基準）
    sqm_per_person: float = Field(3.3, ge=0.1)
    # 予算上限
    budget_total_rent_jpy_month: Optional[int] = Field(default=None, ge=0)
    # 通勤閾値（KPI集計用）
    thresholds_trip_minutes: List[float] = Field(default=[60, 90])
    percentiles: List[int] = Field(default=[50, 95])
    routing: RoutingSettings = Field(default_factory=RoutingSettings)
    # 後方互換フィールド（v0.1.x/v0.2）
    baseline_office_id: Optional[str] = None
    ranking_weights: Optional[Dict[str, float]] = None
    bench_trip_p95_minutes: float = Field(90, ge=1)
    bench_rent_jpy_month: float = Field(10_000_000, ge=1)
    robust_flip_rate_threshold: float = Field(0.10, ge=0, le=1)


class EvaluateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home_station_distribution: List[HomeStation] = Field(min_length=1)
    office_candidates: List[OfficeCandidate] = Field(min_length=1)
    policy_as_is: PolicyAsIs
    settings: Settings


class EvaluateRequest(BaseModel):
    """Top-level request body for POST /evaluate."""
    model_config = ConfigDict(extra="forbid")
    inputs: EvaluateInput
