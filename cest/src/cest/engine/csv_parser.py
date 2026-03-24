from __future__ import annotations

import csv
from io import BytesIO, StringIO
from typing import Any, Dict, List, Optional

from cest.engine.graph_loader import load_station_master

# ── カラム名エイリアス ────────────────────────────────────────────────────────

_STATION_ALIASES = {"最寄り駅", "station_id", "station", "駅名", "最寄駅", "自宅最寄り駅", "最寄り駅名", "自宅駅"}
_COUNT_ALIASES   = {"人数", "count", "社員数", "名"}   # 任意。なければ1行=1人として扱う
_GROUP_ALIASES   = {"部署", "group", "部門", "所属", "部署名", "所属部署", "所属部署名"}
_FARE_ALIASES    = {"通勤費", "通勤手当", "commute_allowance", "commute_allowance_jpy_month",
                    "月額定期代", "定期代", "月額通勤費", "月額通勤手当", "通勤費（円）",
                    "月額定期代（円）", "月額通勤費（円）"}


def _find_col(headers: List[str], aliases: set) -> Optional[str]:
    """ヘッダーリストからエイリアスに一致する列名を返す。"""
    for h in headers:
        if h.strip() in aliases:
            return h
    return None


def _build_station_index() -> Dict[str, str]:
    master = load_station_master()
    index: Dict[str, str] = {}
    for station_id, meta in master.items():
        name = meta.get("name")
        index[station_id] = station_id
        if isinstance(name, str) and name:
            index[name] = station_id
    return index


# ── フォーマット判定・読み込み ─────────────────────────────────────────────────

def _detect_delimiter(content: str) -> str:
    """CSVかTSVかを先頭行のタブ数で判定する。"""
    first_line = content.split("\n")[0]
    return "\t" if first_line.count("\t") > first_line.count(",") else ","


def _read_rows(content: str) -> List[Dict[str, str]]:
    """CSV/TSVテキストを行リストに変換する。"""
    delimiter = _detect_delimiter(content)
    reader = csv.DictReader(StringIO(content), delimiter=delimiter)
    return [dict(row) for row in reader]


def _read_rows_from_excel(data: bytes) -> List[Dict[str, str]]:
    """Excelバイナリを行リストに変換する。openpyxl が必要。"""
    try:
        import openpyxl
    except ImportError:
        raise ImportError("Excel対応には openpyxl が必要です: pip install openpyxl")

    wb = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(c) if c is not None else "" for c in rows[0]]
    result = []
    for row in rows[1:]:
        result.append({headers[i]: (str(v) if v is not None else "") for i, v in enumerate(row)})
    return result


# ── 行リスト → home_station_distribution 変換 ──────────────────────────────

def _rows_to_distribution(
    rows: List[Dict[str, str]],
    station_index: Dict[str, str],
) -> List[Dict[str, Any]]:
    if not rows:
        return []

    headers = list(rows[0].keys())
    col_station = _find_col(headers, _STATION_ALIASES)
    col_count   = _find_col(headers, _COUNT_ALIASES)
    col_group   = _find_col(headers, _GROUP_ALIASES)
    col_fare    = _find_col(headers, _FARE_ALIASES)

    missing = []
    if col_station is None:
        missing.append(f"駅列（{'/'.join(sorted(_STATION_ALIASES))}のいずれか）")
    if missing:
        raise ValueError(f"必須列が見つかりません: {', '.join(missing)}")
    # 人数列は任意。なければ1行=1人として扱う（HRシステムの社員マスタ形式に対応）

    result: List[Dict[str, Any]] = []
    for raw in rows:
        raw_station = (raw.get(col_station) or "").strip()
        if not raw_station:
            continue

        station_id = station_index.get(raw_station, raw_station)

        if col_count is None:
            count = 1  # 人数列なし = 1行1人（社員マスタ形式）
        else:
            try:
                count = int(float(raw.get(col_count, "0") or "0"))
            except ValueError:
                continue
            if count <= 0:
                continue

        group = (raw.get(col_group) or "").strip() or None

        fare: Optional[int] = None
        if col_fare:
            raw_fare = (raw.get(col_fare) or "").strip()
            if raw_fare:
                try:
                    fare = int(float(raw_fare))
                except ValueError:
                    pass

        row: Dict[str, Any] = {"station_id": station_id, "count": count, "group": group}
        if fare is not None:
            row["commute_allowance_jpy_month"] = fare
        result.append(row)

    return result


# ── 公開 API ──────────────────────────────────────────────────────────────────

def parse_employee_csv(content: str) -> List[Dict[str, Any]]:
    """
    社員データ CSV/TSV を home_station_distribution 形式に変換する。

    対応列名（いずれかがあれば認識）:
      駅:   最寄り駅 / station_id / station / 駅名 / 最寄駅
      人数: 人数 / count / 社員数 / 名
      部署: 部署 / group / 部門 / 所属  （任意）
      通勤費: 通勤費 / 通勤手当 / commute_allowance  （任意・円/月）

    駅名が日本語の場合は station_master.json で station_id に変換する。
    未知の駅名はそのまま station_id として扱い、後続で UNREACHABLE になる。
    """
    station_index = _build_station_index()
    rows = _read_rows(content)
    return _rows_to_distribution(rows, station_index)


def parse_employee_excel(data: bytes) -> List[Dict[str, Any]]:
    """
    社員データ Excel (.xlsx) を home_station_distribution 形式に変換する。
    列名の認識ルールは parse_employee_csv と同じ。
    """
    station_index = _build_station_index()
    rows = _read_rows_from_excel(data)
    return _rows_to_distribution(rows, station_index)


def merge_distributions(
    base: List[Dict[str, Any]],
    supplement: List[Dict[str, Any]],
    merge_key: str = "station_id",
) -> List[Dict[str, Any]]:
    """
    2つの home_station_distribution をマージする。

    用途: 社員マスタ（駅・部署・人数）と通勤手当台帳（駅・通勤費）を別ファイルで
    受け取った場合に、merge_key（デフォルト: station_id）で突き合わせて統合する。

    - base に supplement の追加フィールド（commute_allowance_jpy_month 等）を上書きマージ
    - supplement にしかない行は無視する（station_id が base にない場合）
    """
    supplement_map: Dict[str, Dict[str, Any]] = {}
    for row in supplement:
        key = row.get(merge_key)
        if key:
            supplement_map[key] = row

    merged = []
    for row in base:
        key = row.get(merge_key)
        extra = supplement_map.get(key, {})
        merged.append({**row, **{k: v for k, v in extra.items() if k not in row or v is not None}})
    return merged
