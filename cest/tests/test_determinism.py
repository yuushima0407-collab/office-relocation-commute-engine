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
    assert result_1["sensitivity"] == result_2["sensitivity"]
    assert result_1["constraints_impact"] == result_2["constraints_impact"]


def test_output_conforms_to_v03_schema():
    """出力が v0.3 スキーマに適合すること。"""
    input_data = load_fixture("demo_3candidates.json")
    result = evaluate(deepcopy(input_data["inputs"]))

    assert result["version"] == "v0.3"

    # トップレベルキー
    for key in ("all_combinations", "pareto_frontier_ids", "constraints_impact", "sensitivity", "notices"):
        assert key in result, f"レスポンスに '{key}' がない"

    # constraints_impact の構造
    ci = result["constraints_impact"]
    for key in (
        "total_combinations",
        "after_capacity_filter", "after_budget_filter",
        "after_commute_filter", "pareto_optimal",
    ):
        assert key in ci, f"constraints_impact に '{key}' がない"

    # sensitivity の構造
    sens = result["sensitivity"]
    for key in ("ranking_stable", "summary", "details"):
        assert key in sens, f"sensitivity に '{key}' がない"
    assert isinstance(sens["ranking_stable"], bool)

    # all_combinations の各コンボ構造
    for combo in result["all_combinations"]:
        for key in ("combination_id", "selected_offices", "num_offices",
                    "total_rent_jpy_month", "p95_trip_minutes", "avg_trip_minutes",
                    "distribution", "is_pareto_optimal",
                    "assignment", "per_office"):
            assert key in combo, f"combo に '{key}' がない"

    # pareto_frontier_ids は all_combinations の combination_id のサブセット
    all_ids = {c["combination_id"] for c in result["all_combinations"]}
    for pid in result["pareto_frontier_ids"]:
        assert pid in all_ids, f"pareto_frontier_ids の '{pid}' が all_combinations に存在しない"
