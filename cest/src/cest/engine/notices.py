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

    def add(self, level: str, code: str, message: str, actionability: str, action: Optional[str] = None) -> None:
        self._notices.append(make_notice(level, code, message, actionability, action))

    def routing_graph_missing(self) -> None:
        self.add("error", "ROUTING_GRAPH_MISSING", "駅ネットワークグラフが見つかりません。計算を実行できません。", "blocking",
                 "routing.graph_id の設定を確認してください。")

    def no_reachable_population(self, office_name: str) -> None:
        self.add("error", "NO_REACHABLE_POPULATION",
                 f"{office_name}: 到達可能な社員が0人です。KPIは全てnullになります。", "blocking",
                 "居住駅分布またはオフィス最寄駅の設定を確認してください。")

    def station_id_not_found(self, station_id: str) -> None:
        self.add("warning", "STATION_ID_NOT_FOUND",
                 f"駅ID「{station_id}」がネットワークグラフに存在しません。", "needs_action",
                 "駅IDを確認するか、グラフデータを更新してください。")

    def unreachable_exists(self, count: int) -> None:
        self.add("warning", "UNREACHABLE_EXISTS",
                 f"{count}件の駅が到達不能です。これらの駅はKPI計算から除外されます。", "needs_action",
                 "到達不能駅の一覧を確認してください。")

    def coverage_low(self, ratio: float) -> None:
        self.add("warning", "COVERAGE_LOW",
                 f"ネットワークカバー率が{ratio*100:.1f}%で、90%未満です。一部の社員が評価対象外です。", "needs_action",
                 "居住駅データまたはネットワークグラフのカバー範囲を確認してください。")

    def rent_missing(self, office_name: str) -> None:
        self.add("info", "RENT_MISSING",
                 f"{office_name}: 家賃が未入力です。financial軸のスコアはnullになります。", "informational")

    def sensitivity_unstable(self, flip_rate: float) -> None:
        self.add("warning", "SENSITIVITY_UNSTABLE",
                 f"前提を±5分変えると、{flip_rate*100:.0f}%のケースで1位が変わります。結論は不安定です。", "needs_action",
                 "各オフィス候補のラストマイル（徒歩/バス分）を実測または正確な値で入力してから再計算してください。")

    def baseline_office_not_found(self, office_id: str) -> None:
        self.add("warning", "BASELINE_OFFICE_NOT_FOUND",
                 f"baseline_office_id「{office_id}」が候補に存在しません。先頭の候補をbaselineとして使用します。", "needs_action",
                 "settings.baseline_office_id を確認してください。")

    def weights_all_zero_fallback(self) -> None:
        self.add("warning", "WEIGHTS_ALL_ZERO_FALLBACK",
                 "全ての重みが0です。access=1.0として計算します。", "informational")

    def transfer_penalty_unsupported(self, value: float) -> None:
        self.add("warning", "TRANSFER_PENALTY_UNSUPPORTED",
                 f"transfer_penalty_minutes={value}が指定されましたが、v0.1では0のみサポートです。無視します。", "informational")

    def station_coord_missing(self, station_id: str) -> None:
        self.add("info", "STATION_COORD_MISSING",
                 f"駅「{station_id}」の座標がStation Masterに存在しません。Cesiumでは非表示になります。", "informational")

    def override_applied(self, count: int) -> None:
        self.add("info", "OVERRIDE_APPLIED",
                 f"{count}件の駅/セグメントでoffice_days_per_week_overrideが適用されました。", "informational")

    def commute_worsening_distribution(self, count: int, threshold_minutes: float) -> None:
        if count <= 0:
            return
        self.add(
            "warning",
            "COMMUTE_WORSENING_DISTRIBUTION",
            f"baselineと比較して片道{threshold_minutes:.0f}分以上悪化する社員が{count}人います。",
            "informational",
        )

    def hazard_data_partial_coverage(self, available: int, total: int) -> None:
        if total <= 0 or available == total:
            return
        self.add(
            "info",
            "HAZARD_DATA_PARTIAL_COVERAGE",
            f"ハザードデータが利用可能なオフィスは{available}/{total}件です。一部の候補ではハザード軸が計算されません。",
            "informational",
        )

    # ── v0.3 追加 ──────────────────────────────────────────

    def hazard_warning(self, station_id: str, detail: str) -> None:
        self.add(
            "warning",
            "HAZARD_WARNING",
            f"{station_id}: {detail}。自治体のハザードマップを確認してください。",
            "informational",
        )

    def capacity_tight(self, office_name: str, headroom: int) -> None:
        self.add(
            "warning",
            "CAPACITY_TIGHT",
            f"{office_name}: 推定収容人数まで余裕{headroom}人。増員時に注意が必要です。",
            "informational",
        )

    def no_pareto_candidates(self) -> None:
        self.add(
            "error",
            "NO_PARETO_CANDIDATES",
            "制約フィルタ後に有効な組み合わせが0件です。制約を緩和してください。",
            "blocking",
        )
