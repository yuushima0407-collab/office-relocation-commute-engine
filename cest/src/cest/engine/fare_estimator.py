"""
JR東日本 IC運賃テーブルを用いた通勤費推定。

精度の限界:
- 通勤時間から距離を平均速度40km/h で推定（路線・快速/各停による誤差あり）
- JR東日本以外の路線（私鉄・地下鉄）も同テーブルで近似
- 定期代は片道IC運賃 × 2 × 出社日数 × 4.33週 × 定期割引係数(0.85) で推定
すべて推定値。実際の定期代とは異なる場合があります。
"""
from __future__ import annotations

from typing import Optional

# JR東日本 電車特定区間 IC運賃テーブル（片道）
# 出典: JR東日本 旅客営業規則 別表 第1号の2
_JRE_IC_FARE_TABLE = [
    (3,   150),
    (6,   160),
    (10,  170),
    (15,  200),
    (20,  220),
    (25,  250),
    (30,  290),
    (35,  320),
    (40,  360),
    (45,  400),
    (50,  440),
    (60,  490),
    (70,  560),
    (80,  640),
    (90,  720),
    (100, 800),
]

# 東京近郊の鉄道平均速度（km/min）: 40km/h 換算
_KM_PER_MIN = 40.0 / 60.0

# 定期代の割引係数（月額定期 ÷ 往復 × 営業日数の近似）
_TEIKI_DISCOUNT = 0.85
_WEEKS_PER_MONTH = 4.33


def _estimate_distance_km(trip_minutes: float) -> float:
    return trip_minutes * _KM_PER_MIN


def _one_way_fare(distance_km: float) -> int:
    for max_km, fare in _JRE_IC_FARE_TABLE:
        if distance_km <= max_km:
            return fare
    # 100km 超は概算（1kmあたり約7円加算）
    return int(800 + (distance_km - 100) * 7)


def estimate_one_way_fare(trip_minutes: float) -> int:
    """片道運賃の推定（円）。"""
    return _one_way_fare(_estimate_distance_km(trip_minutes))


def estimate_monthly_commute_cost(
    trip_minutes: float,
    days_per_week: float,
    cap_jpy_month: Optional[int] = None,
) -> int:
    """
    月額通勤費の推定（円）。

    cap_jpy_month が指定された場合は上限を適用する（会社が上限付きで負担する場合）。
    """
    one_way = estimate_one_way_fare(trip_minutes)
    monthly = int(one_way * 2 * days_per_week * _WEEKS_PER_MONTH * _TEIKI_DISCOUNT)
    if cap_jpy_month is not None:
        monthly = min(monthly, cap_jpy_month)
    return monthly
