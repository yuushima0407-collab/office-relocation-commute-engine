"""
Test 1: 決定論（Determinism）

同じ入力を与えたとき、何回実行しても必ず同じ出力になること。

なぜこれが重要か：
「昨日と今日で結果が違う」は合意形成ツールとして致命的。
経営会議で「前回と数字が違う」と言われたときに
「同じ入力からは常に同じ結果」を保証できることが信頼の基盤。
"""
from copy import deepcopy

from tests.conftest import load_fixture
from cest.engine.pipeline import evaluate


def test_same_input_same_output():
    input_data = load_fixture("demo_3candidates.json")

    result_1 = evaluate(deepcopy(input_data["inputs"]))
    result_2 = evaluate(deepcopy(input_data["inputs"]))

    # generated_at は実行時刻なので比較から除外
    result_1.pop("generated_at", None)
    result_2.pop("generated_at", None)

    assert result_1["all_combinations"] == result_2["all_combinations"]
    assert result_1["pareto_frontier_ids"] == result_2["pareto_frontier_ids"]
    assert result_1["robustness"] == result_2["robustness"]
    assert result_1["constraints_impact"] == result_2["constraints_impact"]


def test_output_conforms_to_v032_schema():
    """出力が v0.3.2 スキーマに適合すること。"""
    input_data = load_fixture("demo_3candidates.json")
    result = evaluate(deepcopy(input_data["inputs"]))

    assert result["version"] == "v0.3"

    # トップレベルキー
    for key in ("all_combinations", "pareto_frontier_ids", "constraints_impact",
                "robustness", "baseline_diagnosis", "notices"):
        assert key in result, f"レスポンスに '{key}' がない"

    # baseline 未指定時は None
    assert result["baseline_diagnosis"] is None

    # constraints_impact の構造
    ci = result["constraints_impact"]
    for key in (
        "total_combinations",
        "after_capacity_filter", "after_budget_filter",
        "after_commute_filter", "pareto_optimal",
    ):
        assert key in ci, f"constraints_impact に '{key}' がない"

    # robustness の構造
    robustness = result["robustness"]
    assert isinstance(robustness, list)
    # robustness はパレート最適案の数と一致
    pareto_count = len(result["pareto_frontier_ids"])
    assert len(robustness) == pareto_count
    for entry in robustness:
        assert "combination_id" in entry
        assert "rent_tolerance" in entry
        assert "capacity_headroom" in entry
        # rent_tolerance の構造
        for rt in entry["rent_tolerance"]:
            for key in ("office_id", "office_name", "current_rent"):
                assert key in rt, f"rent_tolerance に '{key}' がない"
        # capacity_headroom の構造
        ch = entry["capacity_headroom"]
        for key in ("total_remaining", "bottleneck_office", "bottleneck_remaining", "per_office"):
            assert key in ch, f"capacity_headroom に '{key}' がない"

    # all_combinations の各コンボ構造
    for combo in result["all_combinations"]:
        for key in ("combination_id", "selected_offices", "num_offices",
                    "total_rent_jpy_month", "p95_trip_minutes", "avg_trip_minutes",
                    "rent_per_capacity",
                    "distribution", "is_pareto_optimal",
                    "assignment", "per_office",
                    "department_breakdown", "conflict_alerts"):
            assert key in combo, f"combo に '{key}' がない"

        # department_breakdown の構造
        for dept in combo["department_breakdown"]:
            for key in ("group", "count", "avg_trip_minutes", "p95_trip_minutes",
                        "assigned_office", "commute_cost_jpy_month"):
                assert key in dept, f"department_breakdown に '{key}' がない"

        # conflict_alerts の構造
        assert isinstance(combo["conflict_alerts"], list)
        for alert in combo["conflict_alerts"]:
            for key in ("type", "message", "severity"):
                assert key in alert, f"conflict_alert に '{key}' がない"

    # pareto_frontier_ids は all_combinations の combination_id のサブセット
    all_ids = {c["combination_id"] for c in result["all_combinations"]}
    for pid in result["pareto_frontier_ids"]:
        assert pid in all_ids, f"pareto_frontier_ids の '{pid}' が all_combinations に存在しない"


def test_vs_baseline():
    """baseline 指定時に vs_baseline が各案に付与され、baseline_diagnosis が返ること。"""
    input_data = load_fixture("demo_3candidates.json")
    inputs = deepcopy(input_data["inputs"])

    # baseline として最初の候補オフィスを指定
    first_office = inputs["office_candidates"][0]
    inputs["settings"]["baseline"] = {
        "office_id": "baseline_current",
        "name": "現オフィス",
        "nearest_station_id": first_office["nearest_station_id"],
        "last_mile_minutes": first_office["last_mile_minutes"],
        "rent_jpy_month": first_office.get("rent_jpy_month"),
        "capacity_people": first_office.get("capacity_people"),
    }

    result = evaluate(inputs)

    # baseline_diagnosis の存在と構造
    bd = result["baseline_diagnosis"]
    assert bd is not None, "baseline 指定時に baseline_diagnosis がない"
    for key in ("office_name", "employee_count", "capacity_people", "occupancy_pct",
                "avg_trip_minutes", "p95_trip_minutes",
                "over_60min_count", "over_90min_count", "alerts"):
        assert key in bd, f"baseline_diagnosis に '{key}' がない"

    # vs_baseline の存在と構造
    for combo in result["all_combinations"]:
        assert "vs_baseline" in combo, "baseline 指定時に vs_baseline がない"
        vb = combo["vs_baseline"]
        for key in ("avg_trip_change", "p95_trip_change", "rent_change",
                    "total_cost_change", "worse_count", "better_count", "unchanged_count"):
            assert key in vb, f"vs_baseline に '{key}' がない"
