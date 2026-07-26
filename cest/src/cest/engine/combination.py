"""
CEST v0.3 メインパイプライン。

処理の流れ（この並び通りに実行される）:
  1. combo/enumeration  — オフィス組み合わせを列挙
  2. combo/assignment   — 部署配置（このファイルの _filter_and_evaluate_combos から呼ばれる）
  3. combo/evaluation   — 各組み合わせをKPI評価（フィルタも兼ねる）
  4. combo/pareto       — パレートフロンティア抽出
  5. combo/capacity     — 収容余裕分析
  6. combo/baseline     — Before/After比較（baseline指定時のみ）
  7. combo/explain      — 案ごとの自然文説明生成

各ステップの実装詳細は上記の combo/*.py を参照。このファイルには
「どの順で・何を呼ぶか」という全体の流れだけを置く。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from cest.engine.combo.common import _get_capacity, _get_group
from cest.engine.combo.enumeration import enumerate_combinations
from cest.engine.combo.assignment import build_group_assignment
from cest.engine.combo.evaluation import evaluate_combo
from cest.engine.combo.pareto import mark_pareto_frontier
from cest.engine.combo.capacity import compute_capacity_headroom
from cest.engine.combo.baseline import (
    _compute_baseline_trips,
    compute_baseline_diagnosis,
    compute_vs_baseline,
)
from cest.engine.combo.explain import generate_explain
from cest.engine.support.notices import NoticeCollector


def _filter_and_evaluate_combos(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    combos: List[List[Dict[str, Any]]],
    required_offices_from_assignment: set,
    settings: Dict[str, Any],
    policy_days: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """各組み合わせをフィルタして評価する。

    assignment（部署配置）に依存しない軽いチェック（予算・希望定員）を先に済ませ、
    それを通過した組み合わせにだけ部署配置・収容人数チェック・KPI評価という
    重い処理を行う。フィルタ自体は 予算→希望定員→容量→通勤 の順に適用する。

    settings から読むキー: sqm_per_person, budget_total_rent_jpy_month, min_total_capacity,
    max_p95_trip_minutes, max_avg_trip_minutes, fixed_assignment, group_together,
    thresholds_trip_minutes, commute_cost_policy, commute_cost_cap_jpy_month

    生き残った評価済みコンボと、フィルタ段階ごとの通過数（funnel）を返す。
    """
    sqm_per_person = settings.get("sqm_per_person", 3.3)
    budget = settings.get("budget_total_rent_jpy_month")
    min_total_capacity = settings.get("min_total_capacity")
    max_p95 = settings.get("max_p95_trip_minutes")
    max_avg = settings.get("max_avg_trip_minutes")
    fixed_assignment = settings.get("fixed_assignment", [])
    group_together = settings.get("group_together", [])
    thresholds_trip = settings.get("thresholds_trip_minutes", [60, 90])
    commute_cost_policy = settings.get("commute_cost_policy", "full")
    commute_cost_cap = settings.get("commute_cost_cap_jpy_month")

    valid_after_capacity = 0
    valid_after_budget = 0
    valid_after_min_capacity = 0
    valid_after_commute = 0
    evaluated: List[Dict[str, Any]] = []

    for combo_offices in combos:
        combo_office_ids = {o["office_id"] for o in combo_offices}

        # fixed_assignment で必要なオフィスが含まれているかチェック
        if not required_offices_from_assignment.issubset(combo_office_ids):
            continue

        # 予算フィルタ（部署配置は不要、オフィス側の情報だけで判定できる）
        total_rent = sum(o.get("rent_jpy_month") or 0 for o in combo_offices)
        if budget is not None and total_rent > budget:
            continue
        valid_after_budget += 1

        # 希望定員フィルタ（採用余地込み。これも部署配置は不要）
        # 全オフィスに capacity が設定されているときのみ適用
        # （CSVで容量未入力のオフィスが混ざる場合のフィルタ全滅を防ぐ）
        if min_total_capacity is not None:
            caps = [_get_capacity(o, sqm_per_person) for o in combo_offices]
            if all(c is not None for c in caps):
                total_cap = sum(caps)
                if total_cap < min_total_capacity:
                    continue
        valid_after_min_capacity += 1

        # ここから先は部署配置が必要な重い処理
        assignment = build_group_assignment(
            G, home_stations, combo_offices, fixed_assignment, group_together
        )

        # 収容人数チェック（部署配置の結果に依存）
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

        # KPI 計算
        result = evaluate_combo(
            G, home_stations, combo_offices, assignment,
            policy_days, thresholds_trip, sqm_per_person,
            commute_cost_policy, commute_cost_cap,
        )
        if result is None:
            continue

        # 通勤フィルタ（p95・平均）
        if max_p95 is not None and result["p95_trip_minutes"] and result["p95_trip_minutes"] > max_p95:
            continue
        if max_avg is not None and result["avg_trip_minutes"] and result["avg_trip_minutes"] > max_avg:
            continue
        valid_after_commute += 1

        evaluated.append(result)

    funnel = {
        "after_capacity_filter": valid_after_capacity,
        "after_budget_filter": valid_after_budget,
        "after_min_capacity_filter": valid_after_min_capacity,
        "after_commute_filter": valid_after_commute,
    }
    return evaluated, funnel


def _exclude_wasteful_from_pareto(
    evaluated: List[Dict[str, Any]],
    fixed_offices: List[str],
) -> List[Dict[str, Any]]:
    """使われないオフィス（assigned_population=0）を含む案は、選択肢として残すが
    パレート判定からは除外する（無駄金フィルタ）。
    ただし、ユーザーが「固定」で指定したオフィスは未使用でも除外対象外にする
    （固定はユーザーの意思決定なので、たとえ無駄に見えてもパレート対象に残す）。

    パレート判定対象の案（無駄な拠点を含まないもの）を返す。各comboには
    `_has_unused_office` フラグが立てられ、`_finalize_pareto_flags` で後片付けされる。
    """
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
    return [c for c in evaluated if not c["_has_unused_office"]]


def _finalize_pareto_flags(evaluated: List[Dict[str, Any]]) -> None:
    """無駄な拠点を含む案は is_pareto_optimal=False に固定し、内部フラグを片付ける。"""
    for combo in evaluated:
        if combo["_has_unused_office"]:
            combo["is_pareto_optimal"] = False
        combo.pop("_has_unused_office", None)


def _apply_baseline_comparison(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    evaluated: List[Dict[str, Any]],
    settings: Dict[str, Any],
    policy_days: float,
) -> Optional[Dict[str, Any]]:
    """baseline が指定されていれば現状診断を作り、各comboに vs_baseline を付与する。

    settings から読むキー: baseline, commute_cost_policy, commute_cost_cap_jpy_month
    """
    baseline_cfg = settings.get("baseline")
    if not baseline_cfg:
        return None

    commute_cost_policy = settings.get("commute_cost_policy", "full")
    commute_cost_cap = settings.get("commute_cost_cap_jpy_month")

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
    列挙 → フィルタ評価 → パレート抽出 → 注意点分析 → Before/After比較 → explain生成、の順。
    """
    num_offices_list = settings.get("num_offices", [1])
    fixed_offices = settings.get("fixed_offices", [])
    fixed_assignment = settings.get("fixed_assignment", [])

    # fixed_assignment で参照されるオフィスIDを収集（これらを含まない組み合わせは除外）
    required_offices_from_assignment = {
        item.get("office_id", "") for item in fixed_assignment if item.get("office_id")
    }

    # 1. 組み合わせ列挙
    combos = enumerate_combinations(offices, num_offices_list, fixed_offices)
    total_combinations = len(combos)

    # 2. 部署配置 + フィルタ（容量→予算→希望定員→通勤）を通過した組み合わせを評価
    evaluated, funnel = _filter_and_evaluate_combos(
        G, home_stations, combos, required_offices_from_assignment, settings, policy_days,
    )

    # 3. パレートフロンティア抽出（無駄な拠点を含む案は対象外）
    valid_for_pareto = _exclude_wasteful_from_pareto(evaluated, fixed_offices)
    valid_after_unused = len(valid_for_pareto)
    pareto_frontier_ids = mark_pareto_frontier(valid_for_pareto)
    _finalize_pareto_flags(evaluated)
    if not pareto_frontier_ids:
        collector.no_pareto_candidates()

    # 4. 収容余裕分析
    capacity_headroom = compute_capacity_headroom(evaluated)

    # 5. Before/After 比較（baseline指定時のみ）
    baseline_diagnosis = _apply_baseline_comparison(
        G, home_stations, evaluated, settings, policy_days,
    )

    # 6. Explain 生成（全コンボに対して）
    for combo in evaluated:
        combo["explain"] = generate_explain(combo, evaluated)

    constraints_impact = {
        "total_combinations": total_combinations,
        "after_capacity_filter": funnel["after_capacity_filter"],
        "after_budget_filter": funnel["after_budget_filter"],
        "after_min_capacity_filter": funnel["after_min_capacity_filter"],
        "after_commute_filter": funnel["after_commute_filter"],
        "after_unused_filter": valid_after_unused,
        "pareto_optimal": len(pareto_frontier_ids),
        "vs_previous_round": None,
    }

    return {
        "all_combinations": evaluated,
        "pareto_frontier_ids": pareto_frontier_ids,
        "constraints_impact": constraints_impact,
        "capacity_headroom": capacity_headroom,
        "baseline_diagnosis": baseline_diagnosis,
    }
