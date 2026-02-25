"""
Test 3: 出社頻度を下げると週間負荷が単調に改善（Monotonicity）

他の条件が同じで出社日数だけを減らしたとき、
weekly_minutes の p95 が単調に改善されること。
「週3より週2の方が通勤負荷が高い」はありえない。

なぜこれが重要か：
「働き方で緩和できるか」が CEST の核心機能の一つ。
この単調性が崩れると、緩和策の提示が意味をなさない。
weekly_minutes = round_trip × days の定義から自明だが、
実装で override や加重平均が絡むとバグりやすい。

v0.3 では all_combinations の先頭コンボの per_office[0] の
weekly_minutes.p95 で確認する。
"""
from copy import deepcopy

from tests.conftest import load_fixture
from cest.engine.pipeline import evaluate


def test_reducing_office_days_monotonically_improves_weekly_load():
    base_input = load_fixture("demo_3candidates.json")
    weekly_p95_by_days: dict = {}

    for days in [5, 4, 3, 2, 1]:
        inp = deepcopy(base_input["inputs"])
        inp["policy_as_is"]["office_days_per_week"] = days
        # override を全て除去（純粋に days 変化だけ見る）
        for dist in inp["home_station_distribution"]:
            dist.pop("office_days_per_week_override", None)

        result = evaluate(inp)

        # all_combinations の先頭コンボの最初のオフィスの weekly p95
        if result["all_combinations"]:
            combo = result["all_combinations"][0]
            if combo["per_office"]:
                weekly_p95_by_days[days] = combo["per_office"][0]["kpis"]["weekly_minutes"]["p95"]

    assert len(weekly_p95_by_days) >= 2, "比較可能なデータが取得できなかった"

    for d in [4, 3, 2, 1]:
        if d in weekly_p95_by_days and d + 1 in weekly_p95_by_days:
            assert weekly_p95_by_days[d] <= weekly_p95_by_days[d + 1], (
                f"週{d}日の p95_weekly({weekly_p95_by_days[d]:.1f}) が"
                f"週{d+1}日({weekly_p95_by_days[d+1]:.1f}) より大きい（単調性違反）"
            )
