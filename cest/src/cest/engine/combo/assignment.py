"""部署配置最適化（group_together / fixed_assignment 対応）。

全体の流れは combination.py の run_v3_pipeline を参照。
"""
from __future__ import annotations

from typing import Dict, List, Optional

import networkx as nx

from cest.models.request import HomeStation, OfficeCandidate
from cest.engine.combo.common import _get_group, _index_offices
from cest.engine.support.routing import calc_trip_minutes


def _resolve_super_groups(
    group_together: List[List[str]],
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for cluster in group_together:
        if not cluster:
            continue
        rep = cluster[0]
        for g in cluster:
            mapping[g] = rep
    return mapping


def build_group_assignment(
    G: nx.Graph,
    home_stations: List[HomeStation],
    offices: List[OfficeCandidate],
    fixed_assignment: List[Dict[str, str]],
    group_together: List[List[str]],
) -> Dict[str, str]:
    office_by_id = _index_offices(offices)

    fixed_map: Dict[str, str] = {}
    for item in fixed_assignment:
        g, oid = item.get("group", ""), item.get("office_id", "")
        if g and oid in office_by_id:
            fixed_map[g] = oid

    super_group_map = _resolve_super_groups(group_together)
    all_groups = {_get_group(hs) for hs in home_stations}

    assignment: Dict[str, str] = {}
    processed_supers: Dict[str, str] = {}

    for g in all_groups:
        sg = super_group_map.get(g, g)

        if sg in processed_supers:
            assignment[g] = processed_supers[sg]
            continue

        fixed_oid = None
        for member in _members_of_super_group(sg, super_group_map, all_groups):
            if member in fixed_map:
                fixed_oid = fixed_map[member]
                break

        if fixed_oid and fixed_oid in office_by_id:
            result_oid = fixed_oid
        else:
            members = list(_members_of_super_group(sg, super_group_map, all_groups))
            rows = [hs for hs in home_stations if _get_group(hs) in members]
            result_oid = _best_office_for_group(G, rows, offices)

        if result_oid:
            processed_supers[sg] = result_oid
            for member in _members_of_super_group(sg, super_group_map, all_groups):
                assignment[member] = result_oid
        if g not in assignment and result_oid:
            assignment[g] = result_oid

    return assignment


def _members_of_super_group(
    sg: str,
    super_group_map: Dict[str, str],
    all_groups: set,
) -> List[str]:
    return [g for g in all_groups if super_group_map.get(g, g) == sg]


# 課題: この関数は各グループを独立に「一番近いオフィス」へ割り当てるだけで、
# 他グループが既にそのオフィスへ送った人数（残り席）を考慮しない。
# 定員オーバーになった組み合わせは filter.py 側で丸ごと不採用になるため、
# 「近いオフィスに人が集中して溢れた」だけで、本来分散すれば成立したはずの
# 改善案（例: 通勤が大変なエリアへの新規オフィス案）ごと候補から消えてしまう。
# 改善案: 部署は分割不可のまま「全員の通勤時間合計を最小化する」制約付き割り当てが必要
# → 一般化割当問題（Generalized Assignment Problem）。PuLP 等の ILP ソルバーで解ける規模。
# （2026-08-04 時点、対応は見送り。参照: 対応する greedy/min-cost-flow/ILP の比較検討ログ）
def _best_office_for_group(
    G: nx.Graph,
    rows: List[HomeStation],
    offices: List[OfficeCandidate],
) -> Optional[str]:
    best_oid: Optional[str] = None
    best_avg: Optional[float] = None
    for office in offices:
        total = 0.0
        total_count = 0
        for hs in rows:
            t = calc_trip_minutes(G, hs.station_id, office.nearest_station_id, office.last_mile_minutes)
            if t is None:
                continue
            total += t * hs.count
            total_count += hs.count
        if total_count == 0:
            continue
        avg = total / total_count
        if best_avg is None or avg < best_avg:
            best_avg = avg
            best_oid = office.office_id
    return best_oid
