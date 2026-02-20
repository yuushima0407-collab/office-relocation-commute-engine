from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import networkx as nx

from cest.engine.graph_loader import load_graph, load_station_master
from cest.engine.kpi import compute_kpis_for_scenario
from cest.engine.ranking import (
    access_score,
    financial_score,
    normalize_weights,
    compute_overall_scores,
    determine_best_scenario,
)
from cest.engine.explain_pack import generate_tradeoffs, generate_if_you_prioritize
from cest.engine.sensitivity import run_sensitivity
from cest.engine.notices import NoticeCollector


def evaluate(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main evaluation pipeline. Takes the full input dict and returns
    the EvaluationReport conforming to v0.1.2 schema.
    """
    collector = NoticeCollector()

    home_stations = inputs["home_station_distribution"]
    offices = inputs["office_candidates"]
    policy = inputs["policy_as_is"]
    settings = inputs["settings"]

    policy_days = policy["office_days_per_week"]
    thresholds_trip = settings.get("thresholds_trip_minutes", [60, 90])
    routing_cfg = settings.get("routing", {})
    graph_id = routing_cfg.get("graph_id", "tokyo_core_v1")
    transfer_penalty = routing_cfg.get("transfer_penalty_minutes", 0)

    # Notice: transfer_penalty
    if transfer_penalty != 0:
        collector.transfer_penalty_unsupported(transfer_penalty)

    # Load graph
    try:
        G = load_graph(graph_id) if graph_id else None
    except FileNotFoundError:
        G = None

    if G is None:
        collector.routing_graph_missing()
        return _build_empty_report(inputs, collector)

    # Check for override usage
    override_count = sum(1 for hs in home_stations if hs.get("office_days_per_week_override") is not None)
    if override_count > 0:
        collector.override_applied(override_count)

    # Resolve baseline
    baseline_office_id, baseline_not_found = _resolve_baseline(settings, offices, collector)

    # Check home stations against graph nodes
    graph_nodes = set(G.nodes())
    for hs in home_stations:
        if hs["station_id"] not in graph_nodes:
            collector.station_id_not_found(hs["station_id"])

    # Station Master for coord checking
    station_master = load_station_master()
    for hs in home_stations:
        if hs["station_id"] not in station_master:
            collector.station_coord_missing(hs["station_id"])

    # Check for rent missing
    for office in offices:
        if office.get("rent_jpy_month") is None:
            collector.rent_missing(office.get("name", office["office_id"]))

    # First pass: compute baseline trips for delta calculation
    baseline_office = _find_office(offices, baseline_office_id)
    baseline_trips: Dict[str, Optional[float]] = {}
    if baseline_office:
        from cest.engine.routing import calc_trip_minutes
        for hs in home_stations:
            trip = calc_trip_minutes(
                G, hs["station_id"],
                baseline_office["nearest_station_id"],
                baseline_office["last_mile_minutes"],
            )
            baseline_trips[hs["station_id"]] = trip

    # Compute per-scenario results
    results: List[Dict[str, Any]] = []
    all_unreachable_count = 0

    for office in offices:
        scenario_id = f"scenario_{office['office_id']}"
        is_baseline = office["office_id"] == baseline_office_id

        scenario_result = compute_kpis_for_scenario(
            G, home_stations, office, policy_days, thresholds_trip,
            baseline_trips, is_baseline,
        )

        unreachable_cnt = scenario_result["unreachable"]["count"]
        all_unreachable_count += unreachable_cnt

        # NO_REACHABLE_POPULATION check
        if scenario_result["kpis"]["population_reachable"] == 0:
            collector.no_reachable_population(office.get("name", office["office_id"]))

        # COVERAGE_LOW check
        if scenario_result["coverage"]["network_covered_ratio"] < 0.90:
            collector.coverage_low(scenario_result["coverage"]["network_covered_ratio"])

        results.append({
            "scenario_id": scenario_id,
            "office_id": office["office_id"],
            **scenario_result,
        })

    # UNREACHABLE_EXISTS (aggregate)
    if all_unreachable_count > 0:
        collector.unreachable_exists(all_unreachable_count)

    # Ranking
    bench_p95 = settings.get("bench_trip_p95_minutes", 90)
    bench_rent = settings.get("bench_rent_jpy_month", 10_000_000)
    weights_raw = settings.get("ranking_weights", {"access": 0.6, "financial": 0.3, "environmental": 0.1})
    weights_norm = normalize_weights(weights_raw, collector)

    access_axis: List[Dict[str, Any]] = []
    financial_axis: List[Dict[str, Any]] = []
    environmental_axis: List[Dict[str, Any]] = []
    scenario_axis_data: List[Dict[str, Any]] = []

    for i, r in enumerate(results):
        office = offices[i]
        p95 = r["kpis"]["trip_minutes"]["p95"]
        a_score = access_score(p95, bench_p95)
        f_score_val, f_avail = financial_score(office.get("rent_jpy_month"), bench_rent)

        access_axis.append({
            "scenario_id": r["scenario_id"],
            "score_0_100": a_score,
            "inputs_available": True,
            "quality_label": "computed",
        })
        financial_axis.append({
            "scenario_id": r["scenario_id"],
            "score_0_100": f_score_val,
            "inputs_available": f_avail,
            "quality_label": "computed",
        })
        environmental_axis.append({
            "scenario_id": r["scenario_id"],
            "score_0_100": None,
            "inputs_available": False,
            "quality_label": "computed",
        })
        scenario_axis_data.append({
            "scenario_id": r["scenario_id"],
            "access": a_score,
            "financial": f_score_val,
            "environmental": None,
        })

    overall = compute_overall_scores(scenario_axis_data, weights_norm)

    # Sensitivity
    sensitivity = run_sensitivity(
        G, home_stations, offices, policy_days, settings, collector,
    )

    # best_scenario_id
    best_scenario_id = determine_best_scenario(overall, sensitivity["robust"])

    # Explain pack
    offices_map = {o["office_id"]: o for o in offices}
    tradeoffs = generate_tradeoffs(results, overall, offices_map)
    if_you_prioritize = generate_if_you_prioritize(
        results,
        {"access": access_axis, "financial": financial_axis},
    )

    # Baseline scenario_id — null when BASELINE_OFFICE_NOT_FOUND fired (spec SSOT)
    if baseline_not_found:
        baseline_scenario_id = None
    else:
        baseline_scenario_id = f"scenario_{baseline_office_id}" if baseline_office_id else None

    return {
        "version": "v0.1.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_scenario_id": baseline_scenario_id,
        "inputs": inputs,
        "results": results,
        "ranking": {
            "weights_normalized": weights_norm,
            "axes": {
                "access": access_axis,
                "financial": financial_axis,
                "environmental": environmental_axis,
            },
            "overall": overall,
            "best_scenario_id": best_scenario_id,
        },
        "explain_pack": {
            "tradeoffs": tradeoffs,
            "if_you_prioritize": if_you_prioritize,
        },
        "sensitivity": sensitivity,
        "notices": collector.notices,
    }


def _resolve_baseline(
    settings: Dict[str, Any],
    offices: List[Dict[str, Any]],
    collector: NoticeCollector,
) -> tuple[str, bool]:
    """Returns (resolved_office_id, not_found_flag)."""
    baseline_id = settings.get("baseline_office_id")
    office_ids = [o["office_id"] for o in offices]

    if baseline_id is not None:
        if baseline_id in office_ids:
            return baseline_id, False
        else:
            collector.baseline_office_not_found(baseline_id)
            return office_ids[0], True
    else:
        return office_ids[0], False


def _find_office(offices: List[Dict[str, Any]], office_id: str) -> Optional[Dict[str, Any]]:
    for o in offices:
        if o["office_id"] == office_id:
            return o
    return None


def _build_empty_report(inputs: Dict[str, Any], collector: NoticeCollector) -> Dict[str, Any]:
    """Fallback report when graph is missing."""
    return {
        "version": "v0.1.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_scenario_id": None,
        "inputs": inputs,
        "results": [],
        "ranking": {
            "weights_normalized": {"access": 1.0, "financial": 0.0, "environmental": 0.0},
            "axes": {"access": [], "financial": [], "environmental": []},
            "overall": [],
            "best_scenario_id": None,
        },
        "explain_pack": {
            "tradeoffs": [],
            "if_you_prioritize": {},
        },
        "sensitivity": {
            "robust": False,
            "flip_rate": 1.0,
            "critical_assumption": "last_mile_minutes",
            "summary": "グラフデータが見つからないため感度分析を実行できません。",
            "next_action": "routing.graph_id の設定を確認してください。",
            "variants": [],
        },
        "notices": collector.notices,
    }
