"""
v0.3 パイプライン基本動作テスト

v0.1 形式の入力（group / floor_area_sqm なし）でも
v0.3 パイプラインが正常に動作し、v0.3 レスポンスを返すこと。

- group なし → station_id をグループ代わりに使う（_get_group のデフォルト動作）
- floor_area_sqm / capacity_people なし → 収容チェックをスキップ
"""
from __future__ import annotations

from copy import deepcopy

from tests.conftest import load_fixture
from cest.engine.pipeline import evaluate


def test_v1_style_input_works_with_v03_pipeline():
    """group / floor_area_sqm なしの旧来入力でも v0.3 レスポンスが返ること。"""
    input_data = load_fixture("demo_3candidates.json")
    inputs = deepcopy(input_data["inputs"])

    result = evaluate(inputs)

    assert result["version"] == "v0.3"
    assert "all_combinations" in result
    assert "pareto_frontier_ids" in result
    assert "constraints_impact" in result
    assert "robustness" in result

    # パレートフロンティアが空でないこと
    assert len(result["pareto_frontier_ids"]) >= 1
    assert len(result["all_combinations"]) >= 1
