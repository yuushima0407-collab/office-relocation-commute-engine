"""
Test 2: unreachable で落ちない（Robustness）

路線ネットワークに存在しない駅が入力に含まれても
クラッシュせず、unreachable として正しく報告されること。

なぜこれが重要か：
実際のデータには必ず想定外の駅が入る。
「落ちること」が最悪の失敗。
unreachable を 0 分として扱うことも同様に最悪（サイレントバグ）。

v0.3 では Notice（STATION_ID_NOT_FOUND）で報告される。
"""
from copy import deepcopy

from tests.conftest import load_fixture
from cest.engine.pipeline import evaluate


def test_unreachable_station_does_not_crash():
    input_data = load_fixture("demo_3candidates.json")
    inputs = deepcopy(input_data["inputs"])
    inputs["home_station_distribution"].append(
        {"station_id": "nonexistent_island_sta", "count": 5}
    )

    result = evaluate(inputs)

    # クラッシュしない
    assert result is not None

    # STATION_ID_NOT_FOUND Notice が出る
    notice_codes = [n["code"] for n in result["notices"]]
    assert "STATION_ID_NOT_FOUND" in notice_codes, (
        f"STATION_ID_NOT_FOUND notice が生成されなかった。notices={result['notices']}"
    )

    # 評価結果（all_combinations）が壊れていない
    assert "all_combinations" in result
    assert isinstance(result["all_combinations"], list)
    assert "pareto_frontier_ids" in result
    assert isinstance(result["pareto_frontier_ids"], list)
