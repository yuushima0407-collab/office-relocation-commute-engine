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
