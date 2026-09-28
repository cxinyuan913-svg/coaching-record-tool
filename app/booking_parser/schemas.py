"""約課訊息 LLM 結構化抽取的輸出格式（見功能規格 1.1），以及這整個
booking_parser 子系統對外 API 用的請求/回應格式（見規格 1.7）。放在
同一個檔案是刻意的：這個子系統的 schema 都只有這裡自己會用到，不用
散到 app/schemas.py 裡跟其他既有功能的 schema 混在一起。

LLM 只負責語言理解，日期不直接輸出成絕對日期（例如「2026-10-07」），而是
輸出 DateExpr 這種相對描述（例如「下週三」），由 resolver.py 換算成實際
日期——這樣日期不會算錯，也容易測試（見 resolver.py 開頭的說明）。
"""
from datetime import datetime, time
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Intent(str, Enum):
    new_booking = "new_booking"  # 約新課
    reschedule = "reschedule"  # 改時間（本次只標記不處理）
    cancel = "cancel"  # 取消（本次只標記不處理）
    other = "other"  # 不是約課相關


class PartOfDay(str, Enum):
    morning = "morning"
    afternoon = "afternoon"
    evening = "evening"


class DateExpr(BaseModel):
    """LLM 輸出的日期描述，三選一，由 resolver.py 換算成實際日期。"""

    absolute_month: int | None = Field(None, ge=1, le=12)  # 「10/15」→ 10
    absolute_day: int | None = Field(None, ge=1, le=31)  # 「10/15」→ 15
    day_offset: int | None = Field(None, ge=0, le=60)  # 「今天」0、「明天」1、「後天」2
    week_offset: int | None = Field(None, ge=0, le=8)  # 「這週」0、「下週」1、「下下週」2
    weekday: int | None = Field(None, ge=1, le=7)  # 週一=1 … 週日=7，需搭配 week_offset

    @model_validator(mode="after")
    def exactly_one_form(self):
        forms = [
            self.absolute_month is not None and self.absolute_day is not None,
            self.day_offset is not None,
            self.week_offset is not None and self.weekday is not None,
        ]
        if sum(forms) != 1:
            raise ValueError("DateExpr 必須剛好使用一種表示法")
        return self


class TimeWindowExpr(BaseModel):
    date: DateExpr
    part_of_day: PartOfDay | None = None  # 「晚上」
    start_time: time | None = None  # 「七點」→ 19:00（依上下文判斷上午或下午）
    end_time: time | None = None


class ParsedBookingRequest(BaseModel):
    intent: Intent
    student_name: str | None = None  # 訊息中提到的名字，原樣輸出，不要猜
    area: str | None = None  # 原樣輸出訊息中的地點字詞，例如「竹北」
    windows: list[TimeWindowExpr] = Field(default_factory=list, max_length=6)
    duration_minutes: int | None = Field(None, ge=30, le=240)
    ambiguities: list[str] = Field(default_factory=list)  # LLM 覺得不確定的地方


class ParseMessageRequest(BaseModel):
    """POST /api/booking-requests/parse 的請求格式（規格 1.7）。"""

    text: str
    reference_datetime: datetime | None = None  # 選填，預設現在（台灣時間）
