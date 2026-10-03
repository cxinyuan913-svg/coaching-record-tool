"""找空檔 API（見 spec/scheduling-agent.md）。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.booking_parser.slot_search import (
    RecurringSearchRequest,
    RecurringSearchResult,
    SlotSearchNotAllowed,
    SlotSearchRequest,
    SlotSearchResult,
    area_presets,
    search_recurring,
    search_slots,
)
from app.database import get_db

router = APIRouter(prefix="/api/slot-search", tags=["slot-search"])

TAIWAN_TZ = timezone(timedelta(hours=8))


def get_now() -> datetime:
    """台灣當地時間、不帶時區（跟課程資料表的存法一致）。獨立成 dependency
    是為了讓測試可以固定「現在」，不會因為真實日期往後走而壞掉。"""
    return datetime.now(TAIWAN_TZ).replace(tzinfo=None)


@router.get("/areas", response_model=dict[str, list[int]])
def list_area_presets(db: Session = Depends(get_db)):
    return area_presets(db)


@router.post("", response_model=SlotSearchResult)
def search(payload: SlotSearchRequest, db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    try:
        return search_slots(db, payload, now)
    except SlotSearchNotAllowed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/recurring", response_model=RecurringSearchResult)
def search_recurring_slots(
    payload: RecurringSearchRequest, db: Session = Depends(get_db), now: datetime = Depends(get_now)
):
    """固定時段排課：每週同一天、同一時段、同一場館，連續 N 週（見 recurring_finder.py）。"""
    try:
        return search_recurring(db, payload, now)
    except SlotSearchNotAllowed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
