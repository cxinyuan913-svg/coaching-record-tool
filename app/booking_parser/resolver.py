"""日期換算（見功能規格 1.2）：把 LLM 輸出的相對日期描述（DateExpr／
TimeWindowExpr）換算成實際日期/時間。這裡完全是純程式邏輯，LLM 不參與，
才能寫成確定性的單元測試、日期不會算錯。
"""
from datetime import date, datetime, time, timedelta, timezone

from pydantic import BaseModel

from app.booking_parser.schemas import DateExpr, PartOfDay, TimeWindowExpr

TAIWAN_TZ = timezone(timedelta(hours=8))

# 時段對應（規格 1.2，之後教練可能依實際上課時段調整這幾個常數）
PART_OF_DAY_RANGES: dict[PartOfDay, tuple[time, time]] = {
    PartOfDay.morning: (time(8, 0), time(12, 0)),
    PartOfDay.afternoon: (time(13, 0), time(17, 0)),
    PartOfDay.evening: (time(18, 0), time(22, 0)),
}
# 只有日期、沒有時段 → 整天可上課時段
FULL_DAY_RANGE: tuple[time, time] = (time(8, 0), time(22, 0))
# 只有 start_time、沒有 end_time 時的預設窗口長度（分鐘）
DEFAULT_WINDOW_MINUTES = 60


class DateResolutionError(ValueError):
    """換算後的日期不合理（例如早於今天）時拋出，呼叫端（service.py）視為
    驗證失敗，走重試或標記 needs_review 的流程。"""


class ResolvedWindow(BaseModel):
    date: date
    start: datetime
    end: datetime


def resolve_date(expr: DateExpr, reference_datetime: datetime) -> tuple[date, list[str]]:
    """回傳 (換算出的日期, 這次換算過程附帶的 ambiguity 說明列表)。

    三種表示法互斥（DateExpr 的 pydantic validator 已經保證剛好一種），
    這裡只要照表示法算：
    - 絕對月日：用今年，如果那個日期已經過了今天，改用明年，並記一條
      ambiguity 讓使用者知道系統做了這個假設。
    - day_offset：今天 + N 天。
    - week_offset + weekday：「這週」= 週一開始的本週，「下週」= 下一個
      週一開始的那週，以此類推；weekday 1=週一…7=週日。
    """
    ambiguities: list[str] = []
    ref_date = reference_datetime.date()

    if expr.absolute_month is not None and expr.absolute_day is not None:
        year = ref_date.year
        try:
            candidate = date(year, expr.absolute_month, expr.absolute_day)
        except ValueError as exc:
            raise DateResolutionError(
                f"無效的日期：{expr.absolute_month}/{expr.absolute_day}"
            ) from exc
        if candidate < ref_date:
            candidate = date(year + 1, expr.absolute_month, expr.absolute_day)
            ambiguities.append(
                f"日期 {expr.absolute_month}/{expr.absolute_day} 已經過了今天，"
                f"視為明年（{candidate.isoformat()}）"
            )
        result = candidate

    elif expr.day_offset is not None:
        result = ref_date + timedelta(days=expr.day_offset)

    elif expr.week_offset is not None and expr.weekday is not None:
        this_monday = ref_date - timedelta(days=ref_date.weekday())  # Python: 週一=0
        target_monday = this_monday + timedelta(weeks=expr.week_offset)
        result = target_monday + timedelta(days=expr.weekday - 1)  # weekday: 週一=1…週日=7

    else:  # pragma: no cover - DateExpr 的 validator 已經擋掉這個狀況
        raise DateResolutionError("DateExpr 沒有任何有效表示法")

    if result < ref_date:
        raise DateResolutionError(
            f"換算出的日期 {result.isoformat()} 早於今天 {ref_date.isoformat()}"
        )
    return result, ambiguities


def resolve_window(window: TimeWindowExpr, reference_datetime: datetime) -> tuple[ResolvedWindow, list[str]]:
    """把一個 TimeWindowExpr 換算成實際的 (date, start, end)。

    時間範圍的判斷優先順序：明確的 start_time（搭配 end_time，沒給就用
    start_time + DEFAULT_WINDOW_MINUTES）> part_of_day 對應的固定時段 >
    都沒有就用整天可上課時段。
    """
    result_date, ambiguities = resolve_date(window.date, reference_datetime)

    if window.start_time is not None:
        start_t = window.start_time
        if window.end_time is not None:
            end_t = window.end_time
        else:
            end_dt = datetime.combine(result_date, start_t) + timedelta(minutes=DEFAULT_WINDOW_MINUTES)
            end_t = end_dt.time()
    elif window.part_of_day is not None:
        start_t, end_t = PART_OF_DAY_RANGES[window.part_of_day]
    else:
        start_t, end_t = FULL_DAY_RANGE

    start = datetime.combine(result_date, start_t, tzinfo=TAIWAN_TZ)
    end = datetime.combine(result_date, end_t, tzinfo=TAIWAN_TZ)
    return ResolvedWindow(date=result_date, start=start, end=end), ambiguities
