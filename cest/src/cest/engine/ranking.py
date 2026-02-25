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


# ── v0.3 追加 ────────────────────────────────────────────────────────────────

def _interpolate(x: float, points: List[Tuple[float, float]]) -> float:
    """
    piecewise-linear interpolation.
    points: [(x0, y0), (x1, y1), ...] with x sorted ascending.
    """
    if not points:
        return 0.0
    points = sorted(points, key=lambda p: p[0])
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points[:-1], points[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return points[-1][1]


def _mean_of_available(*values: Optional[float]) -> Optional[float]:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def hazard_score(office_candidate: Dict[str, Any]) -> Optional[float]:
    """
    0-100。高いほど安全。
    station_hazard.json の flood_depth_m / seismic_rank からスコアを算出する。
    """
    from cest.engine.graph_loader import load_station_hazard

    station_id = office_candidate.get("nearest_station_id")
    if station_id is None:
        return None

    station_hazard = load_station_hazard()
    h = station_hazard.get(station_id)
    if not h:
        return None

    flood_depth = h.get("flood_depth_m")
    seismic_rank = h.get("seismic_rank")

    flood_score: Optional[float]
    if flood_depth is None:
        flood_score = None
    else:
        flood_score = _interpolate(
            float(flood_depth),
            [(0.0, 100.0), (0.5, 70.0), (1.0, 50.0), (3.0, 10.0), (5.0, 0.0)],
        )

    seismic_score: Optional[float]
    if seismic_rank is None:
        seismic_score = None
    else:
        try:
            seismic_rank_f = float(seismic_rank)
        except (TypeError, ValueError):
            seismic_score = None
        else:
            seismic_score = (5.0 - seismic_rank_f) * 25.0

    return _mean_of_available(flood_score, seismic_score)
