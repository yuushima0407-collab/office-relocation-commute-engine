from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional

import networkx as nx

from cest.engine.kpi import compute_kpis_for_scenario
from cest.engine.ranking import access_score, financial_score, normalize_weights, compute_overall_scores


def run_sensitivity(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    offices: List[Dict[str, Any]],
    policy_days: float,
    settings: Dict[str, Any],
    collector: Any,
) -> Dict[str, Any]:
    """
    Sensitivity analysis: vary last_mile_minutes ±5 for all offices.
    Spec Section 8.4.
    """
    n = len(offices)
    deltas = [-5, 0, 5]
    threshold = settings.get("robust_flip_rate_threshold", 0.10)
    bench_p95 = settings.get("bench_trip_p95_minutes", 90)
    bench_rent = settings.get("bench_rent_jpy_month", 10_000_000)
    weights_raw = settings.get("ranking_weights", {"access": 0.6, "financial": 0.3, "environmental": 0.1})
    thresholds_trip = settings.get("thresholds_trip_minutes", [60, 90])

    # Dummy collector for sub-computations (don't pollute main notices)
    from cest.engine.notices import NoticeCollector
    dummy_collector = NoticeCollector()
    weights_norm = normalize_weights(weights_raw, dummy_collector)

    # Compute baseline best (delta=0 for all)
    baseline_best = _compute_winner(
        G, home_stations, offices, policy_days, thresholds_trip,
        [0] * n, bench_p95, bench_rent, weights_norm,
    )

    # Generate all combinations
    all_combos = list(itertools.product(deltas, repeat=n))
    total_variants = len(all_combos)
    flip_count = 0
    variants = []

    for combo in all_combos:
        variant_id = "_".join(f"{d:+d}" for d in combo)
        assumptions = {}
        for i, office in enumerate(offices):
            assumptions[office["office_id"]] = {
                "last_mile_minutes_delta": combo[i],
                "last_mile_minutes_effective": max(0, office["last_mile_minutes"] + combo[i]),
            }

        variant_best = _compute_winner(
            G, home_stations, offices, policy_days, thresholds_trip,
            list(combo), bench_p95, bench_rent, weights_norm,
        )

        if variant_best != baseline_best:
            flip_count += 1

        variants.append({
            "variant_id": variant_id,
            "assumptions": assumptions,
            "best_scenario_id": variant_best,
        })

    flip_rate = flip_count / total_variants if total_variants > 0 else 0.0
    robust = flip_rate <= threshold

    if robust:
        summary = "前提（駅→オフィス徒歩時間）を±5分変えても、1位は変わりません。"
        next_action = "そのまま会議に出せます。"
    else:
        summary = f"前提を±5分変えると、{flip_rate*100:.0f}%のケースで1位が変わります。結論は不安定です。"
        next_action = "各オフィス候補のラストマイル（徒歩/バス分）を実測または正確な値で入力してから再計算してください。"
        collector.sensitivity_unstable(flip_rate)

    return {
        "robust": robust,
        "flip_rate": round(flip_rate, 6),
        "critical_assumption": "last_mile_minutes",
        "summary": summary,
        "next_action": next_action,
        "variants": variants,
    }


def _compute_winner(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    offices: List[Dict[str, Any]],
    policy_days: float,
    thresholds_trip: List[float],
    lm_deltas: List[int],
    bench_p95: float,
    bench_rent: float,
    weights_norm: Dict[str, float],
) -> Optional[str]:
    """Compute overall winner for a given set of last_mile deltas."""
    axis_data = []
    for i, office in enumerate(offices):
        modified_office = dict(office)
        modified_office["last_mile_minutes"] = max(0, office["last_mile_minutes"] + lm_deltas[i])
        scenario_id = f"scenario_{office['office_id']}"

        result = compute_kpis_for_scenario(
            G, home_stations, modified_office, policy_days,
            thresholds_trip, None, True,
        )
        p95 = result["kpis"]["trip_minutes"]["p95"]
        a_score = access_score(p95, bench_p95)
        f_score_val, f_avail = financial_score(office.get("rent_jpy_month"), bench_rent)

        axis_data.append({
            "scenario_id": scenario_id,
            "access": a_score,
            "financial": f_score_val,
            "environmental": None,
        })

    overall = compute_overall_scores(axis_data, weights_norm)
    if not overall:
        return None
    best = max(overall, key=lambda x: x["overall_score_0_100"])
    return best["scenario_id"]
