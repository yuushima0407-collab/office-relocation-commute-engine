from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import networkx as nx
import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> Dict[str, Any]:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def demo_input() -> Dict[str, Any]:
    return load_fixture("demo_3candidates.json")


def tiny_graph() -> nx.Graph:
    """渋谷 --10分-- 東京 だけの最小グラフ。ロジックテスト用で、本番の路線データには依存しない。"""
    G = nx.Graph()
    G.add_node("shibuya")
    G.add_node("tokyo")
    G.add_edge("shibuya", "tokyo", weight=10)
    return G
