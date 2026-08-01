"""
Test: max_exceed_risk_count（通勤リスク帯を許容する人数の上限）フィルタ

p95や平均だけでなく、「commute_risk_threshold_minutesを超える通勤が何人いるか」を
直接の上限として組み合わせを絞り込めることを検証する。
"""
from copy import deepcopy

from tests.conftest import load_fixture
from cest.engine.pipeline import evaluate


def _run(max_exceed_risk_count):
    base_input = load_fixture("demo_3candidates.json")
    inp = deepcopy(base_input["inputs"])
    inp["settings"]["num_offices"] = [1, 2, 3]
    if max_exceed_risk_count is not None:
        inp["settings"]["max_exceed_risk_count"] = max_exceed_risk_count
    return evaluate(inp)


def test_no_filter_by_default():
    result = _run(None)
    assert len(result["all_combinations"]) > 0


def test_threshold_below_actual_excludes_all_combos():
    # このフィクスチャは全comboでexceed_risk_count=20固定（デフォルト60分基準）なので、
    # 19までしか許容しないと全滅するはず
    result = _run(19)
    assert result["all_combinations"] == []


def test_threshold_at_actual_keeps_combos():
    result = _run(20)
    assert len(result["all_combinations"]) > 0
    for combo in result["all_combinations"]:
        assert combo["exceed_risk_count"] <= 20


def test_custom_risk_threshold_changes_count():
    """commute_risk_threshold_minutes を変えると exceed_risk_count も変わる。"""
    base_input = load_fixture("demo_3candidates.json")
    inp = deepcopy(base_input["inputs"])
    inp["settings"]["num_offices"] = [1]

    inp["settings"]["commute_risk_threshold_minutes"] = 1
    result_low = evaluate(inp)

    inp["settings"]["commute_risk_threshold_minutes"] = 180
    result_high = evaluate(inp)

    combo_low = result_low["all_combinations"][0]
    combo_high = result_high["all_combinations"][0]
    assert combo_low["commute_risk_threshold_minutes"] == 1
    assert combo_high["commute_risk_threshold_minutes"] == 180
    assert combo_low["exceed_risk_count"] >= combo_high["exceed_risk_count"]
