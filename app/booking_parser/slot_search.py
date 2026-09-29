"""找空檔主流程（見 spec/scheduling-agent.md）：教練自己選日期範圍、時段、
場館、時長 → 撈占用課程與車程 → slot_finder 找候選 → 固定範本組出給學生的
訊息。整個流程不呼叫 LLM。
"""
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app import models
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
    cross_venue: bool
    anchor_lesson_id: int


class SpanOut(BaseModel):
    start: datetime
    end: datetime


class BusyOut(BaseModel):
    venue_id: int
    venue_name: str
    start: datetime
    end: datetime


class DedicatedOut(BaseModel):
    date: date
    spans: list[SpanOut]
    other_busy: list[BusyOut]  # 只給教練參考，不會放進給學生的訊息


class SlotSearchResult(BaseModel):
    anchored_candidates: list[CandidateOut]
    dedicated_dates: list[DedicatedOut]
    message: str


def _fmt_day(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAY_ZH[d.weekday()]})"


def _fmt_hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def build_message(anchored: list[CandidateOut], dedicated: list[DedicatedOut]) -> str:
    """固定範本組出直接給學生看的訊息，不出現「貼靠」「專程」這類內部用語，
    也不寫是接在哪堂課前後，不透露其他學生的資訊。"""
    if not anchored and not dedicated:
        return NO_CANDIDATE_MESSAGE

    sections: list[str] = []
    if anchored:
        lines = ["我這幾個時段可以："]
        for c in anchored:
            lines.append(f"・{_fmt_day(c.date)} {_fmt_hm(c.start)}-{_fmt_hm(c.end)} {c.venue_name}")
        sections.append("\n".join(lines))
    if dedicated:
        lines = ["這幾天比較彈性，時間可以再討論："]
        for d in dedicated:
            ranges = "、".join(f"{_fmt_hm(sp.start)}-{_fmt_hm(sp.end)}" for sp in d.spans)
            lines.append(f"・{_fmt_day(d.date)} {ranges}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def area_presets(db: Session) -> dict[str, list[int]]:
    """{"台北": [場館 id...], "新竹": [...]}，給頁面的快選按鈕用。"""
    presets: dict[str, list[int]] = {}
    for area in AREA_PRESETS:
        rows = db.query(models.VenueArea.venue_id).filter(models.VenueArea.area == area)
        presets[area] = sorted({venue_id for (venue_id,) in rows})
    return presets


def search_slots(db: Session, req: SlotSearchRequest, now: datetime) -> SlotSearchResult:
    """now 是台灣當地時間、不帶時區（跟課程資料表的存法一致）。"""
    venues = {v.id: v for v in db.query(models.Venue)}
    unknown = set(req.venue_ids) - venues.keys()
    if unknown:
        raise SlotSearchNotAllowed(f"場地不存在：{sorted(unknown)}")

    days = [req.date_from + timedelta(days=i) for i in range((req.date_to - req.date_from).days + 1)]
    windows = [
        TimeWindow(start=datetime.combine(d, req.time_from), end=datetime.combine(d, req.time_to))
        for d in days
    ]

    # 所有場館的課都要撈：教練人只有一個，別館的課也會卡住時間
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
    pairs = {(t.venue_a_id, t.venue_b_id): t.travel_minutes for t in db.query(models.VenueTravelTime)}

    result = find_slots(
        busy=busy,
        windows=windows,
        venue_ids=set(req.venue_ids),
        duration_minutes=req.duration_minutes,
        travel=make_travel_lookup(pairs),
        now=now,
    )

    anchored = [
        CandidateOut(**c.model_dump(), venue_name=venues[c.venue_id].name) for c in result.anchored
    ]
    dedicated = [
        DedicatedOut(
            date=d.date,
            spans=[SpanOut(start=sp.start, end=sp.end) for sp in d.spans],
            other_busy=[
                BusyOut(venue_id=b.venue_id, venue_name=venues[b.venue_id].name, start=b.start, end=b.end)
                for b in d.other_busy
            ],
        )
        for d in result.dedicated
    ]
    return SlotSearchResult(
        anchored_candidates=anchored,
        dedicated_dates=dedicated,
        message=build_message(anchored, dedicated),
    )
