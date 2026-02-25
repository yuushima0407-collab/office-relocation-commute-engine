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

    return {
        "selected_offices": [o["office_id"] for o in offices],
        "num_offices": len(offices),
        "total_rent_jpy_month": total_rent,
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

def _is_pareto_dominated(combo: Dict[str, Any], all_combos: List[Dict[str, Any]], commute_key: str = "p95_trip_minutes") -> bool:
    """Check if combo is dominated by any other combo on (commute_key, total_rent_jpy_month)."""
    val_a = combo.get(commute_key) or math.inf
    rent_a = combo["total_rent_jpy_month"]
    for other in all_combos:
        if other is combo:
            continue
        val_b = other.get(commute_key) or math.inf
        rent_b = other["total_rent_jpy_month"]
        if val_b <= val_a and rent_b <= rent_a and (val_b < val_a or rent_b < rent_a):
            return True
    return False


def mark_pareto_frontier(
    combinations: List[Dict[str, Any]],
    commute_key: str = "p95_trip_minutes",
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
        dominated = _is_pareto_dominated(combo, combinations, commute_key)
        combo["is_pareto_optimal"] = not dominated
        if not dominated:
            pareto_ids.append(combo["combination_id"])

    # Sort pareto_ids by commute ascending
    pareto_combos = [c for c in combinations if c["is_pareto_optimal"]]
    pareto_combos.sort(key=lambda c: c.get(commute_key) or math.inf)
    pareto_ids = [c["combination_id"] for c in pareto_combos]

    return pareto_ids


# ── 感度分析（v0.3）────────────────────────────────────────────────────────

def compute_sensitivity_v3(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    offices_all: List[Dict[str, Any]],
    all_combos: List[Dict[str, Any]],
    settings: Dict[str, Any],
    policy_days: float,
) -> Dict[str, Any]:
    thresholds_trip = settings.get("thresholds_trip_minutes", [60, 90])
    sqm_per_person = settings.get("sqm_per_person", 3.3)
    fixed_assignment = settings.get("fixed_assignment", [])
    group_together = settings.get("group_together", [])
    office_by_id = {o["office_id"]: o for o in offices_all}

    pareto = [c for c in all_combos if c.get("is_pareto_optimal")]
    details = []

    # ── 1. last_mile ±5分 ──────────────────────────────────────────────────
    # Re-evaluate all combos with ±5min, then check if pareto frontier changes
    last_mile_ranking_changed = False

    if len(pareto) > 0:
        original_pareto_ids = set(c["combination_id"] for c in pareto)

        for delta in [-5, +5]:
            perturbed_results = []
            for combo in all_combos:
                selected_ids = combo["selected_offices"]
                selected_offices = [office_by_id[oid] for oid in selected_ids if oid in office_by_id]
                modified = [
                    {**o, "last_mile_minutes": max(0, o["last_mile_minutes"] + delta)}
                    for o in selected_offices
                ]
                asgn = build_group_assignment(G, home_stations, modified, fixed_assignment, group_together)
                result = evaluate_combo(G, home_stations, modified, asgn, policy_days, thresholds_trip, sqm_per_person)
                if result:
                    result["combination_id"] = combo["combination_id"]
                    perturbed_results.append(result)

            if perturbed_results:
                # Check pareto on perturbed results
                for pr in perturbed_results:
                    pr["is_pareto_optimal"] = not _is_pareto_dominated(pr, perturbed_results)
                new_pareto_ids = set(pr["combination_id"] for pr in perturbed_results if pr["is_pareto_optimal"])
                if new_pareto_ids != original_pareto_ids:
                    last_mile_ranking_changed = True
                    break

    lm_desc = "全パレート最適案がフロンティア上に維持" if not last_mile_ranking_changed else "ラストマイル変動でパレートフロンティアの構成が変化"
    details.append({
        "parameter": "last_mile_minutes ±5min",
        "ranking_changed": last_mile_ranking_changed,
        "description": lm_desc,
    })

    # ── 2. 出社日数変更 ────────────────────────────────────────────────────
    # p95 is one-way trip, independent of days.
    # But weekly load = p95 * 2 * days changes. Check if pareto ranking on weekly load changes.
    alt_days = 5.0 if policy_days <= 3 else 3.0
    days_ranking_changed = False

    if len(pareto) > 1:
        # With different days, re-evaluate all combos
        alt_results = []
        for combo in all_combos:
            selected_ids = combo["selected_offices"]
            selected_offices = [office_by_id[oid] for oid in selected_ids if oid in office_by_id]
            asgn = build_group_assignment(G, home_stations, selected_offices, fixed_assignment, group_together)
            result = evaluate_combo(G, home_stations, selected_offices, asgn, alt_days, thresholds_trip, sqm_per_person)
            if result:
                result["combination_id"] = combo["combination_id"]
                alt_results.append(result)

        if alt_results:
            original_pareto_ids = set(c["combination_id"] for c in pareto)
            for ar in alt_results:
                ar["is_pareto_optimal"] = not _is_pareto_dominated(ar, alt_results)
            new_pareto_ids = set(ar["combination_id"] for ar in alt_results if ar["is_pareto_optimal"])
            if new_pareto_ids != original_pareto_ids:
                days_ranking_changed = True

    scenario_label = f"出社日数 {policy_days:.0f}日→{alt_days:.0f}日"
    days_desc = (
        "パレートフロンティアの構成が変化" if days_ranking_changed
        else "パレートフロンティアの構成は維持"
    )
    details.append({
        "parameter": scenario_label,
        "ranking_changed": days_ranking_changed,
        "description": days_desc,
    })

    ranking_stable = not any(d["ranking_changed"] for d in details)

    if ranking_stable:
        summary = "ラストマイルを±5分変動させても、出社日数を変更しても、パレートフロンティアの順位は変わりません。結果は安定しています。"
    else:
        unstable_params = [d["parameter"] for d in details if d["ranking_changed"]]
        summary = f"{', '.join(unstable_params)}を変更するとパレートフロンティアの構成が変わります。前提条件の精度を確認してください。"

    return {
        "ranking_stable": ranking_stable,
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
    total_rent = combo["total_rent_jpy_month"]
    total_pop = combo["total_population"]
    exceed_60 = combo["exceed_60_count"]
    per_office = combo["per_office"]
    dist = combo.get("distribution", {})

    # commute
    commute = {
        "headline": f"平均通勤{avg:.0f}分、最も長い人でも{p95:.0f}分",
        "detail": f"社員{total_pop}人中、60分超えは{exceed_60}人",
        "distribution": f"30分未満: {dist.get('under_30', 0)}人 / 30-60分: {dist.get('30_to_60', 0)}人 / 60分超: {dist.get('60_to_90', 0) + dist.get('over_90', 0)}人",
    }

    # cost
    rent_parts = []
    for po in per_office:
        rent = po.get("rent_jpy_month")
        if rent:
            rent_parts.append(f"{po['name']}{rent // 10000}万")
    cost = {
        "headline": f"月額{total_rent // 10000}万円" if total_rent else "家賃未入力",
        "detail": " + ".join(rent_parts) if rent_parts else "",
    }

    # capacity
    all_feasible = all(
        (po["capacity_headroom"] is None or po["capacity_headroom"] >= 0)
        for po in per_office
    )
    cap_details = []
    cap_warnings = []
    for po in per_office:
        cap = po.get("capacity")
        pop = po["assigned_population"]
        hr = po.get("capacity_headroom")
        estimated_note = "※推定値" if po.get("capacity_estimated") else ""
        if cap is not None:
            cap_details.append(
                f"{po['name']}: {pop}人配置、推定収容{cap}人（余裕{hr}人）{estimated_note}"
            )
            if hr is not None and hr < 20:
                cap_warnings.append(f"{po['name']}は余裕が少なく、{hr}人以上の増員で収容超過の可能性あり")
        else:
            cap_details.append(f"{po['name']}: {pop}人配置（収容人数未設定）")

    capacity = {
        "headline": "全拠点で収容可能" if all_feasible else "収容人数を確認してください",
        "detail": " / ".join(cap_details),
    }
    if cap_warnings:
        capacity["warning"] = " / ".join(cap_warnings)
    if any(po.get("capacity_estimated") for po in per_office):
        capacity["note"] = "※推定値。実際の収容可能人数は設備・レイアウトにより異なります"

    # assignment
    asgn_detail = []
    office_groups: Dict[str, List[str]] = {}
    for item in combo.get("assignment", []):
        oid = item["assigned_office_id"]
        office_groups.setdefault(oid, []).append(f"{item['group']}({item['population']}人)")
    for oid, groups in office_groups.items():
        office_name = next((po["name"] for po in per_office if po["office_id"] == oid), oid)
        asgn_detail.append(f"{office_name} → {', '.join(groups)}")

    assignment_explain = {
        "headline": f"{len(combo.get('assignment', []))}部署の配置",
        "detail": asgn_detail,
        "rationale": "各部署を通勤負荷が最小になるオフィスに配置",
    }

    # vs_alternatives — compare with other combos (rent順で近いものを選ぶ)
    combo_id = combo.get("combination_id", "")
    vs = []
    others = sorted(
        [c for c in all_combos if c.get("combination_id") != combo_id],
        key=lambda c: c["total_rent_jpy_month"],
    )
    for other in others[:3]:  # limit to 3
        other_p95 = other.get("p95_trip_minutes") or 0
        other_rent = other["total_rent_jpy_month"]
        rent_diff = other_rent - total_rent
        p95_diff = other_p95 - p95
        parts = []
        if rent_diff != 0:
            parts.append(f"月額{abs(rent_diff) // 10000}万{'高い' if rent_diff > 0 else '安い'}")
        if p95_diff != 0:
            parts.append(f"通勤最長が{abs(p95_diff):.0f}分{'長い' if p95_diff > 0 else '短い'}")
        other_names = "+".join(
            next((po["name"] for po in other["per_office"] if po["office_id"] == oid), oid)
            for oid in other["selected_offices"]
        )
        if parts:
            vs.append(f"{other_names}案: {', '.join(parts)}")

    return {
        "commute": commute,
        "cost": cost,
        "capacity": capacity,
        "assignment": assignment_explain,
        "vs_alternatives": vs,
    }


# ── メインパイプライン ───────────────────────────────────────────────────────

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
            policy_days, thresholds_trip, sqm_per_person
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

    # 収容余裕の通知
    for combo in evaluated:
        if combo.get("is_pareto_optimal"):
            for po in combo.get("per_office", []):
                hr = po.get("capacity_headroom")
                if hr is not None and 0 <= hr < 20:
                    collector.capacity_tight(po["name"], hr)

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
