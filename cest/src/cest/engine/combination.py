"""
CEST v0.3 — 組み合わせ列挙・パレートフロンティア抽出・感度分析・explain 生成
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from cest.engine.kpi import compute_kpis_for_scenario
from cest.engine.routing import calc_trip_minutes
from cest.engine.notices import NoticeCollector
from cest.engine.fare_estimator import estimate_monthly_commute_cost


# ── ヘルパ ───────────────────────────────────────────────────────────────────

def _get_group(hs: Dict[str, Any]) -> str:
    return hs.get("group") or hs["station_id"]


def _get_capacity(office: Dict[str, Any], sqm_per_person: float) -> Optional[int]:
    """収容人数を返す。capacity_people 優先、なければ floor_area_sqm から推定。"""
    if office.get("capacity_people") is not None:
        return office["capacity_people"]
    area = office.get("floor_area_sqm")
    if area is not None and sqm_per_person > 0:
        return int(area / sqm_per_person)
    return None


def _capacity_is_estimated(office: Dict[str, Any]) -> bool:
    return office.get("capacity_people") is None and office.get("floor_area_sqm") is not None


# ── 組み合わせ列挙 ──────────────────────────────────────────────────────────

def enumerate_combinations(
    offices: List[Dict[str, Any]],
    num_offices_list: List[int],
    fixed_offices: List[str],
) -> List[List[Dict[str, Any]]]:
    office_by_id = {o["office_id"]: o for o in offices}
    fixed = [office_by_id[oid] for oid in fixed_offices if oid in office_by_id]
    remaining = [o for o in offices if o["office_id"] not in {o["office_id"] for o in fixed}]

    combos: List[List[Dict[str, Any]]] = []
    for k in num_offices_list:
        if len(fixed) > k:
            continue
        choose = k - len(fixed)
        if choose == 0:
            combos.append(list(fixed))
        else:
            for subset in itertools.combinations(remaining, choose):
                combos.append(list(fixed) + list(subset))
    return combos


# ── 部署配置最適化（group_together 対応）────────────────────────────────────

def _resolve_super_groups(
    home_stations: List[Dict[str, Any]],
    group_together: List[List[str]],
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for cluster in group_together:
        if not cluster:
            continue
        rep = cluster[0]
        for g in cluster:
            mapping[g] = rep
    return mapping


def build_group_assignment(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    offices: List[Dict[str, Any]],
    fixed_assignment: List[Dict[str, str]],
    group_together: List[List[str]],
) -> Dict[str, str]:
    office_by_id = {o["office_id"]: o for o in offices}

    fixed_map: Dict[str, str] = {}
    for item in fixed_assignment:
        g, oid = item.get("group", ""), item.get("office_id", "")
        if g and oid in office_by_id:
            fixed_map[g] = oid

    super_group_map = _resolve_super_groups(home_stations, group_together)
    all_groups = {_get_group(hs) for hs in home_stations}

    assignment: Dict[str, str] = {}
    processed_supers: Dict[str, str] = {}

    for g in all_groups:
        sg = super_group_map.get(g, g)

        if sg in processed_supers:
            assignment[g] = processed_supers[sg]
            continue

        fixed_oid = None
        for member in _members_of_super_group(sg, super_group_map, all_groups):
            if member in fixed_map:
                fixed_oid = fixed_map[member]
                break

        if fixed_oid and fixed_oid in office_by_id:
            result_oid = fixed_oid
        else:
            members = list(_members_of_super_group(sg, super_group_map, all_groups))
            rows = [hs for hs in home_stations if _get_group(hs) in members]
            result_oid = _best_office_for_group(G, rows, offices)

        if result_oid:
            processed_supers[sg] = result_oid
            for member in _members_of_super_group(sg, super_group_map, all_groups):
                assignment[member] = result_oid
        if g not in assignment and result_oid:
            assignment[g] = result_oid

    return assignment


def _members_of_super_group(
    sg: str,
    super_group_map: Dict[str, str],
    all_groups: set,
) -> List[str]:
    return [g for g in all_groups if super_group_map.get(g, g) == sg]


def _best_office_for_group(
    G: nx.Graph,
    rows: List[Dict[str, Any]],
    offices: List[Dict[str, Any]],
) -> Optional[str]:
    best_oid: Optional[str] = None
    best_avg: Optional[float] = None
    for office in offices:
        total = 0.0
        total_count = 0
        reachable = True
        for hs in rows:
            t = calc_trip_minutes(G, hs["station_id"], office["nearest_station_id"], office["last_mile_minutes"])
            if t is None:
                reachable = False
                break
            total += t * hs["count"]
            total_count += hs["count"]
        if not reachable or total_count == 0:
            continue
        avg = total / total_count
        if best_avg is None or avg < best_avg:
            best_avg = avg
            best_oid = office["office_id"]
    return best_oid


# ── 組み合わせ評価 ──────────────────────────────────────────────────────────

def evaluate_combo(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    offices: List[Dict[str, Any]],
    assignment: Dict[str, str],
    policy_days: float,
    thresholds_trip: List[float],
    sqm_per_person: float,
    commute_cost_policy: str = "full",
    commute_cost_cap_jpy_month: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """1組み合わせを評価。返り値 None は計算不能（到達不能など）。"""
    per_office: List[Dict[str, Any]] = []
    total_population = 0
    all_trips: List[Tuple[float, int]] = []  # (trip_minutes, count)
    total_rent = sum(o.get("rent_jpy_month") or 0 for o in offices)

    for office in offices:
        office_id = office["office_id"]
        hs_for = [hs for hs in home_stations if assignment.get(_get_group(hs)) == office_id]
        assigned_pop = sum(hs["count"] for hs in hs_for)

        cap = _get_capacity(office, sqm_per_person)
        headroom = (cap - assigned_pop) if cap is not None else None

        kpis_result = compute_kpis_for_scenario(
            G, hs_for, office, policy_days, thresholds_trip,
            baseline_trips=None, is_baseline=False,
        )

        for sb in kpis_result.get("station_breakdown", []):
            if sb.get("reachable") and sb.get("trip_minutes") is not None:
                per_count = next((hs["count"] for hs in hs_for if hs["station_id"] == sb["station_id"]), 0)
                if per_count > 0:
                    all_trips.append((sb["trip_minutes"], per_count))

        per_office.append({
            "office_id": office_id,
            "name": office.get("name", office_id),
            "assigned_population": assigned_pop,
            "capacity": cap,
            "capacity_headroom": headroom,
            "capacity_estimated": _capacity_is_estimated(office),
            "rent_jpy_month": office.get("rent_jpy_month"),
            "floor_area_sqm": office.get("floor_area_sqm"),
            "kpis": kpis_result["kpis"],
            "station_breakdown": kpis_result.get("station_breakdown", []),
        })
        total_population += assigned_pop

    if not all_trips:
        return None

    sorted_trips = sorted(all_trips, key=lambda x: x[0])
    total_pop_reachable = sum(c for _, c in sorted_trips)
    if total_pop_reachable == 0:
        return None

    # p95
    p95_threshold = 0.95 * total_pop_reachable
    cumulative = 0
    p95_trip: Optional[float] = None
    for trip, cnt in sorted_trips:
        cumulative += cnt
        if cumulative >= p95_threshold:
            p95_trip = trip
            break

    # avg
    total_weighted = sum(t * c for t, c in all_trips)
    avg_trip = total_weighted / total_pop_reachable

    # exceed counts
    exceed_60 = sum(c for t, c in all_trips if t > 60)
    exceed_90 = sum(c for t, c in all_trips if t > 90)

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
            hs_for_office = [hs for hs in home_stations if assignment.get(_get_group(hs)) == po["office_id"]]
            for sb in po.get("station_breakdown", []):
                if not sb.get("reachable") or sb.get("trip_minutes") is None:
                    continue
                hs_data = next((hs for hs in hs_for_office if hs["station_id"] == sb["station_id"]), None)
                if hs_data is None:
                    continue
                count = hs_data["count"]
                if hs_data.get("commute_allowance_jpy_month") is not None:
                    monthly_per_person = hs_data["commute_allowance_jpy_month"]
                    if cap is not None:
                        monthly_per_person = min(monthly_per_person, cap)
                    all_estimated = False
                else:
                    monthly_per_person = estimate_monthly_commute_cost(sb["trip_minutes"], policy_days, cap)
                cost_sum += monthly_per_person * count
        total_commute_cost = cost_sum
        commute_cost_estimated = all_estimated

    # 収容人数合計
    _total_capacity = sum(_get_capacity(o, sqm_per_person) or 0 for o in offices)
    total_cost = (total_rent + total_commute_cost) if total_commute_cost is not None else None
    cost_per_capacity = round(total_cost / _total_capacity) if (_total_capacity > 0 and total_cost is not None) else (
        round(total_rent / _total_capacity) if _total_capacity > 0 else None
    )

    return {
        "selected_offices": [o["office_id"] for o in offices],
        "num_offices": len(offices),
        "total_rent_jpy_month": total_rent,
        "total_commute_cost_jpy_month": total_commute_cost,
        "total_commute_cost_estimated": commute_cost_estimated,
        "total_cost_jpy_month": total_cost,
        "total_capacity": _total_capacity if _total_capacity > 0 else None,
        "cost_per_capacity": cost_per_capacity,
        "p95_trip_minutes": round(p95_trip, 1) if p95_trip is not None else None,
        "avg_trip_minutes": round(avg_trip, 1),
        "total_population": total_population,
        "exceed_60_count": exceed_60,
        "exceed_90_count": exceed_90,
        "distribution": {
            "under_30": under_30,
            "30_to_60": t_30_to_60,
            "60_to_90": t_60_to_90,
            "over_90": over_90,
        },
        "assignment": _build_assignment_summary(assignment, offices, home_stations, sqm_per_person),
        "per_office": per_office,
    }


def _build_assignment_summary(
    assignment: Dict[str, str],
    offices: List[Dict[str, Any]],
    home_stations: List[Dict[str, Any]],
    sqm_per_person: float,
) -> List[Dict[str, Any]]:
    office_ids = {o["office_id"] for o in offices}
    pop_by_group: Dict[str, int] = {}
    for hs in home_stations:
        g = _get_group(hs)
        pop_by_group[g] = pop_by_group.get(g, 0) + hs["count"]

    office_total_pop: Dict[str, int] = {}
    for g, oid in assignment.items():
        if oid in office_ids:
            office_total_pop[oid] = office_total_pop.get(oid, 0) + pop_by_group.get(g, 0)

    summary = []
    for g, oid in sorted(assignment.items()):
        if oid not in office_ids:
            continue
        office = next((o for o in offices if o["office_id"] == oid), None)
        cap = _get_capacity(office, sqm_per_person) if office else None
        total_assigned = office_total_pop.get(oid, 0)
        pop = pop_by_group.get(g, 0)
        summary.append({
            "group": g,
            "assigned_office_id": oid,
            "population": pop,
            "capacity_headroom": (cap - total_assigned) if cap is not None else None,
            "capacity_estimated": _capacity_is_estimated(office) if office else False,
        })
    return summary


# ── パレートフロンティア抽出 ────────────────────────────────────────────────

def _is_pareto_dominated(combo: Dict[str, Any], all_combos: List[Dict[str, Any]]) -> bool:
    """Return True when combo is Pareto-dominated by another combo."""
    avg_a  = combo.get("avg_trip_minutes") or math.inf
    cost_a = combo.get("total_cost_jpy_month") or combo.get("total_rent_jpy_month") or math.inf
    cap_a  = combo.get("total_capacity") or 0
    for other in all_combos:
        if other is combo:
            continue
        avg_b  = other.get("avg_trip_minutes") or math.inf
        cost_b = other.get("total_cost_jpy_month") or other.get("total_rent_jpy_month") or math.inf
        cap_b  = other.get("total_capacity") or 0
        # B が A を支配: avg ≤, cost ≤, capacity ≥ かつ少なくとも1つ厳密に優位
        if avg_b <= avg_a and cost_b <= cost_a and cap_b >= cap_a:
            if avg_b < avg_a or cost_b < cost_a or cap_b > cap_a:
                return True
    return False


def mark_pareto_frontier(
    combinations: List[Dict[str, Any]],
) -> List[str]:
    """Mark is_pareto_optimal on each combo; return list of pareto frontier IDs."""
    # Assign combination_ids
    combo_idx = 0
    for combo in combinations:
        combo_idx += 1
        k = combo["num_offices"]
        combo["combination_id"] = f"k{k}_combo_{combo_idx}"

    pareto_ids = []
    for combo in combinations:
        dominated = _is_pareto_dominated(combo, combinations)
        combo["is_pareto_optimal"] = not dominated
        if not dominated:
            pareto_ids.append(combo["combination_id"])

    # Sort pareto_ids by avg commute ascending
    pareto_combos = [c for c in combinations if c["is_pareto_optimal"]]
    pareto_combos.sort(key=lambda c: c.get("avg_trip_minutes") or math.inf)
    pareto_ids = [c["combination_id"] for c in pareto_combos]

    return pareto_ids


# ── 感度分析（v0.3.1）────────────────────────────────────────────────────────

def _combo_display_name(combo: Dict[str, Any]) -> str:
    return "+".join(po.get("name", po.get("office_id", "")) for po in combo.get("per_office", []))


def compute_sensitivity_v3(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    offices_all: List[Dict[str, Any]],
    all_combos: List[Dict[str, Any]],
    settings: Dict[str, Any],
    policy_days: float,
) -> Dict[str, Any]:
    """
    感度分析: 「条件が変わるとどの案がどれだけ影響を受けるか」を具体的な数値で返す。
    パレート最適な案を対象に、影響が大きい上位3件を表示する。
    """
    pareto = [c for c in all_combos if c.get("is_pareto_optimal")]
    details = []

    # ── 1. last_mile +5min の影響 ──────────────────────────────────────────
    # p95 は全拠点に +5min 加算なので p95 も一律 +5min 変化する
    # p95 が高い案ほど利用者への影響が大きいため、p95 降順の上位3件を表示
    top_by_p95 = sorted(pareto, key=lambda c: c.get("p95_trip_minutes") or 0, reverse=True)[:3]
    lm_impacts = []
    for c in top_by_p95:
        orig = c.get("p95_trip_minutes") or 0
        lm_impacts.append({
            "combo_name": _combo_display_name(c),
            "original_p95": round(orig),
            "changed_p95": round(orig + 5),
            "diff": 5,
        })

    details.append({
        "parameter": "last_mile_minutes +5min",
        "description": "ラストマイルが5分増えた場合の通勤最長(p95)への影響",
        "impacts": lm_impacts,
    })

    # ── 2. 出社日数変更の影響（週間通勤時間）────────────────────────────────
    # 週間通勤時間 = p95 × 2（往復）× 出社日数
    alt_days = 5.0 if policy_days <= 3 else 3.0
    top_by_weekly_diff = sorted(
        pareto,
        key=lambda c: (c.get("p95_trip_minutes") or 0) * 2 * abs(alt_days - policy_days),
        reverse=True,
    )[:3]
    days_impacts = []
    for c in top_by_weekly_diff:
        p95 = c.get("p95_trip_minutes") or 0
        orig_weekly = round(p95 * 2 * policy_days)
        new_weekly = round(p95 * 2 * alt_days)
        days_impacts.append({
            "combo_name": _combo_display_name(c),
            "original_weekly_minutes": orig_weekly,
            "changed_weekly_minutes": new_weekly,
            "diff": new_weekly - orig_weekly,
        })

    scenario_label = f"出社日数 {policy_days:.0f}日→{alt_days:.0f}日"
    details.append({
        "parameter": scenario_label,
        "description": f"出社日数が変わった場合の週間通勤時間（p95基準・往復）への影響",
        "impacts": days_impacts,
    })

    # サマリ生成
    summary_parts = []
    if lm_impacts:
        c = lm_impacts[0]
        summary_parts.append(
            f"ラストマイル+5分で最大影響は{c['combo_name']}案（p95: {c['original_p95']}→{c['changed_p95']}分）"
        )
    if days_impacts:
        max_diff = max(abs(d["diff"]) for d in days_impacts)
        summary_parts.append(f"出社{alt_days:.0f}日では週間通勤が最大{max_diff}分変化")
    summary = "。".join(summary_parts) + "。" if summary_parts else "評価対象案なし。"

    return {
        "summary": summary,
        "details": details,
    }


# ── Explain 生成 ──────────────────────────────────────────────────────────

def generate_explain(
    combo: Dict[str, Any],
    all_combos: List[Dict[str, Any]],
    offices_all: List[Dict[str, Any]],
) -> Dict[str, Any]:
    p95 = combo.get("p95_trip_minutes") or 0
    avg = combo.get("avg_trip_minutes") or 0
    total_rent = combo.get("total_rent_jpy_month") or 0
    total_pop = combo.get("total_population") or 0
    exceed_60 = combo.get("exceed_60_count") or 0
    per_office = combo.get("per_office", [])
    dist = combo.get("distribution", {})

    commute = {
        "headline": f"平均通勤 {avg:.0f}分 / p95 {p95:.0f}分",
        "detail": f"対象 {total_pop}人、60分超は {exceed_60}人",
        "distribution": (
            f"30分未満: {dist.get('under_30', 0)}人 / "
            f"30-60分: {dist.get('30_to_60', 0)}人 / "
            f"60分以上: {dist.get('60_to_90', 0) + dist.get('over_90', 0)}人"
        ),
    }

    rent_parts: List[str] = []
    for po in per_office:
        rent = po.get("rent_jpy_month")
        if isinstance(rent, int) and rent > 0:
            rent_parts.append(f"{po.get('name', po.get('office_id', 'office'))}{rent // 10000}万")

    cost = {
        "headline": f"月額賃料 {total_rent // 10000}万" if total_rent else "賃料情報なし",
        "detail": " + ".join(rent_parts) if rent_parts else "",
    }

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

    office_groups: Dict[str, List[str]] = {}
    for item in combo.get("assignment", []):
        oid = item.get("assigned_office_id")
        if not oid:
            continue
        office_groups.setdefault(oid, []).append(
            f"{item.get('group')}({item.get('population', 0)}人)"
        )

    asgn_detail: List[str] = []
    for oid, groups in office_groups.items():
        office_name = next((po.get("name") for po in per_office if po.get("office_id") == oid), oid)
        asgn_detail.append(f"{office_name}: {', '.join(groups)}")

    assignment_explain = {
        "headline": f"{len(combo.get('assignment', []))}グループを配賦",
        "detail": asgn_detail,
        "rationale": "各グループを通勤負荷が低いオフィスに割り当て",
    }

    combo_id = combo.get("combination_id", "")
    vs: List[str] = []
    others = sorted(
        [c for c in all_combos if c.get("combination_id") != combo_id],
        key=lambda c: c.get("total_rent_jpy_month") or 0,
    )
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

    return {
        "commute": commute,
        "cost": cost,
        "capacity": capacity,
        "assignment": assignment_explain,
        "vs_alternatives": vs,
    }

def run_v3_pipeline(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    offices: List[Dict[str, Any]],
    policy_days: float,
    settings: Dict[str, Any],
    collector: NoticeCollector,
) -> Dict[str, Any]:
    """
    v0.3 メインパイプライン。
    Returns dict with: all_combinations, pareto_frontier_ids, constraints_impact, sensitivity
    """
    sqm_per_person = settings.get("sqm_per_person", 3.3)
    budget = settings.get("budget_total_rent_jpy_month")
    max_p95 = settings.get("max_p95_trip_minutes")
    max_avg = settings.get("max_avg_trip_minutes")
    num_offices_list = settings.get("num_offices", [1])
    fixed_offices = settings.get("fixed_offices", [])
    fixed_assignment = settings.get("fixed_assignment", [])
    group_together = settings.get("group_together", [])
    thresholds_trip = settings.get("thresholds_trip_minutes", [60, 90])
    commute_cost_policy = settings.get("commute_cost_policy", "full")
    commute_cost_cap = settings.get("commute_cost_cap_jpy_month")

    # fixed_assignment で参照されるオフィスIDを収集（これらを含まない組み合わせは除外）
    required_offices_from_assignment = {
        item.get("office_id", "") for item in fixed_assignment if item.get("office_id")
    }

    # 組み合わせ列挙
    combos = enumerate_combinations(offices, num_offices_list, fixed_offices)
    total_combinations = len(combos)

    valid_after_capacity = 0
    valid_after_budget = 0
    valid_after_commute = 0
    evaluated: List[Dict[str, Any]] = []

    for combo_offices in combos:
        combo_office_ids = {o["office_id"] for o in combo_offices}

        # fixed_assignment で必要なオフィスが含まれているかチェック
        if not required_offices_from_assignment.issubset(combo_office_ids):
            continue

        # 部署配置
        assignment = build_group_assignment(
            G, home_stations, combo_offices, fixed_assignment, group_together
        )

        # 収容人数チェック
        capacity_ok = True
        for office in combo_offices:
            oid = office["office_id"]
            assigned_pop = sum(
                hs["count"] for hs in home_stations
                if assignment.get(_get_group(hs)) == oid
            )
            cap = _get_capacity(office, sqm_per_person)
            if cap is not None and assigned_pop > cap:
                capacity_ok = False
                break
        if not capacity_ok:
            continue
        valid_after_capacity += 1

        # 予算フィルタ
        total_rent = sum(o.get("rent_jpy_month") or 0 for o in combo_offices)
        if budget is not None and total_rent > budget:
            continue
        valid_after_budget += 1

        # KPI 計算
        result = evaluate_combo(
            G, home_stations, combo_offices, assignment,
            policy_days, thresholds_trip, sqm_per_person,
            commute_cost_policy, commute_cost_cap,
        )
        if result is None:
            continue

        # 通勤フィルタ（p95）
        if max_p95 is not None and result["p95_trip_minutes"] and result["p95_trip_minutes"] > max_p95:
            continue
        # 通勤フィルタ（平均）
        if max_avg is not None and result["avg_trip_minutes"] and result["avg_trip_minutes"] > max_avg:
            continue
        valid_after_commute += 1

        evaluated.append(result)

    # パレートフロンティア抽出
    pareto_frontier_ids = mark_pareto_frontier(evaluated)

    if not pareto_frontier_ids:
        collector.no_pareto_candidates()


    # 感度分析
    sensitivity = compute_sensitivity_v3(
        G, home_stations, offices, evaluated, settings, policy_days
    )

    # Explain 生成（全コンボに対して）
    for combo in evaluated:
        combo["explain"] = generate_explain(combo, evaluated, offices)

    constraints_impact = {
        "total_combinations": total_combinations,
        "after_capacity_filter": valid_after_capacity,
        "after_budget_filter": valid_after_budget,
        "after_commute_filter": valid_after_commute,
        "pareto_optimal": len(pareto_frontier_ids),
        "vs_previous_round": None,
    }

    return {
        "all_combinations": evaluated,
        "pareto_frontier_ids": pareto_frontier_ids,
        "constraints_impact": constraints_impact,
        "sensitivity": sensitivity,
    }
