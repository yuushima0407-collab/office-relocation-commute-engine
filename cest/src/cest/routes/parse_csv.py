from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import List, Optional

from cest.engine.csv_parser import (
    parse_employee_csv_extended,
    parse_employee_excel_extended,
)


class ParseCsvRequest(BaseModel):
    # 入力サイズの上限。/parse-csv/upload と同じく ~5MB で頭打ちにする。
    csv_text: str = Field(..., max_length=5_000_000)


class HomeStationRow(BaseModel):
    station_id: str
    count: int
    group: str | None = None
    commute_allowance_jpy_month: Optional[int] = None


class UnresolvedStation(BaseModel):
    raw: str
    row_number: int
    candidates: List[str] = []


class ParseCsvResponse(BaseModel):
    home_station_distribution: List[HomeStationRow]
    unresolved_stations: List[UnresolvedStation] = []


router = APIRouter(tags=["parse-csv"])

# アップロード上限（Lambda 同期呼び出しの 6MB ペイロード制限の内側に収める）。
# 社員名簿の CSV/Excel には十分な余裕。これを超える入力は 413 で弾く。
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.post("/parse-csv", response_model=ParseCsvResponse)
def post_parse_csv(body: ParseCsvRequest) -> ParseCsvResponse:
    """CSV/TSVテキストを home_station_distribution 形式に変換する。"""
    try:
        dist_raw, unresolved_raw = parse_employee_csv_extended(body.csv_text)
        rows = [HomeStationRow(**r) for r in dist_raw]
        unresolved = [UnresolvedStation(**u) for u in unresolved_raw]
        return ParseCsvResponse(home_station_distribution=rows, unresolved_stations=unresolved)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/parse-csv/upload", response_model=ParseCsvResponse)
async def post_parse_csv_upload(file: UploadFile = File(...)) -> ParseCsvResponse:
    """CSV/TSV/Excel ファイルをアップロードして home_station_distribution 形式に変換する。"""
    filename = file.filename or ""
    # 上限+1 バイトだけ読み、超過していれば本文を全部処理する前に弾く。
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"ファイルサイズが上限（{MAX_UPLOAD_BYTES // (1024 * 1024)}MB）を超えています",
        )
    try:
        if filename.endswith(".xlsx"):
            dist_raw, unresolved_raw = parse_employee_excel_extended(data)
        else:
            dist_raw, unresolved_raw = parse_employee_csv_extended(
                data.decode("utf-8-sig")
            )

        rows = [HomeStationRow(**r) for r in dist_raw]
        unresolved = [UnresolvedStation(**u) for u in unresolved_raw]
        return ParseCsvResponse(home_station_distribution=rows, unresolved_stations=unresolved)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
