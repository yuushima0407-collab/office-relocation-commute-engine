from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cest.engine.csv_parser import parse_employee_csv


class ParseCsvRequest(BaseModel):
    csv_text: str


class HomeStationRow(BaseModel):
    station_id: str
    count: int
    group: str | None = None


class ParseCsvResponse(BaseModel):
    home_station_distribution: list[HomeStationRow]


router = APIRouter(tags=["parse-csv"])


@router.post("/parse-csv", response_model=ParseCsvResponse)
def post_parse_csv(body: ParseCsvRequest) -> ParseCsvResponse:
    try:
        rows_raw = parse_employee_csv(body.csv_text)
        rows = [HomeStationRow(**r) for r in rows_raw]
        return ParseCsvResponse(home_station_distribution=rows)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

