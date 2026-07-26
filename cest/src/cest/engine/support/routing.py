from __future__ import annotations

from typing import Dict, Optional, Tuple

import networkx as nx

# (id(G), home_station_id, office_station_id) -> rail_minutes。
# G はグラフIDごとに1度だけ読み込まれてプロセス内で使い回されるため、
# 同じ駅ペアの最短経路計算を組み合わせの数だけ繰り返さないようここで覚えておく。
_RAIL_MINUTES_CACHE: Dict[Tuple[int, str, str], Optional[float]] = {}


def calc_rail_minutes(
    G: nx.Graph,
    home_station_id: str,
    office_station_id: str,
) -> Optional[float]:
    key = (id(G), home_station_id, office_station_id)
    if key in _RAIL_MINUTES_CACHE:
        return _RAIL_MINUTES_CACHE[key]
    try:
        result = nx.dijkstra_path_length(G, home_station_id, office_station_id, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        result = None
    _RAIL_MINUTES_CACHE[key] = result
    return result


def calc_trip_minutes(
    G: nx.Graph,
    home_station_id: str,
    office_station_id: str,
    last_mile_minutes: float,
) -> Optional[float]:
    rail = calc_rail_minutes(G, home_station_id, office_station_id)
    if rail is None:
        return None
    return rail + last_mile_minutes
