"""找空檔主流程（見 spec/scheduling-agent.md）：教練自己選日期範圍、時段、
場館、時長 → 撈占用課程與車程 → slot_finder 找候選 → 固定範本組出給學生的
訊息。整個流程不呼叫 LLM。
"""
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app import models
from app.booking_parser.recurring_finder import MAX_POSTPONE, find_recurring, plan_weeks, weekly_dates
from app.booking_parser.slot_finder import (
    WORK_END,
    WORK_START,
    BusySlot,
    TimeWindow,
    find_slots,
    make_travel_lookup,
)

# 占用時段的課程狀態；請假（leave）跟取消都視為時段已釋放
OCCUPYING_STATUSES = (models.LessonStatus.SCHEDULED, models.LessonStatus.COMPLETED)

# 一次最多查幾天，避免誤選一整年、訊息長到不能用
MAX_RANGE_DAYS = 31

# 頁面上「台北場館」「新竹場館」快選按鈕用的地區名稱（對應 venue_areas 表）
AREA_PRESETS = ("台北", "新竹")

WEEKDAY_ZH = "一二三四五六日"

NO_CANDIDATE_MESSAGE = "這段時間目前排不進去，要不要換個日期？"


class SlotSearchNotAllowed(ValueError):
    pass


class SlotSearchRequest(BaseModel):
    date_from: date
    date_to: date
    time_from: time = WORK_START  # 學生可以的開始時間範圍，預設整天
    time_to: time = WORK_END
    venue_ids: list[int] = Field(min_length=1)
    duration_minutes: int = Field(60, ge=30, le=240)

    @model_validator(mode="after")
    def check_ranges(self):
        if self.date_to < self.date_from:
            raise ValueError("結束日期不能早於開始日期")
        if (self.date_to - self.date_from).days + 1 > MAX_RANGE_DAYS:
            raise ValueError(f"一次最多查 {MAX_RANGE_DAYS} 天")
        if self.time_to <= self.time_from:
            raise ValueError("結束時間要晚於開始時間")
        return self


class CandidateOut(BaseModel):
    date: date
    start: datetime
    end: datetime
    venue_id: int
    venue_name: str
    anchor_lesson_id: int


class BusyOut(BaseModel):
    venue_id: int
    venue_name: str
    start: datetime
    end: datetime


class OpenBlockOut(BaseModel):
    date: date
    start: datetime
    end: datetime
    venue_ids: list[int]
    venue_names: list[str]
    other_busy: list[BusyOut]  # 只給教練參考，不會放進給學生的訊息


class SlotSearchResult(BaseModel):
    anchored_candidates: list[CandidateOut]
    open_blocks: list[OpenBlockOut]
    message: str


def _fmt_day(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAY_ZH[d.weekday()]})"


def _fmt_hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def build_message(anchored: list[CandidateOut], open_blocks: list[OpenBlockOut]) -> str:
    """固定範本組出直接給學生看的訊息，不出現「接課」「空檔」這類內部用語，
    也不寫是接在哪堂課前後，不透露其他學生的資訊。"""
    if not anchored and not open_blocks:
        return NO_CANDIDATE_MESSAGE

    sections: list[str] = []
    if anchored:
        lines = ["我這幾個時段最方便："]
        for c in anchored:
            lines.append(f"・{_fmt_day(c.date)} {_fmt_hm(c.start)}-{_fmt_hm(c.end)} {c.venue_name}")
        sections.append("\n".join(lines))
    if open_blocks:
        lines = ["其他有空的時段（場館可以選）："]
        for b in open_blocks:
            venues = "、".join(b.venue_names)
            lines.append(f"・{_fmt_day(b.date)} {_fmt_hm(b.start)}-{_fmt_hm(b.end)} {venues}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def area_presets(db: Session) -> dict[str, list[int]]:
    """{"台北": [場館 id...], "新竹": [...]}，給頁面的快選按鈕用。"""
    presets: dict[str, list[int]] = {}
    for area in AREA_PRESETS:
        rows = db.query(models.VenueArea.venue_id).filter(models.VenueArea.area == area)
        presets[area] = sorted({venue_id for (venue_id,) in rows})
    return presets


def _load_venues(db: Session, venue_ids: list[int]) -> dict[int, models.Venue]:
    venues = {v.id: v for v in db.query(models.Venue)}
    unknown = set(venue_ids) - venues.keys()
    if unknown:
        raise SlotSearchNotAllowed(f"場地不存在：{sorted(unknown)}")
    return venues


def _load_busy(db: Session, days: list[date]) -> list[BusySlot]:
    """這些日期所有場館的占用課程：教練人只有一個，別館的課也會卡住時間。"""
    lessons = (
        db.query(models.Lesson)
        .filter(models.Lesson.date.in_(days), models.Lesson.status.in_(OCCUPYING_STATUSES))
        .all()
    )
    busy = []
    for lesson in lessons:
        start = datetime.combine(lesson.date, lesson.start_time)
        busy.append(
            BusySlot(
                lesson_id=lesson.id,
                venue_id=lesson.venue_id,
                start=start,
                end=start + timedelta(minutes=lesson.duration),
            )
        )
    return busy


def _load_travel(db: Session):
    pairs = {(t.venue_a_id, t.venue_b_id): t.travel_minutes for t in db.query(models.VenueTravelTime)}
    return make_travel_lookup(pairs)


def search_slots(db: Session, req: SlotSearchRequest, now: datetime) -> SlotSearchResult:
    """now 是台灣當地時間、不帶時區（跟課程資料表的存法一致）。"""
    venues = _load_venues(db, req.venue_ids)
    days = [req.date_from + timedelta(days=i) for i in range((req.date_to - req.date_from).days + 1)]
    windows = [
        TimeWindow(start=datetime.combine(d, req.time_from), end=datetime.combine(d, req.time_to))
        for d in days
    ]
    busy = _load_busy(db, days)

    result = find_slots(
        busy=busy,
        windows=windows,
        venue_ids=set(req.venue_ids),
        duration_minutes=req.duration_minutes,
        travel=_load_travel(db),
        now=now,
    )

    anchored = [
        CandidateOut(**c.model_dump(), venue_name=venues[c.venue_id].name) for c in result.anchored
    ]
    open_blocks = [
        OpenBlockOut(
            date=b.date,
            start=b.start,
            end=b.end,
            venue_ids=b.venue_ids,
            venue_names=[venues[v].name for v in b.venue_ids],
            other_busy=[
                BusyOut(venue_id=o.venue_id, venue_name=venues[o.venue_id].name, start=o.start, end=o.end)
                for o in b.other_busy
            ],
        )
        for b in result.open_blocks
    ]
    return SlotSearchResult(
        anchored_candidates=anchored,
        open_blocks=open_blocks,
        message=build_message(anchored, open_blocks),
    )


# ---- 固定時段排課（每週同一天、同一時段，連續 N 週）----

MAX_WEEKS = 20


class RecurringSearchRequest(BaseModel):
    weekday: int = Field(ge=0, le=6)  # 週一=0 … 週日=6（跟 Python date.weekday() 一致）
    date_from: date  # 從這天（含）之後的第一個指定星期開始
    weeks: int = Field(8, ge=1, le=MAX_WEEKS)
    time_from: time = WORK_START
    time_to: time = WORK_END
    venue_ids: list[int] = Field(min_length=1)
    duration_minutes: int = Field(60, ge=30, le=240)

    @model_validator(mode="after")
    def check_times(self):
        if self.time_to <= self.time_from:
            raise ValueError("結束時間要晚於開始時間")
        return self


class SkippedWeekOut(BaseModel):
    date: date
    reason: str  # 只給教練看


class RecurringOptionOut(BaseModel):
    """給學生的訊息由前端組（跟課程套組頁同一個格式），這裡只回結構化資料。"""

    venue_id: int
    venue_name: str
    start_time: time
    end_time: time
    dates: list[date]
    skipped: list[SkippedWeekOut]
    adjacent_weeks: int
    same_venue_weeks: int


class RecurringSearchResult(BaseModel):
    first_date: date
    weeks: int
    options: list[RecurringOptionOut]


def _first_date(req_date_from: date, weekday: int) -> date:
    return req_date_from + timedelta(days=(weekday - req_date_from.weekday()) % 7)


def search_recurring(db: Session, req: RecurringSearchRequest, now: datetime) -> RecurringSearchResult:
    venues = _load_venues(db, req.venue_ids)
    first_date = _first_date(req.date_from, req.weekday)
    days = weekly_dates(first_date, req.weeks + MAX_POSTPONE)

    options = find_recurring(
        busy=_load_busy(db, days),
        first_date=first_date,
        weeks=req.weeks,
        time_from=req.time_from,
        time_to=req.time_to,
        venue_ids=set(req.venue_ids),
        duration_minutes=req.duration_minutes,
        travel=_load_travel(db),
        now=now,
        venue_names={v_id: v.name for v_id, v in venues.items()},
    )
    out = [
        RecurringOptionOut(
            **o.model_dump(exclude={"skipped"}),
            skipped=[SkippedWeekOut(**sk.model_dump()) for sk in o.skipped],
            venue_name=venues[o.venue_id].name,
        )
        for o in options
    ]
    return RecurringSearchResult(first_date=first_date, weeks=req.weeks, options=out)


# ---- 指定時段逐週排排看 ----

class RecurringPlanRequest(BaseModel):
    weekday: int = Field(ge=0, le=6)
    date_from: date
    weeks: int = Field(8, ge=1, le=MAX_WEEKS)
    preferred_start: time  # 教練希望的開始時間，例如 10:00
    venue_id: int  # 只在同一個館換時段（教練決定）
    time_from: time = WORK_START  # 撞課時替代時段的範圍
    time_to: time = WORK_END
    duration_minutes: int = Field(60, ge=30, le=240)

    @model_validator(mode="after")
    def check_times(self):
        if self.time_to <= self.time_from:
            raise ValueError("結束時間要晚於開始時間")
        return self


class SlotChoiceOut(BaseModel):
    start_time: time
    end_time: time
    adjacent: bool
    note: str


class WeekPlanOut(BaseModel):
    date: date
    preferred_ok: bool
    preferred_adjacent: bool
    preferred_reason: str | None
    suggestion: SlotChoiceOut | None
    alternatives: list[SlotChoiceOut]
    day_busy: list[BusyOut]  # 只給教練參考


class RecurringPlanResult(BaseModel):
    first_date: date
    weeks: int  # 要排滿幾堂；week_plans 會多回 MAX_POSTPONE 週給順延用
    venue_id: int
    venue_name: str
    preferred_start: time
    preferred_end: time
    week_plans: list[WeekPlanOut]


def plan_recurring(db: Session, req: RecurringPlanRequest, now: datetime) -> RecurringPlanResult:
    venues = _load_venues(db, [req.venue_id])
    first_date = _first_date(req.date_from, req.weekday)
    days = weekly_dates(first_date, req.weeks + MAX_POSTPONE)
    plans = plan_weeks(
        busy=_load_busy(db, days),
        first_date=first_date,
        weeks=req.weeks,
        preferred_start=req.preferred_start,
        venue_id=req.venue_id,
        time_from=req.time_from,
        time_to=req.time_to,
        duration_minutes=req.duration_minutes,
        travel=_load_travel(db),
        now=now,
        venue_names={v_id: v.name for v_id, v in venues.items()},
    )
    week_plans = [
        WeekPlanOut(
            **p.model_dump(exclude={"day_busy", "suggestion", "alternatives"}),
            suggestion=SlotChoiceOut(**p.suggestion.model_dump()) if p.suggestion else None,
            alternatives=[SlotChoiceOut(**c.model_dump()) for c in p.alternatives],
            day_busy=[
                BusyOut(venue_id=b.venue_id, venue_name=venues[b.venue_id].name, start=b.start, end=b.end)
                for b in p.day_busy
            ],
        )
        for p in plans
    ]
    preferred_end = (datetime.combine(first_date, req.preferred_start) + timedelta(minutes=req.duration_minutes)).time()
    return RecurringPlanResult(
        first_date=first_date,
        weeks=req.weeks,
        venue_id=req.venue_id,
        venue_name=venues[req.venue_id].name,
        preferred_start=req.preferred_start,
        preferred_end=preferred_end,
        week_plans=week_plans,
    )
