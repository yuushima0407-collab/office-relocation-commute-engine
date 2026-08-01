"""案ごとの自然文説明（explain）生成。

全体の流れは combination.py の run_v3_pipeline を参照。
"""
from __future__ import annotations

from typing import Any, Dict, List


def _explain_commute(combo: Dict[str, Any]) -> Dict[str, Any]:
    p95 = combo.get("p95_trip_minutes") or 0
    avg = combo.get("avg_trip_minutes") or 0
    total_pop = combo.get("total_population") or 0
    exceed_risk = combo.get("exceed_risk_count") or 0
    risk_threshold = combo.get("commute_risk_threshold_minutes") or 60
    dist = combo.get("distribution", {})
    return {
        "headline": f"平均通勤 {avg:.0f}分 / p95 {p95:.0f}分",
        "detail": f"対象 {total_pop}人、{risk_threshold:.0f}分以上は {exceed_risk}人",
        "distribution": (
            f"30分未満: {dist.get('under_30', 0)}人 / "
            f"30-60分: {dist.get('30_to_60', 0)}人 / "
            f"60分以上: {dist.get('60_to_90', 0) + dist.get('over_90', 0)}人"
        ),
    }


def _explain_cost(combo: Dict[str, Any]) -> Dict[str, Any]:
    total_rent = combo.get("total_rent_jpy_month") or 0
    rent_parts: List[str] = []
    for po in combo.get("per_office", []):
        rent = po.get("rent_jpy_month")
        if isinstance(rent, int) and rent > 0:
            rent_parts.append(f"{po.get('name', po.get('office_id', 'office'))}{rent // 10000}万")
    return {
        "headline": f"月額賃料 {total_rent // 10000}万" if total_rent else "賃料情報なし",
        "detail": " + ".join(rent_parts) if rent_parts else "",
    }


def _explain_capacity(combo: Dict[str, Any]) -> Dict[str, Any]:
    per_office = combo.get("per_office", [])
    all_feasible = all(
        (po.get("capacity_headroom") is None or po.get("capacity_headroom") >= 0)
        for po in per_office
    )
    cap_details: List[str] = []
    for po in per_office:
        name = po.get("name", po.get("office_id", "office"))
        pop = po.get("assigned_population", 0)
        cap = po.get("capacity")
        hr = po.get("capacity_headroom")
        if cap is not None:
            cap_details.append(f"{name}: {pop}人 / 定員{cap}人（余裕{hr}人）")
        else:
            cap_details.append(f"{name}: {pop}人（定員未設定）")

    capacity = {
        "headline": "全拠点で収容可能" if all_feasible else "収容人数の制約に注意",
        "detail": " / ".join(cap_details),
    }
    if any(po.get("capacity_estimated") for po in per_office):
        capacity["note"] = "※定員は floor_area_sqm からの推定値を含みます。"
    return capacity


def _explain_assignment(combo: Dict[str, Any]) -> Dict[str, Any]:
    # assignment の各行が配属先オフィス名も自分で持ってるので、per_office を探し直す必要はない
    office_groups: Dict[str, List[str]] = {}
    office_names: Dict[str, str] = {}
    for item in combo.get("assignment", []):
        oid = item.get("assigned_office_id")
        if not oid:
            continue
        office_names[oid] = item.get("assigned_office_name", oid)
        office_groups.setdefault(oid, []).append(
            f"{item.get('group')}({item.get('population', 0)}人)"
        )

    asgn_detail: List[str] = []
    for oid, groups in office_groups.items():
        asgn_detail.append(f"{office_names[oid]}: {', '.join(groups)}")

    return {
        "headline": f"{len(combo.get('assignment', []))}グループを配賦",
        "detail": asgn_detail,
        "rationale": "各グループを通勤負荷が低いオフィスに割り当て",
    }


def _explain_vs_alternatives(combo: Dict[str, Any], all_combos: List[Dict[str, Any]]) -> List[str]:
    p95 = combo.get("p95_trip_minutes") or 0
    total_rent = combo.get("total_rent_jpy_month") or 0
    combo_id = combo.get("combination_id", "")

    others = sorted(
        [c for c in all_combos if c.get("combination_id") != combo_id],
        key=lambda c: c.get("total_rent_jpy_month") or 0,
    )
    vs: List[str] = []
    for other in others[:3]:
        other_p95 = other.get("p95_trip_minutes") or 0
        other_rent = other.get("total_rent_jpy_month") or 0
        rent_diff = other_rent - total_rent
        p95_diff = other_p95 - p95

        parts: List[str] = []
        if rent_diff != 0:
            parts.append(f"賃料{abs(rent_diff) // 10000}万{'高い' if rent_diff > 0 else '安い'}")
        if p95_diff != 0:
            parts.append(f"p95が{abs(p95_diff):.0f}分{'長い' if p95_diff > 0 else '短い'}")

        other_names = "+".join(
            next((po.get("name", oid) for po in other.get("per_office", []) if po.get("office_id") == oid), oid)
            for oid in other.get("selected_offices", [])
        )
        if parts:
            vs.append(f"{other_names}: {', '.join(parts)}")
    return vs


def generate_explain(
    combo: Dict[str, Any],
    all_combos: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "commute": _explain_commute(combo),
        "cost": _explain_cost(combo),
        "capacity": _explain_capacity(combo),
        "assignment": _explain_assignment(combo),
        "vs_alternatives": _explain_vs_alternatives(combo, all_combos),
    }
