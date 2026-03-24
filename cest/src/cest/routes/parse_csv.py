from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional

from cest.engine.csv_parser import parse_employee_csv, parse_employee_excel


class ParseCsvRequest(BaseModel):
    csv_text: str


class HomeStationRow(BaseModel):
    station_id: str
    count: int
    group: str | None = None
    commute_allowance_jpy_month: Optional[int] = None


class ParseCsvResponse(BaseModel):
    home_station_distribution: list[HomeStationRow]


router = APIRouter(tags=["parse-csv"])


@router.post("/parse-csv", response_model=ParseCsvResponse)
def post_parse_csv(body: ParseCsvRequest) -> ParseCsvResponse:
    """CSV/TSVテキストを home_station_distribution 形式に変換する。"""
    try:
        rows_raw = parse_employee_csv(body.csv_text)
        rows = [HomeStationRow(**r) for r in rows_raw]
        return ParseCsvResponse(home_station_distribution=rows)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/parse-csv/upload", response_model=ParseCsvResponse)
async def post_parse_csv_upload(file: UploadFile = File(...)) -> ParseCsvResponse:
    """CSV/TSV/Excel ファイルをアップロードして home_station_distribution 形式に変換する。"""
    try:
        filename = file.filename or ""
        data = await file.read()

        if filename.endswith(".xlsx"):
            rows_raw = parse_employee_excel(data)
        else:
            rows_raw = parse_employee_csv(data.decode("utf-8-sig"))  # BOM付きUTF-8対応

        rows = [HomeStationRow(**r) for r in rows_raw]
        return ParseCsvResponse(home_station_distribution=rows)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
