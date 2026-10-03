"""找空檔 API（見 spec/scheduling-agent.md）。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.booking_parser.slot_search import (
    RecurringPlanRequest,
    RecurringPlanResult,
    RecurringSearchRequest,
    RecurringSearchResult,
    SlotSearchNotAllowed,
    SlotSearchRequest,
    SlotSearchResult,
    area_presets,
    plan_recurring,
    search_recurring,
    search_slots,
)
from app.database import get_db
from app.timeutil import now_taipei

router = APIRouter(prefix="/api/slot-search", tags=["slot-search"])

TAIWAN_TZ = timezone(timedelta(hours=8))


def get_now() -> datetime:
    """台灣當地時間、不帶時區（跟課程資料表的存法一致）。獨立成 dependency
    是為了讓測試可以固定「現在」，不會因為真實日期往後走而壞掉。"""
    return now_taipei()


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


@router.post("/recurring/plan", response_model=RecurringPlanResult)
def plan_recurring_slots(
    payload: RecurringPlanRequest, db: Session = Depends(get_db), now: datetime = Depends(get_now)
):
    """指定時段逐週排排看：撞課時列出同館其他時段，可接課時提示（見 recurring_finder.plan_weeks）。"""
    try:
        return plan_recurring(db, payload, now)
    except SlotSearchNotAllowed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
