from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from cest.engine.routing import calc_trip_minutes


def _weighted_stats(
    values_counts: List[Tuple[float, int]],
) -> Dict[str, Optional[float]]:
    """Compute avg, p50, p95 from (value, count) pairs. Returns all-null if empty."""
    if not values_counts:
        return {"avg": None, "p50": None, "p95": None}

    expanded: List[float] = []
    for val, cnt in values_counts:
        expanded.extend([val] * cnt)

    if not expanded:
        return {"avg": None, "p50": None, "p95": None}

    expanded.sort()
    total = len(expanded)
    avg = sum(expanded) / total

    def percentile(data: List[float], p: float) -> float:
        k = (p / 100.0) * (len(data) - 1)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[f]
        return data[f] * (c - k) + data[c] * (k - f)

    return {
        "avg": round(avg, 3),
        "p50": round(percentile(expanded, 50), 3),
        "p95": round(percentile(expanded, 95), 3),
    }


def compute_kpis_for_scenario(
    G: nx.Graph,
    home_stations: List[Dict[str, Any]],
    office: Dict[str, Any],
    policy_days: float,
    thresholds_trip_minutes: List[float],
    baseline_trips: Optional[Dict[str, Optional[float]]],
    is_baseline: bool,
) -> Dict[str, Any]:
    """
    Compute all KPIs for a single scenario (office x policy).

    Returns: {
        kpis, station_breakdown, unreachable, coverage, policy_applied
    }
    """
    office_station = office["nearest_station_id"]
    last_mile = office["last_mile_minutes"]

    station_breakdown: List[Dict[str, Any]] = []
    unreachable_stations: List[Dict[str, Any]] = []
    trip_values: List[Tuple[float, int]] = []

    population_total = 0
    population_reachable = 0
    override_count_total = 0

    applied_days_sum = 0.0

    for hs in home_stations:
        sid = hs["station_id"]
        count = hs["count"]
        override = hs.get("office_days_per_week_override")
        population_total += count

        if override is not None:
            override_count_total += count

        trip = calc_trip_minutes(G, sid, office_station, last_mile)
        reachable = trip is not None

        if reachable:
            population_reachable += count
            trip_values.append((trip, count))

        # threshold_results
        threshold_results = []
        for th in thresholds_trip_minutes:
            exceeds = False if not reachable else (trip > th)
            threshold_results.append({"trip_minutes": th, "exceeds": exceeds})

        # delta_vs_baseline_trip_minutes
        delta: Optional[float] = None
        if not is_baseline and baseline_trips is not None:
            baseline_trip = baseline_trips.get(sid)
            if reachable and baseline_trip is not None:
                delta = round(trip - baseline_trip, 3)

        sb_entry: Dict[str, Any] = {
            "station_id": sid,
            "count": count,
            "reachable": reachable,
            "trip_minutes": round(trip, 3) if reachable else None,
            "threshold_results": threshold_results,
            "delta_vs_baseline_trip_minutes": delta,
        }
        station_breakdown.append(sb_entry)

        if not reachable:
            unreachable_stations.append({"station_id": sid, "count": count})

        # policy applied days for this station
        days = override if override is not None else policy_days
        applied_days_sum += days * count

    # policy_applied
    applied_days_avg = applied_days_sum / population_total if population_total > 0 else policy_days
    override_share = override_count_total / population_total if population_total > 0 else 0.0

    # three_stats
    trip_stats = _weighted_stats(trip_values)

    # round_trip
    rt_values = [(v * 2, c) for v, c in trip_values]
    rt_stats = _weighted_stats(rt_values)

    # weekly (round_trip * applied_days per station)
    weekly_values: List[Tuple[float, int]] = []
    for hs in home_stations:
        sid = hs["station_id"]
        count = hs["count"]
        override = hs.get("office_days_per_week_override")
        days = override if override is not None else policy_days
        trip = calc_trip_minutes(G, sid, office_station, last_mile)
        if trip is not None:
            weekly = trip * 2 * days
            weekly_values.append((weekly, count))
    weekly_stats = _weighted_stats(weekly_values)

    # thresholds aggregate
    thresholds_agg = []
    for th in thresholds_trip_minutes:
        exceed_count = 0
        for sb in station_breakdown:
            for tr in sb["threshold_results"]:
                if tr["trip_minutes"] == th and tr["exceeds"]:
                    exceed_count += sb["count"]
        exceed_share = exceed_count / population_total if population_total > 0 else 0.0
        thresholds_agg.append({
            "trip_minutes": th,
            "exceed_count": exceed_count,
            "exceed_share": round(exceed_share, 6),
        })

    # coverage
    network_covered_ratio = population_reachable / population_total if population_total > 0 else 0.0

    return {
        "kpis": {
            "population": population_total,
            "population_reachable": population_reachable,
            "trip_minutes": trip_stats,
            "round_trip_minutes": rt_stats,
            "weekly_minutes": weekly_stats,
            "thresholds": thresholds_agg,
        },
        "station_breakdown": station_breakdown,
        "unreachable": {
            "count": len(unreachable_stations),
            "stations": unreachable_stations,
        },
        "coverage": {
            "network_covered_ratio": round(network_covered_ratio, 6),
            "quality_label": "computed",
        },
        "policy_applied": {
            "office_days_per_week": round(applied_days_avg, 3),
            "override_population_share": round(override_share, 6),
        },
    }
