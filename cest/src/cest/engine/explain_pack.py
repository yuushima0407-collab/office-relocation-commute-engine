from __future__ import annotations

from typing import Any, Dict, List, Optional


def generate_tradeoffs(
    results: List[Dict[str, Any]],
    overall: List[Dict[str, Any]],
    offices: Dict[str, Dict[str, Any]],
) -> List[str]:
    """
    Generate tradeoff texts comparing top-2 overall scenarios.
    Spec Section 8.2.
    """
    if len(overall) < 2:
        return []

    sorted_overall = sorted(overall, key=lambda x: -x["overall_score_0_100"])
    a_id = sorted_overall[0]["scenario_id"]
    b_id = sorted_overall[1]["scenario_id"]

    a_result = _find_result(results, a_id)
    b_result = _find_result(results, b_id)
    if a_result is None or b_result is None:
        return []

    a_name = offices.get(a_result["office_id"], {}).get("name", a_id)
    b_name = offices.get(b_result["office_id"], {}).get("name", b_id)

    candidates = []

    # Candidate 1: p95_trip_minutes
    a_p95 = a_result["kpis"]["trip_minutes"]["p95"]
    b_p95 = b_result["kpis"]["trip_minutes"]["p95"]
    if a_p95 is not None and b_p95 is not None:
        delta_p95 = a_p95 - b_p95
        direction = "短い" if delta_p95 < 0 else "長い"
        candidates.append({
            "abs": abs(delta_p95),
            "text": f"{a_name}は{b_name}より p95(片道)が {abs(delta_p95):.0f}分 {direction}",
        })

    # Candidate 2: 90分超割合
    a_exceed = _get_exceed_share(a_result, 90)
    b_exceed = _get_exceed_share(b_result, 90)
    if a_exceed is not None and b_exceed is not None:
        delta_exceed = a_exceed - b_exceed
        direction = "少ない" if delta_exceed < 0 else "多い"
        candidates.append({
            "abs": abs(delta_exceed) * 100,
            "text": f"{a_name}は90分超の社員が {abs(delta_exceed)*100:.1f}pt {direction}",
        })

    # Candidate 3: 家賃
    a_office = offices.get(a_result["office_id"], {})
    b_office = offices.get(b_result["office_id"], {})
    a_rent = a_office.get("rent_jpy_month")
    b_rent = b_office.get("rent_jpy_month")
    if a_rent is not None and b_rent is not None:
        delta_rent = a_rent - b_rent
        direction = "安い" if delta_rent < 0 else "高い"
        candidates.append({
            "abs": abs(delta_rent),
            "text": f"{a_name}は家賃が月{abs(delta_rent):,}円 {direction}",
        })

    # Candidate 4: 最悪駅 Top1 (largest absolute delta)
    worst = _find_worst_station(a_result)
    if worst is not None:
        direction = "改善" if worst["delta"] < 0 else "悪化"
        candidates.append({
            "abs": abs(worst["delta"]),
            "text": f"{worst['station_id']}駅の{worst['count']}人が、{a_name}では平均{abs(worst['delta']):.0f}分{direction}",
        })

    # Sort by abs descending, take top 2
    candidates.sort(key=lambda x: -x["abs"])
    return [c["text"] for c in candidates[:2]]


def generate_if_you_prioritize(
    results: List[Dict[str, Any]],
    axis_scores: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[str]]:
    """
    Spec Section 8.3.
    """
    iyp: Dict[str, List[str]] = {}

    # access
    access_scores = axis_scores.get("access", [])
    valid_access = [s for s in access_scores if s["score_0_100"] is not None]
    if valid_access:
        best = max(valid_access, key=lambda s: s["score_0_100"])
        iyp["access"] = [best["scenario_id"]]

    # financial
    fin_scores = axis_scores.get("financial", [])
    valid_fin = [s for s in fin_scores if s["inputs_available"] and s["score_0_100"] is not None]
    if valid_fin:
        best = max(valid_fin, key=lambda s: s["score_0_100"])
        iyp["financial"] = [best["scenario_id"]]

    return iyp


def _find_result(results: List[Dict[str, Any]], scenario_id: str) -> Optional[Dict[str, Any]]:
    for r in results:
        if r["scenario_id"] == scenario_id:
            return r
    return None


def _get_exceed_share(result: Dict[str, Any], threshold: float) -> Optional[float]:
    for th in result["kpis"].get("thresholds", []):
        if th["trip_minutes"] == threshold:
            return th["exceed_share"]
    return None


def _find_worst_station(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    worst = None
    worst_abs = 0.0
    for sb in result.get("station_breakdown", []):
        delta = sb.get("delta_vs_baseline_trip_minutes")
        if delta is not None and abs(delta) > worst_abs:
            worst_abs = abs(delta)
            worst = {
                "station_id": sb["station_id"],
                "count": sb["count"],
                "delta": delta,
            }
    return worst
