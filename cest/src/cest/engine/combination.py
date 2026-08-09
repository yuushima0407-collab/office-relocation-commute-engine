"""
CEST v0.3 メインパイプライン。

処理の流れ（この並び通りに実行される）:
  1. combo/enumeration  — オフィス組み合わせを列挙
  2. combo/filter        — 部署配置・フィルタ・KPI評価
  3. combo/pareto        — 無駄拠点（未使用オフィス）を含む案を除外
  4. combo/pareto        — パレートフロンティア抽出
  5. combo/capacity      — 収容余裕分析
  6. combo/baseline      — Before/After比較（baseline指定時のみ）
  7. combo/explain       — 案ごとの自然文説明生成

各ステップの実装詳細は上記の combo/*.py を参照。このファイルには
「どの順で・何を呼ぶか」という全体の流れだけを置く。
"""
from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx

from cest.models.request import Settings, HomeStation, OfficeCandidate
from cest.engine.combo.enumeration import enumerate_combinations
from cest.engine.combo.filter import filter_and_evaluate_combos
from cest.engine.combo.pareto import (
    mark_pareto_frontier,
    exclude_wasteful_offices,
)
from cest.engine.combo.capacity import compute_capacity_headroom
from cest.engine.combo.baseline import apply_baseline_comparison
from cest.engine.combo.explain import generate_explain
from cest.engine.support.notices import NoticeCollector


def run_v3_pipeline(
    G: nx.Graph,
    home_stations: List[HomeStation],
    offices: List[OfficeCandidate],
    policy_days: float,
    settings: Settings,
    collector: NoticeCollector,
) -> Dict[str, Any]:
    """
    v0.3 メインパイプライン。
    列挙 → フィルタ評価 → パレート抽出 → 収容余裕分析 → Before/After比較 → explain生成、の順。
    """
    num_offices_list = settings.num_offices
    fixed_offices = settings.fixed_offices

    # fixed_assignment で参照されるオフィスIDを収集（これらを含まない組み合わせは除外）
    required_offices_from_assignment = {
        item.office_id for item in settings.fixed_assignment if item.office_id
    }

    # 1. 組み合わせ列挙
    combos = enumerate_combinations(offices, num_offices_list, fixed_offices)
    total_combinations = len(combos)

    # 2. 部署配置 + フィルタ（容量→予算→希望定員→通勤）を通過した組み合わせを評価
    evaluated, funnel = filter_and_evaluate_combos(
        G, home_stations, combos, required_offices_from_assignment, settings, policy_days,
    )

    # 3. 無駄拠点（未使用オフィス）を含む案を除外
    evaluated = exclude_wasteful_offices(evaluated, fixed_offices)
    valid_after_unused = len(evaluated)

    # 4. パレートフロンティア抽出
    pareto_frontier_ids = mark_pareto_frontier(evaluated)
    if not pareto_frontier_ids:
        collector.no_pareto_candidates()

    # 5. 収容余裕分析
    capacity_headroom = compute_capacity_headroom(evaluated)

    # 6. Before/After 比較（baseline指定時のみ）
    baseline_diagnosis = apply_baseline_comparison(
        G, home_stations, evaluated, settings, policy_days,
    )

    # 7. Explain 生成（全コンボに対して）
    for combo in evaluated:
        combo["explain"] = generate_explain(combo, evaluated)

    constraints_impact = {
        "total_combinations": total_combinations,
        "after_fixed_assignment_filter": funnel["after_fixed_assignment_filter"],
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
