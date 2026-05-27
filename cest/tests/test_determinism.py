"""
Test 1: 決定論（Determinism）+ JSON Schema 適合

同じ入力を与えたとき、何回実行しても必ず同じ出力になること。
出力が v0.3.3 JSON Schema（cest/schemas/evaluation_report_v0.3.3.json）に適合すること。

なぜこれが重要か：
「昨日と今日で結果が違う」は合意形成ツールとして致命的。
経営会議で「前回と数字が違う」と言われたときに
「同じ入力からは常に同じ結果」を保証できることが信頼の基盤。

Schema 検証はバックエンドの出力構造をフロントとの契約として固定する。
新フィールド追加や削除のたびに Schema を更新する運用にすることで、
コード変更とドキュメントの乖離を防ぐ。
"""
from copy import deepcopy

from tests.conftest import load_fixture
from cest.engine.pipeline import evaluate
from cest.utils.schema_validate import validate_response


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


def test_output_conforms_to_v033_schema():
    """出力が v0.3.3 JSON Schema に適合すること。"""
    input_data = load_fixture("demo_3candidates.json")
    result = evaluate(deepcopy(input_data["inputs"]))

    errors = validate_response(result)
    assert errors == [], (
        f"v0.3.3 Schema 違反 {len(errors)} 件: "
        + "; ".join(f"{e['path']}: {e['message']}" for e in errors[:5])
    )


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

    # Schema 適合
    errors = validate_response(result)
    assert errors == [], (
        f"baseline 指定時の Schema 違反 {len(errors)} 件: "
        + "; ".join(f"{e['path']}: {e['message']}" for e in errors[:5])
    )

    # baseline_diagnosis が返ること（構造は Schema で担保済み）
    assert result["baseline_diagnosis"] is not None, (
        "baseline 指定時に baseline_diagnosis が None"
    )

    # vs_baseline が各案に付与されること
    for combo in result["all_combinations"]:
        assert "vs_baseline" in combo, "baseline 指定時に vs_baseline がない"
