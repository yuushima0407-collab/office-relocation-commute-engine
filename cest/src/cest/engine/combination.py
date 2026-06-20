"""
CEST v0.3.2 — 組み合わせ列挙・パレートフロンティア・部署別影響・注意点分析・explain 生成
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

def _index_offices(offices: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """オフィスのリストを office_id をキーにした辞書に変換する。"""
    return {o["office_id"]: o for o in offices}

# ── 組み合わせ列挙 ──────────────────────────────────────────────────────────

def enumerate_combinations(
    offices: List[Dict[str, Any]],
    num_offices_list: List[int],
    fixed_offices: List[str],
) -> List[List[Dict[str, Any]]]:
    office_by_id = _index_offices(offices)
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
    office_by_id = _index_offices(offices)

    fixed_map: Dict[str, str] = {}
    for item in fixed_assignment:
        g, oid = item.get("group", ""), item.get("office_id", "")
        if g and oid in office_by_id:
            fixed_map[g] = oid

    super_group_map = _resolve_super_groups(group_together)
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
    rent_per_capacity = round(total_rent / _total_capacity) if _total_capacity > 0 else None

    # 部署別影響（v0.3.2）
    dept_breakdown = _compute_department_breakdown(
        home_stations, assignment, per_office, policy_days,
        commute_cost_policy, commute_cost_cap_jpy_month,
    )
    conflict_alerts = _compute_conflict_alerts(dept_breakdown)

    return {
        "selected_offices": [o["office_id"] for o in offices],
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
        "department_breakdown": dept_breakdown,
        "conflict_alerts": conflict_alerts,
    }


# ── 部署別影響（v0.3.2）──────────────────────────────────────────────────────

_CONFLICT_GAP_THRESHOLD_MINUTES = 15


def _compute_department_breakdown(
    home_stations: List[Dict[str, Any]],
    assignment: Dict[str, str],
    per_office: List[Dict[str, Any]],
    policy_days: float,
    commute_cost_policy: str,
    commute_cost_cap: Optional[int],
) -> List[Dict[str, Any]]:
    """部署（group）ごとの通勤統計を算出する。"""
    # station_breakdownからtrip_minutesを引くためのルックアップ
    trip_lookup: Dict[str, Dict[str, float]] = {}  # office_id -> {station_id: minutes}
    for po in per_office:
        oid = po["office_id"]
        trip_lookup[oid] = {}
        for sb in po.get("station_breakdown", []):
            if sb.get("reachable") and sb.get("trip_minutes") is not None:
                trip_lookup[oid][sb["station_id"]] = sb["trip_minutes"]

    office_name_map = {po["office_id"]: po.get("name", po["office_id"]) for po in per_office}

    # group ごとに集計
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for hs in home_stations:
        g = _get_group(hs)
        groups.setdefault(g, []).append(hs)

    breakdown: List[Dict[str, Any]] = []
    cap = commute_cost_cap if commute_cost_policy == "capped" else None

    for g, stations in sorted(groups.items()):
        oid = assignment.get(g)
        if not oid or oid not in trip_lookup:
            continue

        trips: List[Tuple[float, int]] = []
        commute_cost = 0
        for hs in stations:
            t = trip_lookup[oid].get(hs["station_id"])
            if t is None:
                continue
            trips.append((t, hs["count"]))
            if commute_cost_policy != "ignore":
                if hs.get("commute_allowance_jpy_month") is not None:
                    per_person = hs["commute_allowance_jpy_month"]
                    if cap is not None:
                        per_person = min(per_person, cap)
                else:
                    per_person = estimate_monthly_commute_cost(t, policy_days, cap)
                commute_cost += per_person * hs["count"]

        if not trips:
            continue

        total_pop = sum(c for _, c in trips)
        avg_trip = sum(t * c for t, c in trips) / total_pop if total_pop else 0
        sorted_t = sorted(trips, key=lambda x: x[0])
        p95_threshold = 0.95 * total_pop
        cum = 0
        p95_trip = 0.0
        for t, c in sorted_t:
            cum += c
            if cum >= p95_threshold:
                p95_trip = t
                break

        breakdown.append({
            "group": g,
            "count": total_pop,
            "avg_trip_minutes": round(avg_trip, 1),
            "p95_trip_minutes": round(p95_trip, 1),
            "assigned_office": office_name_map.get(oid, oid),
            "commute_cost_jpy_month": commute_cost if commute_cost_policy != "ignore" else None,
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
    """Return True when combo is Pareto-dominated by another combo.

    パレート軸: (total_rent, avg_trip, total_capacity) の3軸。
    - total_rent: 低いほど良い
    - avg_trip: 低いほど良い（平均通勤。p95は外れ値に振られやすいので採用しない）
    - total_capacity: 高いほど良い
    """
    avg_a  = combo.get("avg_trip_minutes") or math.inf
    rent_a = combo.get("total_rent_jpy_month") or math.inf
    cap_a  = combo.get("total_capacity") or 0
    for other in all_combos:
        if other is combo:
            continue
        avg_b  = other.get("avg_trip_minutes") or math.inf
        rent_b = other.get("total_rent_jpy_month") or math.inf
        cap_b  = other.get("total_capacity") or 0
        # B が A を支配: rent ≤, avg ≤, capacity ≥ かつ少なくとも1つ厳密に優位
        if rent_b <= rent_a and avg_b <= avg_a and cap_b >= cap_a:
            if rent_b < rent_a or avg_b < avg_a or cap_b > cap_a:
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

    # Sort pareto_ids by total_rent ascending (default scatter X axis)
    pareto_combos = [c for c in combinations if c["is_pareto_optimal"]]
    pareto_combos.sort(key=lambda c: c.get("total_rent_jpy_month") or math.inf)
    pareto_ids = [c["combination_id"] for c in pareto_combos]

    return pareto_ids


# ── 注意点分析（v0.3.2: robustness）───────────────────────────────────────────

# 賃料耐性の閾値: tolerance_pct がこの値未満なら警告
_RENT_TOLERANCE_WARNING_PCT = 10.0

def _combo_display_name(combo: Dict[str, Any]) -> str:
    return "+".join(po.get("name", po.get("office_id", "")) for po in combo.get("per_office", []))


def compute_robustness(
    all_combos: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """各パレート最適案の注意点を算出する。

    賃料耐性: 各オフィスの賃料が何%上がるとパレートから脱落するか逆算。
    収容余裕: オフィスごとの残り人数とボトルネック検出。
    """
    pareto = [c for c in all_combos if c.get("is_pareto_optimal")]
    non_pareto = [c for c in all_combos if not c.get("is_pareto_optimal")]
    result: List[Dict[str, Any]] = []

    for combo in pareto:
        rent_tolerance = _compute_rent_tolerance(combo, pareto, non_pareto)
        capacity_headroom = _compute_capacity_headroom(combo)
        result.append({
            "combination_id": combo["combination_id"],
            "rent_tolerance": rent_tolerance,
            "capacity_headroom": capacity_headroom,
        })

    return result


def _compute_rent_tolerance(
    combo: Dict[str, Any],
    pareto: List[Dict[str, Any]],
    non_pareto: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """各オフィスの賃料がいくら上がるとパレートから脱落するか逆算する。

    3軸パレート (total_rent, avg_trip, total_capacity) での脱落条件:
    他の案 B が combo A を支配する = rent_B ≤ rent_A かつ avg_B ≤ avg_A かつ cap_B ≥ cap_A。
    賃料が上がっても avg と capacity は変わらないので、
    avg と capacity で combo を支配しうる案（avg ≤ combo かつ cap ≥ combo）を探し、
    その案の total_rent まで上がったら脱落。
    """
    combo_avg  = combo.get("avg_trip_minutes") or math.inf
    combo_rent = combo.get("total_rent_jpy_month") or 0
    combo_cap  = combo.get("total_capacity") or 0

    # combo を支配しうる案: avg と capacity の両方で combo に勝てる案
    potential_dominators = []
    for other in pareto + non_pareto:
        if other is combo:
            continue
        other_avg  = other.get("avg_trip_minutes") or math.inf
        other_rent = other.get("total_rent_jpy_month") or math.inf
        other_cap  = other.get("total_capacity") or 0
        if other_avg <= combo_avg and other_cap >= combo_cap:
            potential_dominators.append(other)

    if not potential_dominators:
        # avg と capacity で勝てる案がない → 賃料がいくら上がっても脱落しない
        tolerances = []
        for po in combo.get("per_office", []):
            tolerances.append({
                "office_id": po["office_id"],
                "office_name": po.get("name", po["office_id"]),
                "current_rent": po.get("rent_jpy_month") or 0,
                "max_rent_before_drop": None,
                "tolerance_pct": None,
            })
        return tolerances

    # 最も厳しい dominator: total_rent が最も低い案
    # combo の total_rent がこの値を超えると、その案に3軸すべてで負ける
    min_dominator_rent = min(
        d.get("total_rent_jpy_month") or math.inf for d in potential_dominators
    )

    rent_headroom = min_dominator_rent - combo_rent

    tolerances = []
    for po in combo.get("per_office", []):
        office_rent = po.get("rent_jpy_month") or 0
        if office_rent > 0 and rent_headroom >= 0:
            max_office_rent = office_rent + rent_headroom
            tolerance_pct = round((rent_headroom / office_rent) * 100, 1)
        else:
            max_office_rent = None
            tolerance_pct = None

        tolerances.append({
            "office_id": po["office_id"],
            "office_name": po.get("name", po["office_id"]),
            "current_rent": office_rent,
            "max_rent_before_drop": max_office_rent,
            "tolerance_pct": tolerance_pct,
        })

    return tolerances


# 推定定員がこの割合以上埋まっていたら「推定定員ギリギリ」として警告する。
# 定員が floor_area_sqm からの推定値の場合、実際の定員が下振れすると
# 収容不能になりうるため、余裕があるうちに気づけるようにする。
_CAPACITY_TIGHT_ESTIMATE_RATIO = 0.9


def _compute_capacity_headroom(combo: Dict[str, Any]) -> Dict[str, Any]:
    """オフィスごとの収容余裕とボトルネック検出。

    定員が推定値（capacity_estimated）かつ充足率が高いオフィスは、
    推定が下振れすると収容不能になりうるため warnings で警告する。
    """
    per_office_info = []
    total_remaining = 0
    bottleneck_office = None
    bottleneck_remaining = math.inf
    capacity_warnings: List[str] = []

    for po in combo.get("per_office", []):
        cap = po.get("capacity")
        assigned = po.get("assigned_population", 0)
        remaining = (cap - assigned) if cap is not None else None

        # 推定定員にほぼ達しているオフィスを検出（推定は下振れリスクがあるため）
        tight_estimate = bool(
            po.get("capacity_estimated")
            and cap is not None and cap > 0
            and remaining is not None and remaining >= 0
            and assigned >= cap * _CAPACITY_TIGHT_ESTIMATE_RATIO
        )

        per_office_info.append({
            "office_id": po["office_id"],
            "office_name": po.get("name", po["office_id"]),
            "capacity": cap,
            "assigned": assigned,
            "remaining": remaining,
            "tight_estimate": tight_estimate,
        })

        if tight_estimate:
            capacity_warnings.append(
                f"{po.get('name', po['office_id'])}: 推定定員{cap}人に対し{assigned}人配置"
                f"（残り{remaining}人）。定員は推定値のため、余裕を見て再確認を推奨します。"
            )

        if remaining is not None:
            total_remaining += remaining
            if remaining < bottleneck_remaining:
                bottleneck_remaining = remaining
                bottleneck_office = po.get("name", po["office_id"])

    return {
        "total_remaining": total_remaining,
        "bottleneck_office": bottleneck_office,
        "bottleneck_remaining": bottleneck_remaining if bottleneck_remaining < math.inf else None,
        "per_office": per_office_info,
        "warnings": capacity_warnings,
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

# ── Before/After 比較（v0.3.2）────────────────────────────────────────────────

def _compute_baseline_trips(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    baseline: Dict[str, Any],
) -> Dict[str, Optional[float]]:
    """baselineオフィスへの各駅からの通勤時間を計算。"""
    trips: Dict[str, Optional[float]] = {}
    for hs in home_stations:
        t = calc_trip_minutes(
            G, hs["station_id"],
            baseline["nearest_station_id"],
            baseline["last_mile_minutes"],
        )
        trips[hs["station_id"]] = t
    return trips


def compute_baseline_diagnosis(
    baseline: Dict[str, Any],
    home_stations: List[Dict[str, Any]],
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
        bt = baseline_trips.get(hs["station_id"])
        if bt is None:
            continue
        trips.append((bt, hs["count"]))
        total_pop += hs["count"]
        if commute_cost_policy != "ignore":
            if hs.get("commute_allowance_jpy_month") is not None:
                per = hs["commute_allowance_jpy_month"]
                if cap is not None:
                    per = min(per, cap)
            else:
                per = estimate_monthly_commute_cost(bt, policy_days, cap)
            commute_cost += per * hs["count"]

    if total_pop == 0:
        return {}

    weighted = sum(t * c for t, c in trips)
    avg_trip = weighted / total_pop

    sorted_trips = sorted(trips, key=lambda x: x[0])
    p95_th = 0.95 * total_pop
    cum = 0
    p95_trip = 0.0
    for t, c in sorted_trips:
        cum += c
        if cum >= p95_th:
            p95_trip = t
            break

    over_60 = sum(c for t, c in trips if t > 60)
    over_90 = sum(c for t, c in trips if t > 90)

    capacity = baseline.get("capacity_people")
    occupancy_pct = round((total_pop / capacity) * 100, 1) if capacity and capacity > 0 else None
    rent = baseline.get("rent_jpy_month") or 0
    rent_per_person = round(rent / total_pop) if total_pop > 0 and rent > 0 else None

    alerts: List[str] = []
    if occupancy_pct is not None and occupancy_pct > 100:
        alerts.append(f"収容率が100%を超えています（{occupancy_pct}%）")
    if over_90 > 0:
        alerts.append(f"通勤90分超の社員が{over_90}人（{round(over_90 / total_pop * 100)}%）います")
    if over_60 > total_pop * 0.3:
        alerts.append(f"通勤60分超の社員が{over_60}人（{round(over_60 / total_pop * 100)}%）で、全体の3割を超えています")

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
    home_stations: List[Dict[str, Any]],
    assignment: Dict[str, str],
    baseline: Dict[str, Any],
    baseline_trips: Dict[str, Optional[float]],
    policy_days: float,
    commute_cost_policy: str,
    commute_cost_cap: Optional[int],
) -> Dict[str, Any]:
    """案とbaselineの差分を計算する。"""
    # baseline集計
    b_weighted = 0.0
    b_total_pop = 0
    b_trip_list: List[Tuple[float, int]] = []
    b_commute_cost = 0
    cap = commute_cost_cap if commute_cost_policy == "capped" else None

    for hs in home_stations:
        bt = baseline_trips.get(hs["station_id"])
        if bt is None:
            continue
        b_trip_list.append((bt, hs["count"]))
        b_weighted += bt * hs["count"]
        b_total_pop += hs["count"]
        if commute_cost_policy != "ignore":
            if hs.get("commute_allowance_jpy_month") is not None:
                per = hs["commute_allowance_jpy_month"]
                if cap is not None:
                    per = min(per, cap)
            else:
                per = estimate_monthly_commute_cost(bt, policy_days, cap)
            b_commute_cost += per * hs["count"]

    if b_total_pop == 0:
        return {}

    b_avg = b_weighted / b_total_pop
    b_sorted = sorted(b_trip_list, key=lambda x: x[0])
    b_p95_th = 0.95 * b_total_pop
    cum = 0
    b_p95 = 0.0
    for t, c in b_sorted:
        cum += c
        if cum >= b_p95_th:
            b_p95 = t
            break

    b_rent = baseline.get("rent_jpy_month") or 0

    # combo値
    c_avg = combo.get("avg_trip_minutes") or 0
    c_p95 = combo.get("p95_trip_minutes") or 0
    c_rent = combo.get("total_rent_jpy_month") or 0
    c_commute = combo.get("total_commute_cost_jpy_month") or 0

    # 人数比較: comboの各社員がbaselineと比べて改善/悪化
    # combo側のtrip_minutesを per_office.station_breakdown から取得
    combo_trip_by_station: Dict[str, float] = {}
    for po in combo.get("per_office", []):
        oid = po["office_id"]
        for sb in po.get("station_breakdown", []):
            if sb.get("reachable") and sb.get("trip_minutes") is not None:
                sid = sb["station_id"]
                # assignmentからこの駅の社員がこのオフィスに配置されてるか確認
                for hs in home_stations:
                    if hs["station_id"] == sid and assignment.get(_get_group(hs)) == oid:
                        combo_trip_by_station[sid] = sb["trip_minutes"]

    worse = 0
    better = 0
    unchanged = 0
    for hs in home_stations:
        sid = hs["station_id"]
        bt = baseline_trips.get(sid)
        ct = combo_trip_by_station.get(sid)
        if bt is None or ct is None:
            continue
        diff = ct - bt
        if diff > 1:
            worse += hs["count"]
        elif diff < -1:
            better += hs["count"]
        else:
            unchanged += hs["count"]

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
    min_total_capacity = settings.get("min_total_capacity")
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

        # 希望定員フィルタ（採用余地込み）
        # 全オフィスに capacity が設定されているときのみ適用
        # （CSVで容量未入力のオフィスが混ざる場合のフィルタ全滅を防ぐ）
        if min_total_capacity is not None:
            caps = [_get_capacity(o, sqm_per_person) for o in combo_offices]
            if all(c is not None for c in caps):
                total_cap = sum(caps)
                if total_cap < min_total_capacity:
                    continue

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

    # 使われないオフィス（assigned_population=0）を含む案は、選択肢として残すが
    # パレート判定からは除外する（無駄金フィルタ）。
    # ただし、ユーザーが「固定」で指定したオフィスは未使用でも除外対象外にする
    # （固定はユーザーの意思決定なので、たとえ無駄に見えてもパレート対象に残す）。
    fixed_oids_set = set(fixed_offices)
    for combo in evaluated:
        unused_non_fixed = [
            po["office_id"] for po in combo.get("per_office", [])
            if (po.get("assigned_population") or 0) == 0
            and po["office_id"] not in fixed_oids_set
        ]
        unused_fixed = [
            po["office_id"] for po in combo.get("per_office", [])
            if (po.get("assigned_population") or 0) == 0
            and po["office_id"] in fixed_oids_set
        ]
        combo["_has_unused_office"] = bool(unused_non_fixed)
        if unused_fixed:
            combo["unused_fixed_offices"] = unused_fixed
    valid_for_pareto = [c for c in evaluated if not c["_has_unused_office"]]
    valid_after_unused = len(valid_for_pareto)

    # パレートフロンティア抽出（無駄な拠点を含む案は対象外）
    pareto_frontier_ids = mark_pareto_frontier(valid_for_pareto)

    # 無駄な拠点を含む案は is_pareto_optimal=False に固定
    for combo in evaluated:
        if combo["_has_unused_office"]:
            combo["is_pareto_optimal"] = False
        combo.pop("_has_unused_office", None)

    if not pareto_frontier_ids:
        collector.no_pareto_candidates()


    # 注意点分析（v0.3.2: 賃料耐性 + 収容余裕）
    robustness = compute_robustness(evaluated)

    # Before/After 比較（v0.3.2）
    baseline_cfg = settings.get("baseline")
    baseline_diagnosis = None
    if baseline_cfg:
        baseline_trips = _compute_baseline_trips(G, home_stations, baseline_cfg)
        baseline_diagnosis = compute_baseline_diagnosis(
            baseline_cfg, home_stations, baseline_trips,
            policy_days, commute_cost_policy, commute_cost_cap,
        )
        for combo in evaluated:
            combo_offices_for = [o for o in offices if o["office_id"] in combo["selected_offices"]]
            asgn = build_group_assignment(
                G, home_stations, combo_offices_for, fixed_assignment, group_together,
            )
            combo["vs_baseline"] = compute_vs_baseline(
                combo, home_stations, asgn, baseline_cfg, baseline_trips,
                policy_days, commute_cost_policy, commute_cost_cap,
            )

    # Explain 生成（全コンボに対して）
    for combo in evaluated:
        combo["explain"] = generate_explain(combo, evaluated, offices)

    constraints_impact = {
        "total_combinations": total_combinations,
        "after_capacity_filter": valid_after_capacity,
        "after_budget_filter": valid_after_budget,
        "after_commute_filter": valid_after_commute,
        "after_unused_filter": valid_after_unused,
        "pareto_optimal": len(pareto_frontier_ids),
        "vs_previous_round": None,
    }

    return {
        "all_combinations": evaluated,
        "pareto_frontier_ids": pareto_frontier_ids,
        "constraints_impact": constraints_impact,
        "robustness": robustness,
        "baseline_diagnosis": baseline_diagnosis,
    }
