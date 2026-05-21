from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional

from cest.engine.csv_parser import (
    parse_employee_csv_extended,
    parse_employee_excel_extended,
)


class ParseCsvRequest(BaseModel):
    csv_text: str


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
    try:
        filename = file.filename or ""
        data = await file.read()

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
