from __future__ import annotations

from cest.engine.csv_parser import parse_employee_csv


def test_csv_parser_basic():
    csv_text = "station_id,count,group\nomiya,5,開発\nyokohama,8,営業\n"
    rows = parse_employee_csv(csv_text)
    assert rows == [
        {"station_id": "omiya", "count": 5, "group": "開発"},
        {"station_id": "yokohama", "count": 8, "group": "営業"},
    ]


def test_csv_parser_station_name_fallback():
    # station_masterに存在しない名前はそのままIDとして扱われる
    csv_text = "station_id,count\n架空駅,3\n"
    rows = parse_employee_csv(csv_text)
    assert rows == [
        {"station_id": "架空駅", "count": 3, "group": None},
    ]

