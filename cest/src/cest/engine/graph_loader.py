from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import networkx as nx

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_GRAPH_CACHE: Dict[str, nx.Graph] = {}
_STATION_MASTER_CACHE: Dict[str, Dict[str, Any]] | None = None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_graph(graph_id: str = "tokyo_core_v1") -> nx.Graph:
    if graph_id in _GRAPH_CACHE:
        return _GRAPH_CACHE[graph_id]

    path = _DATA_DIR / f"{graph_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Graph file not found: {path}")

    data = _load_json(path)
    G = nx.Graph()
    for node in data.get("nodes", []):
        G.add_node(node["station_id"], name=node.get("name", ""))
    for edge in data.get("edges", []):
        u, v, w = edge["from"], edge["to"], edge["minutes"]
        if G.has_edge(u, v):
            existing = G[u][v]["weight"]
            if w < existing:
                G[u][v]["weight"] = w
        else:
            G.add_edge(u, v, weight=w)

    _GRAPH_CACHE[graph_id] = G
    return G


def load_station_master() -> Dict[str, Dict[str, Any]]:
    global _STATION_MASTER_CACHE
    if _STATION_MASTER_CACHE is not None:
        return _STATION_MASTER_CACHE

    path = _DATA_DIR / "station_master.json"
    data = _load_json(path)
    master = {}
    for s in data.get("stations", []):
        master[s["station_id"]] = {
            "name": s.get("name", ""),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
        }
    _STATION_MASTER_CACHE = master
    return master
