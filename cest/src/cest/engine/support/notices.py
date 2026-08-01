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

    def station_id_not_found(self, station_id: str) -> None:
        self.add(
            "warning",
            "STATION_ID_NOT_FOUND",
            f"station_id '{station_id}' がネットワークグラフに存在しません。",
            "needs_action",
            "駅IDを修正するか、グラフデータを更新してください。",
        )

    def rent_missing(self, office_name: str) -> None:
        self.add(
            "info",
            "RENT_MISSING",
            f"{office_name}: 家賃が未入力です。費用比較の精度が下がります。",
            "informational",
        )

    def station_coord_missing(self, station_id: str) -> None:
        self.add(
            "info",
            "STATION_COORD_MISSING",
            f"station_id '{station_id}' の座標が station_master にありません。",
            "informational",
        )

    def hazard_warning(self, office_name: str, detail: str) -> None:
        self.add(
            "info",
            "HAZARD_WARNING",
            f"{office_name}: {detail}",
            "informational",
        )

    def hazard_data_missing(self, office_names: List[str]) -> None:
        names = "、".join(office_names)
        self.add(
            "info",
            "HAZARD_DATA_MISSING",
            f"{names}: ハザードデータが未収集のため、浸水・地震リスクを判定できません（警告が無い＝安全ではありません）。",
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

    def fixed_offices_exceed_max(self, fixed_count: int, max_num_offices: int) -> None:
        self.add(
            "error",
            "FIXED_OFFICES_EXCEED_MAX",
            f"固定オフィスが{fixed_count}件ありますが、拠点数の上限が{max_num_offices}件のため、"
            f"組み合わせが1件も作れません。",
            "needs_action",
            f"「最大何拠点まで許す？」を{fixed_count}件以上に増やすか、固定オフィスを減らしてください。",
        )

    def department_partially_missing(self, missing_people: int) -> None:
        self.add(
            "warning",
            "DEPARTMENT_PARTIALLY_MISSING",
            f"部署未入力が {missing_people} 名います。該当者は個人単位で配置されました。",
            "informational",
        )
