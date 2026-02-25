from __future__ import annotations

import csv
from io import StringIO
from typing import Any, Dict, List

from cest.engine.graph_loader import load_station_master


def _build_station_index() -> Dict[str, str]:
    """
    station_master.json から
    - station_id -> station_id
    - 駅名（日本語表記） -> station_id
    の簡易インデックスを構築する。
    """
    master = load_station_master()
    index: Dict[str, str] = {}
    for station_id, meta in master.items():
        name = meta.get("name")
        index[station_id] = station_id
        if isinstance(name, str) and name:
            index[name] = station_id
    return index


def parse_employee_csv(content: str) -> List[Dict[str, Any]]:
    """
    社員データCSVをhome_station_distribution形式に変換する。

    入力例:
        station_id,count,group
        omiya,5,開発
        横浜,8,営業

    - ヘッダーは少なくとも station_id, count を含むこと
    - group 列は任意
    - 駅名（日本語）の場合は station_master.json を使って station_id に変換する
    """
    station_index = _build_station_index()

    f = StringIO(content)
    reader = csv.DictReader(f)
    rows: List[Dict[str, Any]] = []
    for raw in reader:
        raw_station = (raw.get("station_id") or "").strip()
        if not raw_station:
            continue

        station_id = station_index.get(raw_station)
        if station_id is None:
            # 未知の駅はそのままIDとして扱う（後続でUNREACHABLEとして扱われる）
            station_id = raw_station

        try:
            count = int(raw.get("count", "0"))
        except ValueError:
            continue
        if count <= 0:
            continue

        group = raw.get("group") or None

        rows.append(
            {
                "station_id": station_id,
                "count": count,
                "group": group,
            }
        )
    return rows

