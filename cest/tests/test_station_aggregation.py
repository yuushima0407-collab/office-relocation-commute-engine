"""
同一駅に複数部署がいる集計済みデータで、人数が二重計上されないことの検証。

背景: evaluate_combo は station_breakdown（行ごと）を見て人数を集計するが、
以前は station_id での再検索（next）を使っていたため、同一駅が複数行（複数部署）
あって同じオフィスに配置されると、毎回「最初の行のcount」を拾ってしまい
人数を過大計上していた。
"""
from cest.models.request import HomeStation, OfficeCandidate
from cest.engine.combo.evaluation import evaluate_combo
from tests.conftest import tiny_graph


def test_same_station_two_departments_not_double_counted():
    """渋谷の営業5人・開発3人が同じオフィスAへ → 合計8人として集計されること。"""
    G = tiny_graph()
    office = OfficeCandidate(
        office_id="A",
        name="A",
        nearest_station_id="tokyo",
        last_mile_minutes=5,
        rent_jpy_month=100000,
        capacity_people=100,
    )
    # 同一駅(渋谷)に異なる部署・異なる人数の2行
    home_stations = [
        HomeStation(station_id="shibuya", count=5, group="sales"),
        HomeStation(station_id="shibuya", count=3, group="dev"),
    ]
    assignment = {"sales": "A", "dev": "A"}

    result = evaluate_combo(
        G, home_stations, [office], assignment,
        policy_days=3, thresholds_trip=[60, 90], sqm_per_person=3.3,
    )

    # 渋谷→東京(10分) + 徒歩5分 = 15分 が 5+3=8人
    dist = result["distribution"]
    total_in_dist = (
        dist["under_30"] + dist["30_to_60"] + dist["60_to_90"] + dist["over_90"]
    )
    assert total_in_dist == 8, f"分布の合計人数が8でない（二重計上の疑い）: {total_in_dist}"
    assert result["total_population"] == 8
    assert result["avg_trip_minutes"] == 15.0
