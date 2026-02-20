from __future__ import annotations

from typing import Optional

import networkx as nx


def calc_rail_minutes(
    G: nx.Graph,
    home_station_id: str,
    office_station_id: str,
) -> Optional[float]:
    try:
        return nx.dijkstra_path_length(G, home_station_id, office_station_id, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


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
