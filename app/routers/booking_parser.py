"""約課訊息解析 API（見功能規格 1.7），以及找空檔排班（見 spec/scheduling-agent.md）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.booking_parser.llm_client import AnthropicExtractionClient, ExtractionClient
from app.booking_parser.schemas import ParseMessageRequest
from app.booking_parser.service import TAIWAN_TZ, ParseResult, parse_message
from app.booking_parser.suggest import (
    SuggestNotFound,
    SuggestRequest,
    SuggestResult,
    SuggestUnavailable,
    suggest_slots,
)
from app.database import get_db

router = APIRouter(prefix="/api/booking-requests", tags=["booking-requests"])


def get_extraction_client() -> ExtractionClient:
    """預設用 Anthropic 的實作；ANTHROPIC_API_KEY 沒設定時回傳清楚的
    錯誤訊息，不要讓使用者看到不知所云的例外堆疊。"""
    try:
        return AnthropicExtractionClient()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/parse", response_model=ParseResult)
def parse_booking_message(
    payload: ParseMessageRequest,
    db: Session = Depends(get_db),
    client: ExtractionClient = Depends(get_extraction_client),
):
    return parse_message(db, client, payload.text, payload.reference_datetime)


def get_now() -> datetime:
    """台灣當地時間、不帶時區（跟課程資料表的存法一致）。獨立成 dependency
    是為了讓測試可以固定「現在」，不會因為真實日期往後走而壞掉。"""
    return datetime.now(TAIWAN_TZ).replace(tzinfo=None)


@router.post("/{booking_request_id}/suggest", response_model=SuggestResult)
def suggest_booking_slots(
    booking_request_id: int,
    payload: SuggestRequest | None = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    try:
        return suggest_slots(db, booking_request_id, payload or SuggestRequest(), now)
    except SuggestNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SuggestUnavailable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
