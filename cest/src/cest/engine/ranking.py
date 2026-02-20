from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from cest.engine.notices import NoticeCollector


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def access_score(
    p95_trip_minutes: Optional[float],
    bench_trip_p95_minutes: float,
) -> Optional[float]:
    if p95_trip_minutes is None:
        return None
    return round(100 * clamp(1 - (p95_trip_minutes / bench_trip_p95_minutes), 0, 1), 3)


def financial_score(
    rent_jpy_month: Optional[int],
    bench_rent_jpy_month: float,
) -> Tuple[Optional[float], bool]:
    """Returns (score, inputs_available)."""
    if rent_jpy_month is None:
        return None, False
    score = round(100 * clamp(1 - (rent_jpy_month / bench_rent_jpy_month), 0, 1), 3)
    return score, True


def normalize_weights(
    weights: Dict[str, float],
    collector: NoticeCollector,
) -> Dict[str, float]:
    total = sum(weights.values())
    if total == 0:
        collector.weights_all_zero_fallback()
        return {"access": 1.0, "financial": 0.0, "environmental": 0.0}
    return {k: round(v / total, 6) for k, v in weights.items()}


def compute_overall_scores(
    scenario_axis_scores: List[Dict[str, Any]],
    weights_normalized: Dict[str, float],
) -> List[Dict[str, Any]]:
    """
    scenario_axis_scores: [
        {
            "scenario_id": str,
            "access": float|None,
            "financial": float|None,
            "environmental": float|None,
        }
    ]
    Returns: [{"scenario_id": str, "overall_score_0_100": float}]
    """
    results = []
    for s in scenario_axis_scores:
        score = 0.0
        for axis in ["access", "financial", "environmental"]:
            axis_score = s.get(axis)
            if axis_score is not None:
                score += weights_normalized[axis] * axis_score
        results.append({
            "scenario_id": s["scenario_id"],
            "overall_score_0_100": round(clamp(score, 0, 100), 3),
        })
    return results


def determine_best_scenario(
    overall: List[Dict[str, Any]],
    robust: bool,
) -> Optional[str]:
    if not robust:
        return None
    if not overall:
        return None
    best = max(overall, key=lambda x: x["overall_score_0_100"])
    return best["scenario_id"]
