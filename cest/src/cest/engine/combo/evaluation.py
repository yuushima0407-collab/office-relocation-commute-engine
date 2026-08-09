"""1つの組み合わせ（オフィス選定案）を評価し、KPI・部署別影響を算出する。

全体の流れは combination.py の run_v3_pipeline を参照。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from cest.models.request import HomeStation, OfficeCandidate
from cest.engine.combo.common import (
    _capacity_is_estimated,
    _get_capacity,
    _get_group,
    _monthly_commute_cost,
    _weighted_p95,
)
from cest.engine.combo.department import (
    _build_assignment_summary,
    _compute_department_breakdown,
)
from cest.engine.combo.kpi import compute_kpis_for_scenario


def evaluate_combo(
    G: nx.Graph,
    home_stations: List[HomeStation],
    offices: List[OfficeCandidate],
    assignment: Dict[str, str],
    policy_days: float,
    thresholds_trip: List[float],
    sqm_per_person: float,
    commute_cost_policy: str = "full",
    commute_cost_cap_jpy_month: Optional[int] = None,
    commute_risk_threshold_minutes: float = 60,
) -> Optional[Dict[str, Any]]:
    """1組み合わせを評価。返り値 None は計算不能（到達不能など）。"""
    per_office: List[Dict[str, Any]] = []
    total_population = 0
    all_trips: List[Tuple[float, int]] = []  # (trip_minutes, count)
    total_rent = sum(o.rent_jpy_month or 0 for o in offices)

    # オフィスの数だけ home_stations 全件をスキャンし直すと、大規模データでは
    # オフィス数 × 社員行数の計算量になる。先に1回だけ配属先ごとに振り分けておく。
    office_to_hs: Dict[Optional[str], List[HomeStation]] = {}
    for hs in home_stations:
        office_to_hs.setdefault(assignment.get(_get_group(hs)), []).append(hs)

    for office in offices:
        office_id = office.office_id
        hs_for = office_to_hs.get(office_id, [])
        assigned_pop = sum(hs.count for hs in hs_for)

        cap = _get_capacity(office, sqm_per_person)
        headroom = (cap - assigned_pop) if cap is not None else None

        kpis_result = compute_kpis_for_scenario(
            G, hs_for, office, policy_days, thresholds_trip,
            baseline_trips=None, is_baseline=False,
        )

        # station_breakdown の各要素は count も自分で持ってるので、hs_for を探し直す必要はない
        for sb in kpis_result.get("station_breakdown", []):
            if sb.get("reachable") and sb.get("trip_minutes") is not None:
                all_trips.append((sb["trip_minutes"], sb["count"]))

        per_office.append({
            "office_id": office_id,
            "name": office.name,
            "assigned_population": assigned_pop,
            "capacity": cap,
            "capacity_headroom": headroom,
            "capacity_estimated": _capacity_is_estimated(office),
            "rent_jpy_month": office.rent_jpy_month,
            "floor_area_sqm": office.floor_area_sqm,
            "kpis": kpis_result["kpis"],
            "station_breakdown": kpis_result.get("station_breakdown", []),
        })
        total_population += assigned_pop

    if not all_trips:
        return None

    total_pop_reachable = sum(c for _, c in all_trips)
    if total_pop_reachable == 0:
        return None

    p95_trip = _weighted_p95(all_trips)

    # avg
    total_weighted = sum(t * c for t, c in all_trips)
    avg_trip = total_weighted / total_pop_reachable

    # exceed counts（distributionの区切りと揃えて「以上」で統一）
    exceed_risk = sum(c for t, c in all_trips if t >= commute_risk_threshold_minutes)
    exceed_90 = sum(c for t, c in all_trips if t >= 90)

    # distribution
    under_30 = sum(c for t, c in all_trips if t < 30)
    t_30_to_60 = sum(c for t, c in all_trips if 30 <= t < 60)
    t_60_to_90 = sum(c for t, c in all_trips if 60 <= t < 90)
    over_90 = sum(c for t, c in all_trips if t >= 90)

    # 通勤費計算
    total_commute_cost: Optional[int] = None
    commute_cost_estimated = True
    if commute_cost_policy != "ignore":
        cap = commute_cost_cap_jpy_month if commute_cost_policy == "capped" else None
        cost_sum = 0
        all_estimated = True
        for po in per_office:
            # station_breakdown の各要素が commute_allowance_jpy_month・count も自分で持ってるので
            # home_stations を探し直す必要はない
            for sb in po.get("station_breakdown", []):
                if not sb.get("reachable") or sb.get("trip_minutes") is None:
                    continue
                if sb.get("commute_allowance_jpy_month") is not None:
                    all_estimated = False
                monthly_per_person = _monthly_commute_cost(
                    sb.get("commute_allowance_jpy_month"), sb["trip_minutes"], policy_days, cap,
                )
                cost_sum += monthly_per_person * sb["count"]
        total_commute_cost = cost_sum
        commute_cost_estimated = all_estimated

    # 収容人数合計
    _total_capacity = sum(_get_capacity(o, sqm_per_person) or 0 for o in offices)
    total_cost = (total_rent + total_commute_cost) if total_commute_cost is not None else None
    rent_per_capacity = round(total_rent / _total_capacity) if _total_capacity > 0 else None

    # 部署別影響（v0.3.2）
    dept_breakdown = _compute_department_breakdown(
        per_office, policy_days, commute_cost_policy, commute_cost_cap_jpy_month,
    )

    return {
        "selected_offices": [o.office_id for o in offices],
        "num_offices": len(offices),
        "total_rent_jpy_month": total_rent,
        "total_commute_cost_jpy_month": total_commute_cost,
        "total_commute_cost_estimated": commute_cost_estimated,
        "total_cost_jpy_month": total_cost,
        "total_capacity": _total_capacity if _total_capacity > 0 else None,
        "rent_per_capacity": rent_per_capacity,
        "p95_trip_minutes": round(p95_trip, 1) if p95_trip is not None else None,
        "avg_trip_minutes": round(avg_trip, 1),
        "total_population": total_population,
        "exceed_risk_count": exceed_risk,
        "commute_risk_threshold_minutes": commute_risk_threshold_minutes,
        "exceed_90_count": exceed_90,
        "distribution": {
            "under_30": under_30,
            "30_to_60": t_30_to_60,
            "60_to_90": t_60_to_90,
            "over_90": over_90,
        },
        "assignment": _build_assignment_summary(per_office),
        "per_office": per_office,
        "department_breakdown": dept_breakdown,
    }
