from __future__ import annotations

from typing import Any, Dict, List, Optional


def make_notice(
    level: str,
    code: str,
    message: str,
    actionability: str,
    action: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "level": level,
        "code": code,
        "message": message,
        "action": action,
        "actionability": actionability,
    }


class NoticeCollector:
    def __init__(self) -> None:
        self._notices: List[Dict[str, Any]] = []

    @property
    def notices(self) -> List[Dict[str, Any]]:
        return list(self._notices)

    def add(
        self,
        level: str,
        code: str,
        message: str,
        actionability: str,
        action: Optional[str] = None,
    ) -> None:
        self._notices.append(make_notice(level, code, message, actionability, action))

    def routing_graph_missing(self) -> None:
        self.add(
            "error",
            "ROUTING_GRAPH_MISSING",
            "駅ネットワークグラフが見つからないため計算できません。",
            "blocking",
            "settings.routing.graph_id を確認してください。",
        )

    def no_reachable_population(self, office_name: str) -> None:
        self.add(
            "error",
            "NO_REACHABLE_POPULATION",
            f"{office_name}: 到達可能な対象人口が 0 です。",
            "blocking",
            "駅IDやオフィス最寄駅の設定を確認してください。",
        )

    def station_id_not_found(self, station_id: str) -> None:
        self.add(
            "warning",
            "STATION_ID_NOT_FOUND",
            f"station_id '{station_id}' がネットワークグラフに存在しません。",
            "needs_action",
            "駅IDを修正するか、グラフデータを更新してください。",
        )

    def unreachable_exists(self, count: int) -> None:
        self.add(
            "warning",
            "UNREACHABLE_EXISTS",
            f"到達不能な駅が {count} 件あります。",
            "needs_action",
            "到達不能駅の設定を確認してください。",
        )

    def coverage_low(self, ratio: float) -> None:
        self.add(
            "warning",
            "COVERAGE_LOW",
            f"ネットワークカバー率が {ratio * 100:.1f}% です。",
            "needs_action",
            "駅IDやグラフカバレッジを見直してください。",
        )

    def rent_missing(self, office_name: str) -> None:
        self.add(
            "info",
            "RENT_MISSING",
            f"{office_name}: 家賃が未入力です。費用比較の精度が下がります。",
            "informational",
        )

    def sensitivity_unstable(self, flip_rate: float) -> None:
        self.add(
            "warning",
            "SENSITIVITY_UNSTABLE",
            f"感度分析で {flip_rate * 100:.0f}% のケースで最良案が変化しました。",
            "needs_action",
            "候補数を絞って追加検証することを推奨します。",
        )

    def baseline_office_not_found(self, office_id: str) -> None:
        self.add(
            "warning",
            "BASELINE_OFFICE_NOT_FOUND",
            f"baseline_office_id '{office_id}' が候補に存在しません。",
            "needs_action",
            "settings.baseline_office_id を確認してください。",
        )

    def weights_all_zero_fallback(self) -> None:
        self.add(
            "warning",
            "WEIGHTS_ALL_ZERO_FALLBACK",
            "ranking_weights が全て 0 のため access=1.0 で評価しました。",
            "informational",
        )

    def transfer_penalty_unsupported(self, value: float) -> None:
        self.add(
            "warning",
            "TRANSFER_PENALTY_UNSUPPORTED",
            f"transfer_penalty_minutes={value} は現行ロジックで未対応です。",
            "informational",
        )

    def station_coord_missing(self, station_id: str) -> None:
        self.add(
            "info",
            "STATION_COORD_MISSING",
            f"station_id '{station_id}' の座標が station_master にありません。",
            "informational",
        )

    def override_applied(self, count: int) -> None:
        self.add(
            "info",
            "OVERRIDE_APPLIED",
            f"office_days_per_week_override を {count} 件に適用しました。",
            "informational",
        )

    def commute_worsening_distribution(self, count: int, threshold_minutes: float) -> None:
        if count <= 0:
            return
        self.add(
            "warning",
            "COMMUTE_WORSENING_DISTRIBUTION",
            f"baseline 比で {threshold_minutes:.0f} 分超の対象が {count} 人増えました。",
            "informational",
        )

    def hazard_data_partial_coverage(self, available: int, total: int) -> None:
        if total <= 0 or available == total:
            return
        self.add(
            "info",
            "HAZARD_DATA_PARTIAL_COVERAGE",
            f"ハザード評価可能なオフィスは {available}/{total} 件です。",
            "informational",
        )

    def hazard_warning(self, office_name: str, detail: str) -> None:
        self.add(
            "info",
            "HAZARD_WARNING",
            f"{office_name}: {detail}",
            "informational",
        )

    def no_pareto_candidates(self) -> None:
        self.add(
            "error",
            "NO_PARETO_CANDIDATES",
            "制約後に有効な候補が 0 件です。",
            "blocking",
            "制約条件を緩和してください。",
        )

    def department_partially_missing(self, missing_people: int) -> None:
        self.add(
            "warning",
            "DEPARTMENT_PARTIALLY_MISSING",
            f"部署未入力が {missing_people} 名います。該当者は個人単位で配置されました。",
            "informational",
        )
