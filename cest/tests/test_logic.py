"""
Test: ロジック検証

パレート判定、注意点分析（robustness）、対立ポイント警告の
計算ロジックが正しいことを、手作りデータで検証する。
"""
import math

from cest.engine.combination import (
    _is_pareto_dominated,
    mark_pareto_frontier,
    _compute_rent_tolerance,
    _compute_capacity_headroom,
    _compute_conflict_alerts,
)


# ── ヘルパ: テスト用のコンボを簡単に作る ──────────────────────────────────────

def _make_combo(rent, avg, capacity, combo_id=None, per_office=None):
    """最小限のcomboデータを生成する。

    v0.3.3 でパレート判定軸は (total_rent, avg_trip, total_capacity) の3軸。
    """
    combo = {
        "total_rent_jpy_month": rent,
        "avg_trip_minutes": avg,
        "total_capacity": capacity,
        "is_pareto_optimal": False,
    }
    if combo_id:
        combo["combination_id"] = combo_id
    if per_office:
        combo["per_office"] = per_office
    return combo


# ── パレート判定（3軸）──────────────────────────────────────────────────────────

class TestParetoDominance:
    """3軸パレート支配の判定ロジック（rent × avg_trip × capacity）。"""

    def test_clearly_dominated(self):
        """3軸すべてで負けている案は支配される。"""
        A = _make_combo(rent=300, avg=40, capacity=100)
        B = _make_combo(rent=500, avg=50, capacity=80)  # 全部負け
        assert _is_pareto_dominated(B, [A, B]) is True

    def test_clearly_not_dominated(self):
        """3軸すべてで勝っている案は支配されない。"""
        A = _make_combo(rent=300, avg=40, capacity=100)
        B = _make_combo(rent=500, avg=50, capacity=80)
        assert _is_pareto_dominated(A, [A, B]) is False

    def test_one_axis_wins_survives(self):
        """1軸でも勝っていれば支配されない（パレートに残る）。"""
        A = _make_combo(rent=300, avg=40, capacity=100)
        # rent と avg で負けるが capacity で勝つ
        C = _make_combo(rent=400, avg=60, capacity=120)
        assert _is_pareto_dominated(C, [A, C]) is False

    def test_equal_on_all_axes(self):
        """3軸すべて同じ値なら支配されない（厳密に1つは優位でないと支配にならない）。"""
        A = _make_combo(rent=300, avg=40, capacity=100)
        B = _make_combo(rent=300, avg=40, capacity=100)
        assert _is_pareto_dominated(A, [A, B]) is False
        assert _is_pareto_dominated(B, [A, B]) is False

    def test_equal_two_axes_worse_one(self):
        """2軸が同じで1軸だけ負けていたら支配される。"""
        A = _make_combo(rent=300, avg=40, capacity=100)
        B = _make_combo(rent=300, avg=40, capacity=90)  # capacity だけ負け
        assert _is_pareto_dominated(B, [A, B]) is True

    def test_capacity_saves_expensive_office(self):
        """収容人数が多いだけで他2軸で負けていてもパレートに残る。
        これがv0.3.1（2軸）では落ちていた問題を解決する。"""
        cheap_small = _make_combo(rent=300, avg=40, capacity=50)
        expensive_big = _make_combo(rent=500, avg=60, capacity=200)
        # rent も avg も負けてるが capacity で大きく勝つ → 支配されない
        assert _is_pareto_dominated(expensive_big, [cheap_small, expensive_big]) is False

    def test_mark_pareto_frontier_ids(self):
        """mark_pareto_frontier が正しいIDリストを返す。"""
        combos = [
            _make_combo(rent=300, avg=40, capacity=100),  # パレート
            _make_combo(rent=500, avg=50, capacity=80),   # A に支配される
            _make_combo(rent=400, avg=60, capacity=120),  # capacity で勝ち → パレート
            _make_combo(rent=200, avg=70, capacity=150),  # rent と capacity で勝ち → パレート
        ]
        # num_offices が必要
        for c in combos:
            c["num_offices"] = 1

        pareto_ids = mark_pareto_frontier(combos)

        # combos[1] だけが支配される（rent, avg, capacity すべて combos[0] に負ける）
        assert combos[0]["is_pareto_optimal"] is True
        assert combos[1]["is_pareto_optimal"] is False
        assert combos[2]["is_pareto_optimal"] is True
        assert combos[3]["is_pareto_optimal"] is True
        assert len(pareto_ids) == 3

    def test_all_pareto_when_no_domination(self):
        """どの案も他を支配しない場合は全案パレート最適。"""
        combos = [
            _make_combo(rent=100, avg=90, capacity=50),   # 安い・遠い・小さい
            _make_combo(rent=500, avg=30, capacity=80),   # 高い・近い・中
            _make_combo(rent=300, avg=60, capacity=200),  # 中・中・大きい
        ]
        for c in combos:
            c["num_offices"] = 1
        pareto_ids = mark_pareto_frontier(combos)
        assert len(pareto_ids) == 3


# ── 賃料耐性（rent tolerance）──────────────────────────────────────────────────

class TestRentTolerance:
    """賃料がいくら上がるとパレートから脱落するかの計算。"""

    def test_no_dominator_means_unlimited(self):
        """avg と capacity で勝てる案がなければ tolerance_pct は None（上限なし）。"""
        combo = _make_combo(rent=300, avg=30, capacity=100, combo_id="test")
        combo["per_office"] = [
            {"office_id": "A", "name": "A社", "rent_jpy_month": 300},
        ]
        # 他の案は avg で combo に勝てない
        other = _make_combo(rent=200, avg=50, capacity=120)
        result = _compute_rent_tolerance(combo, [combo], [other])

        assert len(result) == 1
        assert result[0]["tolerance_pct"] is None
        assert result[0]["max_rent_before_drop"] is None

    def test_dominator_exists(self):
        """支配しうる案がある場合、正しい tolerance_pct を計算する。"""
        # combo: rent=300, avg=50, cap=100
        # dominator: rent=400, avg=40, cap=120 (avg ≤ 50 かつ cap ≥ 100 → 支配しうる)
        # combo の rent が 400 を超えたら脱落
        # headroom = 400 - 300 = 100
        combo = _make_combo(rent=300, avg=50, capacity=100, combo_id="test")
        combo["per_office"] = [
            {"office_id": "X", "name": "Xオフィス", "rent_jpy_month": 300},
        ]
        dominator = _make_combo(rent=400, avg=40, capacity=120)
        result = _compute_rent_tolerance(combo, [combo], [dominator])

        assert len(result) == 1
        assert result[0]["max_rent_before_drop"] == 400  # 300 + 100
        # tolerance_pct = (100 / 300) * 100 = 33.3%
        assert result[0]["tolerance_pct"] == 33.3

    def test_multiple_dominators_picks_strictest(self):
        """複数の支配候補がある場合、最も厳しい（rent が最も低い）ものを使う。"""
        combo = _make_combo(rent=300, avg=50, capacity=100, combo_id="test")
        combo["per_office"] = [
            {"office_id": "X", "name": "Xオフィス", "rent_jpy_month": 300},
        ]
        # dominator1: rent=400 → headroom 100
        # dominator2: rent=350 → headroom 50（こっちが厳しい）
        d1 = _make_combo(rent=400, avg=40, capacity=120)
        d2 = _make_combo(rent=350, avg=45, capacity=110)
        result = _compute_rent_tolerance(combo, [combo], [d1, d2])

        assert result[0]["max_rent_before_drop"] == 350
        # tolerance_pct = (50 / 300) * 100 = 16.7%
        assert result[0]["tolerance_pct"] == 16.7

    def test_multi_office_combo(self):
        """複数オフィスの案で、各オフィスに同じ headroom が配分される。"""
        combo = _make_combo(rent=500, avg=50, capacity=100, combo_id="test")
        combo["per_office"] = [
            {"office_id": "A", "name": "A社", "rent_jpy_month": 300},
            {"office_id": "B", "name": "B社", "rent_jpy_month": 200},
        ]
        # dominator: rent=600 → headroom = 600 - 500 = 100
        dominator = _make_combo(rent=600, avg=40, capacity=120)
        result = _compute_rent_tolerance(combo, [combo], [dominator])

        assert len(result) == 2
        # A: max = 300 + 100 = 400, pct = (100/300)*100 = 33.3
        assert result[0]["max_rent_before_drop"] == 400
        assert result[0]["tolerance_pct"] == 33.3
        # B: max = 200 + 100 = 300, pct = (100/200)*100 = 50.0
        assert result[1]["max_rent_before_drop"] == 300
        assert result[1]["tolerance_pct"] == 50.0


# ── 収容余裕（capacity headroom）──────────────────────────────────────────────

class TestCapacityHeadroom:
    """オフィスごとの残り人数とボトルネック検出。"""

    def test_basic_headroom(self):
        """基本的な収容余裕の計算。"""
        combo = {
            "per_office": [
                {"office_id": "A", "name": "A社", "capacity": 100, "assigned_population": 70},
                {"office_id": "B", "name": "B社", "capacity": 50, "assigned_population": 48},
            ]
        }
        result = _compute_capacity_headroom(combo)

        assert result["total_remaining"] == 32  # (100-70) + (50-48)
        assert result["bottleneck_office"] == "B社"
        assert result["bottleneck_remaining"] == 2
        assert len(result["per_office"]) == 2
        assert result["per_office"][0]["remaining"] == 30
        assert result["per_office"][1]["remaining"] == 2

    def test_over_capacity(self):
        """収容超過（remaining が負）の場合もボトルネックとして検出。"""
        combo = {
            "per_office": [
                {"office_id": "A", "name": "A社", "capacity": 50, "assigned_population": 60},
            ]
        }
        result = _compute_capacity_headroom(combo)
        assert result["bottleneck_remaining"] == -10
        assert result["total_remaining"] == -10

    def test_no_capacity_info(self):
        """capacity が None のオフィスは remaining も None。"""
        combo = {
            "per_office": [
                {"office_id": "A", "name": "A社", "capacity": None, "assigned_population": 30},
            ]
        }
        result = _compute_capacity_headroom(combo)
        assert result["per_office"][0]["remaining"] is None
        assert result["bottleneck_remaining"] is None

    def test_tight_estimated_capacity_warns(self):
        """推定定員にほぼ達していたら tight_estimate と warnings が立つ。"""
        combo = {
            "per_office": [
                {"office_id": "A", "name": "A社", "capacity": 100,
                 "assigned_population": 95, "capacity_estimated": True},
            ]
        }
        result = _compute_capacity_headroom(combo)
        assert result["per_office"][0]["tight_estimate"] is True
        assert len(result["warnings"]) == 1

    def test_given_capacity_not_warned(self):
        """定員が実数値（推定でない）なら、ギリギリでも警告しない。"""
        combo = {
            "per_office": [
                {"office_id": "A", "name": "A社", "capacity": 100,
                 "assigned_population": 95, "capacity_estimated": False},
            ]
        }
        result = _compute_capacity_headroom(combo)
        assert result["per_office"][0]["tight_estimate"] is False
        assert result["warnings"] == []

    def test_estimated_with_room_not_warned(self):
        """推定定員でも余裕があれば警告しない。"""
        combo = {
            "per_office": [
                {"office_id": "A", "name": "A社", "capacity": 100,
                 "assigned_population": 50, "capacity_estimated": True},
            ]
        }
        result = _compute_capacity_headroom(combo)
        assert result["per_office"][0]["tight_estimate"] is False
        assert result["warnings"] == []


# ── 対立ポイント警告（conflict alerts）──────────────────────────────────────────

class TestConflictAlerts:
    """部署間の平均通勤格差が閾値を超えたら警告を出す（v0.3.3 で p95 から avg に変更）。"""

    def test_gap_over_threshold(self):
        """avg の差が 15 分以上なら警告。"""
        breakdown = [
            {"group": "営業部", "avg_trip_minutes": 68},
            {"group": "経理部", "avg_trip_minutes": 45},
        ]
        alerts = _compute_conflict_alerts(breakdown)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "warning"
        assert "23分" in alerts[0]["message"]

    def test_gap_under_threshold(self):
        """avg の差が 15 分未満なら警告なし。"""
        breakdown = [
            {"group": "営業部", "avg_trip_minutes": 50},
            {"group": "経理部", "avg_trip_minutes": 45},
        ]
        alerts = _compute_conflict_alerts(breakdown)
        assert len(alerts) == 0

    def test_exactly_15_minutes(self):
        """ちょうど 15 分の差は警告（>= 15）。"""
        breakdown = [
            {"group": "営業部", "avg_trip_minutes": 60},
            {"group": "経理部", "avg_trip_minutes": 45},
        ]
        alerts = _compute_conflict_alerts(breakdown)
        assert len(alerts) == 1

    def test_three_departments_multiple_alerts(self):
        """3部署で複数ペアが閾値を超えたら複数の警告。"""
        breakdown = [
            {"group": "営業部", "avg_trip_minutes": 70},
            {"group": "経理部", "avg_trip_minutes": 40},
            {"group": "開発部", "avg_trip_minutes": 50},
        ]
        alerts = _compute_conflict_alerts(breakdown)
        # 営業-経理: 30分差 → 警告
        # 営業-開発: 20分差 → 警告
        # 経理-開発: 10分差 → なし
        assert len(alerts) == 2

    def test_single_department_no_alert(self):
        """1部署だけなら比較対象がないので警告なし。"""
        breakdown = [
            {"group": "営業部", "avg_trip_minutes": 70},
        ]
        alerts = _compute_conflict_alerts(breakdown)
        assert len(alerts) == 0
