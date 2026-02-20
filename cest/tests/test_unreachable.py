"""
Test 2: unreachableで落ちない（Robustness）

路線ネットワークに存在しない駅が入力に含まれても
クラッシュせず、unreachableとして正しく報告されること。

なぜこれが重要か：
実際のデータには必ず想定外の駅が入る。
「落ちること」が最悪の失敗。
unreachableを0分として扱うことも同様に最悪（サイレントバグ）。
"""
from copy import deepcopy

from tests.conftest import load_fixture
from cest.engine.pipeline import evaluate


def test_unreachable_station_does_not_crash():
    input_data = load_fixture("demo_3candidates.json")
    inputs = deepcopy(input_data["inputs"])
    inputs["home_station_distribution"].append(
        {"station_id": "nonexistent_island_sta", "count": 5, "segment": None,
         "office_days_per_week_override": None}
    )

    result = evaluate(inputs)

    # クラッシュしない
    assert result is not None

    # unreachableに正しく報告される
    for scenario_result in result["results"]:
        unreachable_ids = [s["station_id"] for s in scenario_result["unreachable"]["stations"]]
        assert "nonexistent_island_sta" in unreachable_ids

        # 0分として混入していない
        for sb in scenario_result["station_breakdown"]:
            if sb["station_id"] == "nonexistent_island_sta":
                assert sb["reachable"] is False
                assert sb["trip_minutes"] is None

    # Noticeが出る
    notice_codes = [n["code"] for n in result["notices"]]
    assert "UNREACHABLE_EXISTS" in notice_codes
