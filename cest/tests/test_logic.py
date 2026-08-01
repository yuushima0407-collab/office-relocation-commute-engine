"""
Test: ロジック検証

パレート判定、収容余裕分析の
計算ロジックが正しいことを、手作りデータで検証する。
"""
import math

from cest.engine.combo.pareto import _is_pareto_dominated, mark_pareto_frontier
from cest.engine.combo.capacity import _compute_capacity_headroom


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
