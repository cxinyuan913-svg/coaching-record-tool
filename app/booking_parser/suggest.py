"""找空檔排班主流程（見 spec/scheduling-agent.md）：讀一筆已解析的約課紀錄
→ 決定時長、相關場館 → 撈占用課程與車程 → slot_finder 找候選 → 固定範本
組訊息。整個流程不呼叫 LLM。

學生/地區比對結果 Phase 1 沒有存進資料庫，這裡用 parsed_json 裡的原始字詞
重新比對一次：比對完全在本地做、成本很低，也能反映解析之後才新增的別名。
"""
import json
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.booking_parser.matcher import match_area, match_student
from app.booking_parser.resolver import FULL_DAY_RANGE, ResolvedWindow
from app.booking_parser.schemas import ParsedBookingRequest
from app.booking_parser.slot_finder import BusySlot, TimeWindow, find_slots, make_travel_lookup

DEFAULT_DURATION_MINUTES = 60

# 占用時段的課程狀態；請假（leave）跟取消都視為時段已釋放
OCCUPYING_STATUSES = (models.LessonStatus.SCHEDULED, models.LessonStatus.COMPLETED)

WEEKDAY_ZH = "一二三四五六日"

NO_CANDIDATE_MESSAGE = "這段時間目前排不進去，要不要換個日期？"


class SuggestNotFound(LookupError):
    pass


class SuggestUnavailable(ValueError):
    """這筆紀錄沒有可用的日期時段（不是約課、或解析失敗），無從找空檔。"""


class SuggestRequest(BaseModel):
    """全部選填，用來覆蓋解析結果（例如模糊比對要人工選學生、地區比對不到）。"""

    duration_minutes: int | None = Field(None, ge=30, le=240)
    venue_ids: list[int] | None = None
    student_id: int | None = None


class CandidateOut(BaseModel):
    date: date
    start: datetime
    end: datetime
    venue_id: int
    venue_name: str
    cross_venue: bool
    anchor_lesson_id: int


class BusyOut(BaseModel):
    venue_id: int
    venue_name: str
    start: datetime
    end: datetime


class DedicatedOut(BaseModel):
    date: date
    other_busy: list[BusyOut]  # 只給教練參考，不會放進給學生的訊息


class SuggestResult(BaseModel):
    booking_request_id: int
    duration_minutes: int
    duration_source: str  # "request" | "message" | "student_last_lesson" | "default"
    student_id: int | None
    venue_ids: list[int]
    anchored_candidates: list[CandidateOut]
    dedicated_dates: list[DedicatedOut]
    message: str
    notes: list[str]  # 給教練看的補充說明（例如地區比對不到、改用全部場館）


def _fmt_day(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAY_ZH[d.weekday()]})"


def _fmt_hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def build_message(
    anchored: list[CandidateOut], dedicated: list[DedicatedOut], windows: list[TimeWindow]
) -> str:
    """固定範本組訊息。跨館候選不寫錨點是哪堂課，不透露其他學生的資訊。"""
    if not anchored and not dedicated:
        return NO_CANDIDATE_MESSAGE

    sections: list[str] = []
    if anchored:
        lines = ["貼靠候選（交通最省）："]
        for c in anchored:
            reason = "同日前後有其他課程" if c.cross_venue else "緊接既有課程"
            lines.append(f"・{_fmt_day(c.date)} {_fmt_hm(c.start)}-{_fmt_hm(c.end)}，{c.venue_name}（{reason}）")
        sections.append("\n".join(lines))
    if dedicated:
        lines = ["專程候選（需要專程前往）："]
        for d in dedicated:
            lines.append(f"・{_fmt_day(d.date)} {_day_range_text(d.date, windows)}，需自行決定時段")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _day_range_text(day: date, windows: list[TimeWindow]) -> str:
    """學生沒指定時段（整天）就寫「全天可談」，有指定就寫出時段範圍。"""
    day_windows = [w for w in windows if w.start.date() == day]
    if any((w.start.time(), w.end.time()) == FULL_DAY_RANGE for w in day_windows):
        return "全天可談"
    ranges = "、".join(f"{_fmt_hm(w.start)}-{_fmt_hm(w.end)}" for w in sorted(day_windows, key=lambda w: w.start))
    return f"{ranges} 之間可談"


def _to_local_naive(w: ResolvedWindow) -> TimeWindow:
    """resolver 產生的時段帶台灣時區，課程資料表存的是沒有時區的台灣當地
    時間，統一去掉時區再比較，避免 aware/naive 混用直接丟例外。"""
    return TimeWindow(start=w.start.replace(tzinfo=None), end=w.end.replace(tzinfo=None))


def _lesson_span(lesson: models.Lesson) -> tuple[datetime, datetime]:
    start = datetime.combine(lesson.date, lesson.start_time)
    return start, start + timedelta(minutes=lesson.duration)


def suggest_slots(db: Session, booking_request_id: int, req: SuggestRequest, now: datetime) -> SuggestResult:
    """now 是台灣當地時間、不帶時區。"""
    record = db.get(models.BookingRequest, booking_request_id)
    if record is None:
        raise SuggestNotFound("約課紀錄不存在")

    resolved = [ResolvedWindow.model_validate(w) for w in json.loads(record.resolved_json or "[]")]
    if not resolved:
        raise SuggestUnavailable("這筆紀錄沒有可用的日期時段（不是約新課，或解析失敗），無法找空檔")
    windows = [_to_local_naive(w) for w in resolved]

    try:
        parsed = ParsedBookingRequest.model_validate(json.loads(record.parsed_json or "null"))
    except ValueError:
        parsed = None
    notes: list[str] = []

    # 學生：手動指定 > 精確/別名比對到的（模糊比對不自動選）
    student_id = req.student_id
    if student_id is None and parsed is not None and parsed.student_name:
        student_id = match_student(db, parsed.student_name).matched_student_id
        if student_id is None:
            notes.append(f"學生「{parsed.student_name}」沒有確定比對到，時長不會參考他過去的課")

    # 時長：手動指定 > 訊息有講 > 該學生最近一堂課 > 預設
    if req.duration_minutes is not None:
        duration, duration_source = req.duration_minutes, "request"
    elif parsed is not None and parsed.duration_minutes is not None:
        duration, duration_source = parsed.duration_minutes, "message"
    else:
        last = None
        if student_id is not None:
            last = (
                db.query(models.Lesson)
                .filter(
                    models.Lesson.student_id == student_id,
                    models.Lesson.status != models.LessonStatus.CANCELLED,
                )
                .order_by(models.Lesson.date.desc(), models.Lesson.start_time.desc())
                .first()
            )
        if last is not None:
            duration, duration_source = last.duration, "student_last_lesson"
        else:
            duration, duration_source = DEFAULT_DURATION_MINUTES, "default"

    # 場館：手動指定 > 地區比對到的 > 全部場館
    venues = {v.id: v for v in db.query(models.Venue)}
    if req.venue_ids:
        unknown = set(req.venue_ids) - venues.keys()
        if unknown:
            raise SuggestUnavailable(f"場地不存在：{sorted(unknown)}")
        venue_ids = set(req.venue_ids)
    else:
        matched: list[int] = []
        if parsed is not None and parsed.area:
            matched = match_area(db, parsed.area).matched_venue_ids
            if not matched:
                notes.append(f"地區「{parsed.area}」沒有對到任何場館，改用全部場館找空檔")
        venue_ids = set(matched) if matched else set(venues)

    days = sorted({w.start.date() for w in windows})
    lessons = (
        db.query(models.Lesson)
        .filter(models.Lesson.date.in_(days), models.Lesson.status.in_(OCCUPYING_STATUSES))
        .all()
    )
    busy = [
        BusySlot(lesson_id=l.id, venue_id=l.venue_id, start=s, end=e)
        for l in lessons
        for s, e in [_lesson_span(l)]
    ]
    pairs = {(t.venue_a_id, t.venue_b_id): t.travel_minutes for t in db.query(models.VenueTravelTime)}

    result = find_slots(
        busy=busy,
        windows=windows,
        venue_ids=venue_ids,
        duration_minutes=duration,
        travel=make_travel_lookup(pairs),
        now=now,
    )

    anchored = [
        CandidateOut(**c.model_dump(), venue_name=venues[c.venue_id].name) for c in result.anchored
    ]
    dedicated = [
        DedicatedOut(
            date=d.date,
            other_busy=[
                BusyOut(venue_id=b.venue_id, venue_name=venues[b.venue_id].name, start=b.start, end=b.end)
                for b in d.other_busy
            ],
        )
        for d in result.dedicated
    ]

    return SuggestResult(
        booking_request_id=record.id,
        duration_minutes=duration,
        duration_source=duration_source,
        student_id=student_id,
        venue_ids=sorted(venue_ids),
        anchored_candidates=anchored,
        dedicated_dates=dedicated,
        message=build_message(anchored, dedicated, windows),
        notes=notes,
    )
