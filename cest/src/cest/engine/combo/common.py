"""combination パイプライン全体で使う小さな共通ヘルパー。

他の combo_*.py モジュールはここに依存してよいが、ここは他の combo_*.py に依存しない
（循環importを避けるため、本当に共通なものだけをここに置く）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from cest.models.request import HomeStation, OfficeCandidate
from cest.engine.support.fare_estimator import estimate_monthly_commute_cost


def _get_group(hs: HomeStation) -> str:
    return hs.group or hs.station_id


def _get_capacity(office: OfficeCandidate, sqm_per_person: float) -> Optional[int]:
    """収容人数を返す。capacity_people 優先、なければ floor_area_sqm から推定。"""
    if office.capacity_people is not None:
        return office.capacity_people
    area = office.floor_area_sqm
    if area is not None and sqm_per_person > 0:
        return int(area / sqm_per_person)
    return None


def _capacity_is_estimated(office: OfficeCandidate) -> bool:
    return office.capacity_people is None and office.floor_area_sqm is not None


def _index_offices(offices: List[OfficeCandidate]) -> Dict[str, OfficeCandidate]:
    """オフィスのリストを office_id をキーにした辞書に変換する。"""
    return {o.office_id: o for o in offices}


def _weighted_p95(trips: List[Tuple[float, int]]) -> float:
    """(通勤分, 人数) のリストから、累積人数が全体の95%に達する時点の通勤分を返す。

    trips は空でないこと（呼び出し側で保証する）。
    """
    total = sum(c for _, c in trips)
    threshold = 0.95 * total
    cumulative = 0
    for t, c in sorted(trips, key=lambda x: x[0]):
        cumulative += c
        if cumulative >= threshold:
            return t
    return trips[-1][0]


def _monthly_commute_cost(
    commute_allowance_jpy_month: Optional[int],
    trip_minutes: float,
    policy_days: float,
    cap: Optional[int],
) -> int:
    """1人あたりの月額通勤費。実費指定（commute_allowance_jpy_month）があればそれを優先し、
    なければ運賃テーブルから推定する。どちらも cap が指定されていれば上限を適用する。

    呼び出し元は HomeStation（型付き）と station_breakdown（dict、comboの一部）の
    両方があり形が揃わないので、レコード全体ではなく必要な1フィールドだけ受け取る。
    """
    if commute_allowance_jpy_month is not None:
        return min(commute_allowance_jpy_month, cap) if cap is not None else commute_allowance_jpy_month
    return estimate_monthly_commute_cost(trip_minutes, policy_days, cap)
