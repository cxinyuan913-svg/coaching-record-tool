"""約課訊息解析 API（見功能規格 1.7）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.booking_parser.llm_client import AnthropicExtractionClient, ExtractionClient
from app.booking_parser.schemas import ParseMessageRequest
from app.booking_parser.service import ParseResult, parse_message
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
