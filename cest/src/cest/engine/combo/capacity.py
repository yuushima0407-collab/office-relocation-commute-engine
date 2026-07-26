"""収容余裕分析。

全体の流れは combination.py の run_v3_pipeline を参照。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

# 推定定員がこの割合以上埋まっていたら「推定定員ギリギリ」として警告する。
# 定員が floor_area_sqm からの推定値の場合、実際の定員が下振れすると
# 収容不能になりうるため、余裕があるうちに気づけるようにする。
_CAPACITY_TIGHT_ESTIMATE_RATIO = 0.9


def compute_capacity_headroom(
    all_combos: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """各パレート最適案の収容余裕とボトルネックを算出する。"""
    pareto = [c for c in all_combos if c.get("is_pareto_optimal")]
    result: List[Dict[str, Any]] = []

    for combo in pareto:
        result.append({
            "combination_id": combo["combination_id"],
            "capacity_headroom": _compute_capacity_headroom(combo),
        })

    return result


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
