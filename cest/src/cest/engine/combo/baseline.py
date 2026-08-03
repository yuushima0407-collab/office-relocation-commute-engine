"""Before/After 比較（v0.3.2）— 現オフィス診断と、各案との差分。

全体の流れは combination.py の run_v3_pipeline を参照。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from cest.models.request import Settings, HomeStation
from cest.engine.combo.common import _monthly_commute_cost, _weighted_p95
from cest.engine.support.routing import calc_trip_minutes


def _compute_baseline_trips(
    G: nx.Graph,
    home_stations: List[HomeStation],
    baseline: Dict[str, Any],
) -> Dict[str, Optional[float]]:
    """baselineオフィスへの各駅からの通勤時間を計算。"""
    trips: Dict[str, Optional[float]] = {}
    for hs in home_stations:
        t = calc_trip_minutes(
            G, hs.station_id,
            baseline["nearest_station_id"],
            baseline["last_mile_minutes"],
        )
        trips[hs.station_id] = t
    return trips


def compute_baseline_diagnosis(
    baseline: Dict[str, Any],
    home_stations: List[HomeStation],
    baseline_trips: Dict[str, Optional[float]],
    policy_days: float,
    commute_cost_policy: str,
    commute_cost_cap: Optional[int],
) -> Dict[str, Any]:
    """現オフィスの診断情報を生成する。"""
    cap = commute_cost_cap if commute_cost_policy == "capped" else None
    trips: List[Tuple[float, int]] = []
    total_pop = 0
    commute_cost = 0

    for hs in home_stations:
        bt = baseline_trips.get(hs.station_id)
        if bt is None:
            continue
        trips.append((bt, hs.count))
        total_pop += hs.count
        if commute_cost_policy != "ignore":
            commute_cost += _monthly_commute_cost(hs.commute_allowance_jpy_month, bt, policy_days, cap) * hs.count

    if total_pop == 0:
        return {}

    weighted = sum(t * c for t, c in trips)
    avg_trip = weighted / total_pop
    p95_trip = _weighted_p95(trips)

    over_60 = sum(c for t, c in trips if t >= 60)
    over_90 = sum(c for t, c in trips if t >= 90)

    capacity = baseline.get("capacity_people")
    occupancy_pct = round((total_pop / capacity) * 100, 1) if capacity and capacity > 0 else None
    rent = baseline.get("rent_jpy_month") or 0
    rent_per_person = round(rent / total_pop) if total_pop > 0 and rent > 0 else None

    alerts: List[str] = []
    if occupancy_pct is not None and occupancy_pct > 100:
        alerts.append(f"収容率が100%を超えています（{occupancy_pct}%）")
    if over_90 > 0:
        alerts.append(f"通勤90分以上の社員が{over_90}人（{round(over_90 / total_pop * 100)}%）います")
    if over_60 > total_pop * 0.3:
        alerts.append(f"通勤60分以上の社員が{over_60}人（{round(over_60 / total_pop * 100)}%）で、全体の3割を超えています")

    return {
        "office_name": baseline.get("name", "現オフィス"),
        "employee_count": total_pop,
        "capacity_people": capacity,
        "occupancy_pct": occupancy_pct,
        "avg_trip_minutes": round(avg_trip, 1),
        "p95_trip_minutes": round(p95_trip, 1),
        "over_60min_count": over_60,
        "over_60min_pct": round(over_60 / total_pop * 100, 1) if total_pop > 0 else 0,
        "over_90min_count": over_90,
        "over_90min_pct": round(over_90 / total_pop * 100, 1) if total_pop > 0 else 0,
        "total_commute_cost_jpy_month": commute_cost if commute_cost_policy != "ignore" else None,
        "rent_per_person": rent_per_person,
        "alerts": alerts,
    }


def compute_vs_baseline(
    combo: Dict[str, Any],
    baseline: Dict[str, Any],
    baseline_trips: Dict[str, Optional[float]],
    baseline_diagnosis: Dict[str, Any],
    commute_cost_policy: str,
) -> Dict[str, Any]:
    """案とbaselineの差分を計算する。

    baselineの集計値（avg/p95/通勤費）は compute_baseline_diagnosis で計算済みのものを
    そのまま使う（comboごとに同じbaseline集計をやり直さない）。
    """
    if not baseline_diagnosis:
        return {}

    b_avg = baseline_diagnosis.get("avg_trip_minutes") or 0
    b_p95 = baseline_diagnosis.get("p95_trip_minutes") or 0
    b_commute_cost = baseline_diagnosis.get("total_commute_cost_jpy_month") or 0
    b_rent = baseline.get("rent_jpy_month") or 0

    # combo値
    c_avg = combo.get("avg_trip_minutes") or 0
    c_p95 = combo.get("p95_trip_minutes") or 0
    c_rent = combo.get("total_rent_jpy_month") or 0
    c_commute = combo.get("total_commute_cost_jpy_month") or 0

    # 人数比較: comboの各社員がbaselineと比べて改善/悪化
    # station_breakdown の各要素が station_id・count も自分で持ってるので、
    # home_stations や assignment を見て探し直す必要はない
    worse = 0
    better = 0
    unchanged = 0
    for po in combo.get("per_office", []):
        for sb in po.get("station_breakdown", []):
            if not sb.get("reachable") or sb.get("trip_minutes") is None:
                continue
            bt = baseline_trips.get(sb["station_id"])
            if bt is None:
                continue
            diff = sb["trip_minutes"] - bt
            if diff > 1:
                worse += sb["count"]
            elif diff < -1:
                better += sb["count"]
            else:
                unchanged += sb["count"]

    return {
        "avg_trip_change": round(c_avg - b_avg, 1),
        "p95_trip_change": round(c_p95 - b_p95, 1),
        "rent_change": c_rent - b_rent,
        "commute_cost_change": (c_commute - b_commute_cost) if commute_cost_policy != "ignore" else None,
        "total_cost_change": (c_rent + c_commute) - (b_rent + b_commute_cost) if commute_cost_policy != "ignore" else c_rent - b_rent,
        "worse_count": worse,
        "better_count": better,
        "unchanged_count": unchanged,
    }


def apply_baseline_comparison(
    G: nx.Graph,
    home_stations: List[HomeStation],
    evaluated: List[Dict[str, Any]],
    settings: Settings,
    policy_days: float,
) -> Optional[Dict[str, Any]]:
    """baseline が指定されていれば現状診断を作り、各comboに vs_baseline を付与する。"""
    if settings.baseline is None:
        return None
    # この先の関数は辞書を期待してるので、ここで変換する
    baseline_cfg = settings.baseline.model_dump()

    commute_cost_policy = settings.commute_cost_policy
    commute_cost_cap = settings.commute_cost_cap_jpy_month

    baseline_trips = _compute_baseline_trips(G, home_stations, baseline_cfg)
    baseline_diagnosis = compute_baseline_diagnosis(
        baseline_cfg, home_stations, baseline_trips,
        policy_days, commute_cost_policy, commute_cost_cap,
    )
    for combo in evaluated:
        combo["vs_baseline"] = compute_vs_baseline(
            combo, baseline_cfg, baseline_trips, baseline_diagnosis, commute_cost_policy,
        )
    return baseline_diagnosis
