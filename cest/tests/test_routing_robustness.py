"""
1人の社員の駅が不正（入力ミス／cestグラフ範囲外）でも、部署全体が
配置不能にならないことの検証。

方針: 到達不能な人はその人だけ飛ばして、到達できる人で評価を続ける。
不備自体は別途 STATION_ID_NOT_FOUND 警告で通知される（pipeline側）。
"""
from cest.engine.combo.assignment import build_group_assignment
from tests.conftest import tiny_graph


def test_one_invalid_station_does_not_block_group():
    """営業部に1人だけ不正な駅がいても、残りの社員で配置先が決まること。"""
    G = tiny_graph()
    offices = [
        {"office_id": "A", "name": "A", "nearest_station_id": "tokyo", "last_mile_minutes": 5},
    ]
    home_stations = [
        {"station_id": "shibuya", "count": 5, "group": "sales"},
        {"station_id": "typo_xyz", "count": 1, "group": "sales"},  # 入力ミス想定（グラフに無い）
    ]

    assignment = build_group_assignment(G, home_stations, offices, [], [])

    # 1件の不備で配置不能にならず、到達できる5人を基準にAへ配置される
    assert assignment.get("sales") == "A", f"営業部が配置されていない: {assignment}"
