"""部署別影響（部署ごとの通勤統計・部署間の対立ポイント・配置サマリ）。

全体の流れは combination.py の run_v3_pipeline を参照。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from cest.engine.combo.common import _monthly_commute_cost, _weighted_p95

_CONFLICT_GAP_THRESHOLD_MINUTES = 15


def _compute_department_breakdown(
    per_office: List[Dict[str, Any]],
    policy_days: float,
    commute_cost_policy: str,
    commute_cost_cap: Optional[int],
) -> List[Dict[str, Any]]:
    """部署（group）ごとの通勤統計を算出する。

    station_breakdown の各要素が group・count も自分で持ってるので、
    home_stations・assignment を見て部署ごとに集計し直す必要はない。
    """
    cap = commute_cost_cap if commute_cost_policy == "capped" else None

    # group -> (通勤trip一覧, 通勤費, 配属オフィス名)
    by_group: Dict[str, Dict[str, Any]] = {}
    for po in per_office:
        office_name = po.get("name", po["office_id"])
        for sb in po.get("station_breakdown", []):
            if not sb.get("reachable") or sb.get("trip_minutes") is None:
                continue
            entry = by_group.setdefault(
                sb["group"], {"trips": [], "commute_cost": 0, "office_name": office_name}
            )
            entry["trips"].append((sb["trip_minutes"], sb["count"]))
            if commute_cost_policy != "ignore":
                entry["commute_cost"] += _monthly_commute_cost(sb, sb["trip_minutes"], policy_days, cap) * sb["count"]

    breakdown: List[Dict[str, Any]] = []
    for g, data in sorted(by_group.items()):
        trips: List[Tuple[float, int]] = data["trips"]
        total_pop = sum(c for _, c in trips)
        avg_trip = sum(t * c for t, c in trips) / total_pop if total_pop else 0
        p95_trip = _weighted_p95(trips)

        breakdown.append({
            "group": g,
            "count": total_pop,
            "avg_trip_minutes": round(avg_trip, 1),
            "p95_trip_minutes": round(p95_trip, 1),
            "assigned_office": data["office_name"],
            "commute_cost_jpy_month": data["commute_cost"] if commute_cost_policy != "ignore" else None,
        })

    return breakdown


def _compute_conflict_alerts(
    dept_breakdown: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """部署間の平均通勤格差が大きいペアを検出する。"""
    alerts: List[Dict[str, Any]] = []
    if len(dept_breakdown) < 2:
        return alerts

    for i, a in enumerate(dept_breakdown):
        for b in dept_breakdown[i + 1:]:
            gap = abs(a["avg_trip_minutes"] - b["avg_trip_minutes"])
            if gap >= _CONFLICT_GAP_THRESHOLD_MINUTES:
                worse = a if a["avg_trip_minutes"] > b["avg_trip_minutes"] else b
                better = b if worse is a else a
                alerts.append({
                    "type": "department_gap",
                    "message": f"{worse['group']}(平均{worse['avg_trip_minutes']:.0f}分)と{better['group']}(平均{better['avg_trip_minutes']:.0f}分)で{gap:.0f}分の格差があります",
                    "severity": "warning",
                })

    return alerts


def _build_assignment_summary(per_office: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """部署ごとの配属先・人数のサマリを作る。

    定員の余裕（capacity_headroom）・推定フラグは per_office に既に計算済みなので、
    ここではそれをそのまま使い回す（自分で定員計算をやり直さない）。
    """
    rows: List[Dict[str, Any]] = []
    for po in per_office:
        pop_by_group: Dict[str, int] = {}
        for sb in po.get("station_breakdown", []):
            pop_by_group[sb["group"]] = pop_by_group.get(sb["group"], 0) + sb["count"]
        for g, pop in pop_by_group.items():
            rows.append({
                "group": g,
                "assigned_office_id": po["office_id"],
                "assigned_office_name": po.get("name", po["office_id"]),
                "population": pop,
                "capacity_headroom": po.get("capacity_headroom"),
                "capacity_estimated": po.get("capacity_estimated", False),
            })
    rows.sort(key=lambda r: r["group"])
    return rows
