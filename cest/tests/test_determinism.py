"""
Test 1: 決定論（Determinism）

同じ入力を与えたとき、何回実行しても必ず同じ出力になること。
ランダム性・非決定的な処理が混入していないことを保証する。

なぜこれが重要か：
「昨日と今日で結果が違う」は合意形成ツールとして致命的。
経営会議で「前回と数字が違う」と言われたときに
「同じ入力からは常に同じ結果」を保証できることが信頼の基盤。
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

    assert result_1["results"] == result_2["results"]
    assert result_1["ranking"] == result_2["ranking"]
    assert result_1["sensitivity"] == result_2["sensitivity"]


def test_output_conforms_to_schema():
    """出力JSONがv0.1.2 Schemaに適合すること。"""
    input_data = load_fixture("demo_3candidates.json")
    result = evaluate(deepcopy(input_data["inputs"]))

    errors = validate_response(result)
    assert errors == [], f"Schema validation errors: {errors}"
