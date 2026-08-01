"""パレートフロンティア抽出。

全体の流れは combination.py の run_v3_pipeline を参照。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List


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

    for combo in combinations:
        dominated = _is_pareto_dominated(combo, combinations)
        combo["is_pareto_optimal"] = not dominated

    # Sort pareto_ids by total_rent ascending (default scatter X axis)
    pareto_combos = [c for c in combinations if c["is_pareto_optimal"]]
    pareto_combos.sort(key=lambda c: c.get("total_rent_jpy_month") or math.inf)
    pareto_ids = [c["combination_id"] for c in pareto_combos]

    return pareto_ids


def exclude_wasteful_from_pareto(
    evaluated: List[Dict[str, Any]],
    fixed_offices: List[str],
) -> List[Dict[str, Any]]:
    """使われないオフィス（assigned_population=0）を含む案は、選択肢として残すが
    パレート判定からは除外する（無駄金フィルタ）。
    ただし、ユーザーが「固定」で指定したオフィスは未使用でも除外対象外にする
    （固定はユーザーの意思決定なので、たとえ無駄に見えてもパレート対象に残す）。

    パレート判定対象の案（無駄な拠点を含まないもの）を返す。各comboには
    `_has_unused_office` フラグが立てられ、`finalize_pareto_flags` で後片付けされる。
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


def finalize_pareto_flags(evaluated: List[Dict[str, Any]]) -> None:
    """無駄な拠点を含む案は is_pareto_optimal=False に固定し、内部フラグを片付ける。"""
    for combo in evaluated:
        if combo["_has_unused_office"]:
            combo["is_pareto_optimal"] = False
        combo.pop("_has_unused_office", None)
