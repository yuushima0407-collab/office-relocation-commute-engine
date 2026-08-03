"""組み合わせのフィルタ＋評価。

assignment（部署配置）に依存しない軽いチェック（予算・希望定員）を先に済ませ、
それを通過した組み合わせにだけ部署配置・収容人数チェック・KPI評価という
重い処理を行う。フィルタ自体は 予算→希望定員→容量→通勤 の順に適用する。

全体の流れは combination.py の run_v3_pipeline を参照。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import networkx as nx

from cest.models.request import Settings, HomeStation, OfficeCandidate
from cest.engine.combo.common import _get_capacity, _get_group
from cest.engine.combo.assignment import build_group_assignment
from cest.engine.combo.evaluation import evaluate_combo


def filter_and_evaluate_combos(
    G: nx.Graph,
    home_stations: List[HomeStation],
    combos: List[List[OfficeCandidate]],
    required_offices_from_assignment: set,
    settings: Settings,
    policy_days: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """各組み合わせをフィルタして評価する。

    生き残った評価済みコンボと、フィルタ段階ごとの通過数（funnel）を返す。
    """
    sqm_per_person = settings.sqm_per_person
    budget = settings.budget_total_rent_jpy_month
    min_total_capacity = settings.min_total_capacity
    max_p95 = settings.max_p95_trip_minutes
    max_avg = settings.max_avg_trip_minutes
    commute_risk_threshold_minutes = settings.commute_risk_threshold_minutes
    max_exceed_risk_count = settings.max_exceed_risk_count
    # build_group_assignment は辞書のリストを期待してるので、ここで変換する
    fixed_assignment = [fa.model_dump() for fa in settings.fixed_assignment]
    group_together = settings.group_together
    thresholds_trip = settings.thresholds_trip_minutes
    commute_cost_policy = settings.commute_cost_policy
    commute_cost_cap = settings.commute_cost_cap_jpy_month

    valid_after_fixed_assignment = 0
    valid_after_capacity = 0
    valid_after_budget = 0
    valid_after_min_capacity = 0
    valid_after_commute = 0
    evaluated: List[Dict[str, Any]] = []

    for combo_offices in combos:
        combo_office_ids = {o.office_id for o in combo_offices}

        # fixed_assignment で必要なオフィスが含まれているかチェック
        if not required_offices_from_assignment.issubset(combo_office_ids):
            continue
        valid_after_fixed_assignment += 1

        # 予算フィルタ（部署配置は不要、オフィス側の情報だけで判定できる）
        total_rent = sum(o.rent_jpy_month or 0 for o in combo_offices)
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
            oid = office.office_id
            assigned_pop = sum(
                hs.count for hs in home_stations
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
            commute_risk_threshold_minutes,
        )
        if result is None:
            continue

        # 通勤フィルタ（p95・平均・通勤リスク帯の許容人数）
        if max_p95 is not None and result["p95_trip_minutes"] and result["p95_trip_minutes"] > max_p95:
            continue
        if max_avg is not None and result["avg_trip_minutes"] and result["avg_trip_minutes"] > max_avg:
            continue
        if max_exceed_risk_count is not None and result["exceed_risk_count"] > max_exceed_risk_count:
            continue
        valid_after_commute += 1

        evaluated.append(result)

    funnel = {
        "after_fixed_assignment_filter": valid_after_fixed_assignment,
        "after_capacity_filter": valid_after_capacity,
        "after_budget_filter": valid_after_budget,
        "after_min_capacity_filter": valid_after_min_capacity,
        "after_commute_filter": valid_after_commute,
    }
    return evaluated, funnel
