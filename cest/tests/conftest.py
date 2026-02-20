from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> Dict[str, Any]:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def demo_input() -> Dict[str, Any]:
    return load_fixture("demo_3candidates.json")
