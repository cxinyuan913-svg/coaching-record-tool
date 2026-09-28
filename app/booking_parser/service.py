"""約課訊息解析主流程（見功能規格 1.5）：呼叫 LLM → Pydantic 驗證 →
日期換算 → 學生/地區比對 → 決定狀態 → 記錄這次呼叫。

「驗證失敗要重試」涵蓋兩種情況（規格 1.5 第 2、3 點）：
1. LLM 輸出沒通過 ParsedBookingRequest 的 schema 驗證。
2. schema 驗證過了，但日期換算失敗（resolve_window 丟
   DateResolutionError）——這通常代表 LLM 理解錯了相對日期的意思
   （例如把「上週」講成「下週」），重試才有意義。

學生/地區比對不到人不算「LLM 講錯話」，不會觸發重試（重試同一句話、
同一個模型，比對不到的學生還是比對不到），而是直接反映在最終狀態
needs_review 上，讓人工確認。
"""
import json
from datetime import datetime, timezone, timedelta

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.orm import Session

from app import models
from app.booking_parser.llm_client import PROMPT_VERSION, ExtractionClient
from app.booking_parser.matcher import AreaMatchResult, StudentMatchResult, match_area, match_student
from app.booking_parser.resolver import DateResolutionError, ResolvedWindow, resolve_window
from app.booking_parser.schemas import Intent, ParsedBookingRequest
from app.models import BookingRequestStatus

TAIWAN_TZ = timezone(timedelta(hours=8))

# 驗證失敗最多重試幾次（不含第一次呼叫，所以總共最多呼叫 LLM 3 次）
MAX_RETRIES = 2


class ParseResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    booking_request_id: int
    status: BookingRequestStatus
    parsed: ParsedBookingRequest | None
    resolved_windows: list[ResolvedWindow]
    student_match: StudentMatchResult | None
    area_match: AreaMatchResult | None
    ambiguities: list[str]
    retry_count: int


def parse_message(
    db: Session,
    client: ExtractionClient,
    text: str,
    reference_datetime: datetime | None = None,
) -> ParseResult:
    if reference_datetime is None:
        reference_datetime = datetime.now(TAIWAN_TZ)

    parsed: ParsedBookingRequest | None = None
    resolved_windows: list[ResolvedWindow] = []
    resolution_ambiguities: list[str] = []
    last_raw: dict | None = None
    last_error: str | None = None
    total_latency_ms = 0
    total_input_tokens = 0
    total_output_tokens = 0
    attempt = 0

    while attempt <= MAX_RETRIES:
        raw = client.extract(
            text, reference_datetime, retry_errors=[last_error] if last_error else None
        )
        last_raw = raw
        total_latency_ms += getattr(client, "last_latency_ms", None) or 0
        total_input_tokens += getattr(client, "last_input_tokens", None) or 0
        total_output_tokens += getattr(client, "last_output_tokens", None) or 0

        try:
            candidate = ParsedBookingRequest.model_validate(raw)
        except ValidationError as exc:
            last_error = f"格式驗證失敗：{exc}"
            attempt += 1
            continue

        if candidate.intent == Intent.new_booking:
            try:
                windows: list[ResolvedWindow] = []
                ambiguities: list[str] = []
                for window in candidate.windows:
                    resolved, window_ambiguities = resolve_window(window, reference_datetime)
                    windows.append(resolved)
                    ambiguities.extend(window_ambiguities)
            except DateResolutionError as exc:
                last_error = f"日期換算失敗：{exc}"
                attempt += 1
                continue
            resolved_windows = windows
            resolution_ambiguities = ambiguities

        parsed = candidate
        break

    # attempt 在「重試用完還是失敗」的情況下，迴圈結束時會是 MAX_RETRIES+1
    # （最後一次失敗後還會 +1 才跳出 while 條件），這裡夾住上限，讓
    # retry_count 的語意維持「實際重試了幾次」，不是「呼叫了幾次」
    retry_count = min(attempt, MAX_RETRIES)

    student_match: StudentMatchResult | None = None
    area_match: AreaMatchResult | None = None
    ambiguities: list[str] = list(resolution_ambiguities)

    if parsed is None:
        status = BookingRequestStatus.NEEDS_REVIEW
        ambiguities.append(f"重試 {MAX_RETRIES} 次後仍然驗證失敗：{last_error}")
    elif parsed.intent != Intent.new_booking:
        status = BookingRequestStatus.NOT_BOOKING
        ambiguities.extend(parsed.ambiguities)
    else:
        ambiguities.extend(parsed.ambiguities)
        if parsed.student_name:
            student_match = match_student(db, parsed.student_name)
        if parsed.area:
            area_match = match_area(db, parsed.area)

        needs_review = (
            bool(ambiguities)
            or (student_match is not None and student_match.needs_review)
            or (area_match is not None and area_match.needs_review)
        )
        status = BookingRequestStatus.NEEDS_REVIEW if needs_review else BookingRequestStatus.OK

    booking_request = models.BookingRequest(
        raw_text=text,
        reference_datetime=reference_datetime,
        parsed_json=json.dumps(
            parsed.model_dump(mode="json") if parsed is not None else last_raw, ensure_ascii=False
        ),
        resolved_json=json.dumps(
            [w.model_dump(mode="json") for w in resolved_windows], ensure_ascii=False
        ),
        status=status,
        retry_count=retry_count,
        model=getattr(client, "model", None) or client.name,
        prompt_version=PROMPT_VERSION,
        latency_ms=total_latency_ms or None,
        input_tokens=total_input_tokens or None,
        output_tokens=total_output_tokens or None,
    )
    db.add(booking_request)
    db.commit()
    db.refresh(booking_request)

    return ParseResult(
        booking_request_id=booking_request.id,
        status=status,
        parsed=parsed,
        resolved_windows=resolved_windows,
        student_match=student_match,
        area_match=area_match,
        ambiguities=ambiguities,
        retry_count=retry_count,
    )
