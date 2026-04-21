from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import networkx as nx

from cest.engine.graph_loader import load_graph, load_station_master, load_station_hazard
from cest.engine.notices import NoticeCollector
from cest.engine.combination import run_v3_pipeline


def evaluate(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    v0.3 評価パイプライン。
    """
    collector = NoticeCollector()

    home_stations = inputs["home_station_distribution"]
    offices = inputs["office_candidates"]
    policy = inputs["policy_as_is"]
    settings = inputs["settings"]

    policy_days = policy["office_days_per_week"]
    routing_cfg = settings.get("routing", {})
    graph_id = routing_cfg.get("graph_id", "tokyo_core_v1")
    transfer_penalty = routing_cfg.get("transfer_penalty_minutes", 0)

    if transfer_penalty != 0:
        collector.transfer_penalty_unsupported(transfer_penalty)

    # グラフ読み込み
    try:
        G = load_graph(graph_id) if graph_id else None
    except FileNotFoundError:
        G = None

    if G is None:
        collector.routing_graph_missing()
        return _build_empty_report(collector)

    # 駅の存在チェック
    graph_nodes = set(G.nodes())
    station_master = load_station_master()
    for hs in home_stations:
        if hs["station_id"] not in graph_nodes:
            collector.station_id_not_found(hs["station_id"])
        if hs["station_id"] not in station_master:
            collector.station_coord_missing(hs["station_id"])

    # 家賃未入力チェック
    for office in offices:
        if office.get("rent_jpy_month") is None:
            collector.rent_missing(office.get("name", office["office_id"]))

    # ハザード警告（フィルタではなく警告のみ）
    station_hazard = load_station_hazard()
    for office in offices:
        sid = office.get("nearest_station_id", "")
        h = station_hazard.get(sid, {})
        flood = h.get("flood_depth_m")
        seismic = h.get("seismic_rank")
        warnings = []
        if flood is not None and flood > 0:
            warnings.append(f"浸水想定区域（{flood}m）")
        if seismic is not None and seismic >= 4:
            warnings.append(f"地震ランク{seismic}")
        if warnings:
            detail = "、".join(warnings)
            collector.hazard_warning(
                office.get("name", sid),
                detail,
            )

    # v0.3 パイプライン実行
    result = run_v3_pipeline(
        G=G,
        home_stations=home_stations,
        offices=offices,
        policy_days=policy_days,
        settings=settings,
        collector=collector,
    )

    return {
        "version": "v0.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "all_combinations": result["all_combinations"],
        "pareto_frontier_ids": result["pareto_frontier_ids"],
        "constraints_impact": result["constraints_impact"],
        "robustness": result["robustness"],
        "baseline_diagnosis": result.get("baseline_diagnosis"),
        "notices": collector.notices,
    }


def _build_empty_report(collector: NoticeCollector) -> Dict[str, Any]:
    return {
        "version": "v0.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "all_combinations": [],
        "pareto_frontier_ids": [],
        "constraints_impact": {
            "total_combinations": 0,
            "after_capacity_filter": 0,
            "after_budget_filter": 0,
            "after_commute_filter": 0,
            "pareto_optimal": 0,
            "vs_previous_round": None,
        },
        "robustness": [],
        "baseline_diagnosis": None,
        "notices": collector.notices,
    }
