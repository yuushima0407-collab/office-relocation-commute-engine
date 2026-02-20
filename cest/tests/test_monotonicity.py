"""
Test 3: 出社頻度を下げると週間負荷が単調に改善（Monotonicity）

他の条件が同じで出社日数だけを減らしたとき、
weekly_minutesのp95が単調に改善されること。
「週3より週2の方が通勤負荷が高い」はありえない。

なぜこれが重要か：
「働き方で緩和できるか」がCESTの核心機能の一つ。
この単調性が崩れると、緩和策の提示が意味をなさない。
weekly_minutes = round_trip × days の定義から自明だが、
実装でoverrideや加重平均が絡むとバグりやすい。
"""
from copy import deepcopy

from tests.conftest import load_fixture
from cest.engine.pipeline import evaluate


def test_reducing_office_days_monotonically_improves_weekly_load():
    base_input = load_fixture("demo_3candidates.json")
    p95_weekly_by_days = {}

    for days in [5, 4, 3, 2, 1]:
        inp = deepcopy(base_input["inputs"])
        inp["policy_as_is"]["office_days_per_week"] = days
        # overrideを全て除去（純粋にdays変化だけ見る）
        for dist in inp["home_station_distribution"]:
            dist["office_days_per_week_override"] = None

        result = evaluate(inp)
        reachable_result = result["results"][0]  # 最初のオフィス候補で比較
        p95_weekly_by_days[days] = reachable_result["kpis"]["weekly_minutes"]["p95"]

    # 日数が減るにつれてp95_weeklyも単調減少（または同値）
    for d in [4, 3, 2, 1]:
        assert p95_weekly_by_days[d] <= p95_weekly_by_days[d + 1], \
            f"週{d}日のp95weekly({p95_weekly_by_days[d]:.1f})が" \
            f"週{d+1}日({p95_weekly_by_days[d+1]:.1f})より大きい（単調性違反）"
