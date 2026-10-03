"""固定時段排課：找「每週同一天、同一個時段、同一個場館」連續 N 週都能上的課
（見 spec/scheduling-agent.md「固定時段排課」）。

情境：新學生每週六都可以，要排連續 8 週、每次一小時。其他學生的週六課不是
固定的，每週的空檔都不一樣，一週一週比對很難找到最適合的固定時段。

做法：把每個「場館 × 整點開始時間」當候選，逐週用跟找空檔同一套規則（不撞課、
前後趕得到、算車程）檢查；某週不行就順延，往後補一週，最多順延
MAX_POSTPONE 週，湊不滿 N 堂就不列。排序：順延越少越好 → 同館接課的週數越多
越好 → 當天本來就在這個館的週數越多越好 → 時間早的優先。

純函式，不碰資料庫；撈資料跟組訊息是 slot_search.py 的工作。
"""
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel

from app.booking_parser.slot_finder import (
    WORK_END,
    WORK_START,
    BusySlot,
    TimeWindow,
    TravelLookup,
    _is_candidate,
)

# 某週不行時最多往後順延幾週來湊滿堂數
MAX_POSTPONE = 2

MAX_OPTIONS = 10

# 教練要求開始時間只用整點
STEP = timedelta(hours=1)


class SkippedWeek(BaseModel):
    date: date
    reason: str  # 只給教練看，例如「撞到 15:00-16:00 快羽會館的課」


class RecurringOption(BaseModel):
    venue_id: int
    start_time: time
    end_time: time
    dates: list[date]  # 實際上課的 N 個日期（已順延）
    skipped: list[SkippedWeek]  # 被跳過的週
    adjacent_weeks: int  # 緊接在同館既有課程前後的週數（最省交通）
    same_venue_weeks: int  # 當天本來就有課在這個館的週數（不用專程跑）


def weekly_dates(first: date, count: int) -> list[date]:
    return [first + timedelta(weeks=i) for i in range(count)]


def _explain(
    start: datetime,
    end: datetime,
    venue_id: int,
    busy: list[BusySlot],
    travel: TravelLookup,
    venue_names: dict[int, str],
    now: datetime,
) -> str:
    """這一週為什麼不行，給教練看的說明。判斷順序跟 _is_reachable 一致。"""
    if start < now:
        return "時間已經過了"
    for slot in busy:
        if slot.start < end and start < slot.end:
            return f"撞到 {slot.start:%H:%M}-{slot.end:%H:%M} {venue_names.get(slot.venue_id, '')}的課"
    before = [s for s in busy if s.end <= start]
    after = [s for s in busy if s.start >= end]
    if before:
        prev = max(before, key=lambda s: s.end)
        minutes = travel(prev.venue_id, venue_id)
        if minutes is None or prev.end + timedelta(minutes=minutes) > start:
            return f"前一堂 {prev.end:%H:%M} 在{venue_names.get(prev.venue_id, '')}下課，趕不過來"
    if after:
        nxt = min(after, key=lambda s: s.start)
        minutes = travel(venue_id, nxt.venue_id)
        if minutes is None or end + timedelta(minutes=minutes) > nxt.start:
            return f"趕不上 {nxt.start:%H:%M} 在{venue_names.get(nxt.venue_id, '')}的下一堂"
    return "不在可上課時段內"


def find_recurring(
    *,
    busy: list[BusySlot],
    first_date: date,
    weeks: int,
    time_from: time,
    time_to: time,
    venue_ids: set[int],
    duration_minutes: int,
    travel: TravelLookup,
    now: datetime,
    venue_names: dict[int, str] | None = None,
) -> list[RecurringOption]:
    """busy 要包含 first_date 起 weeks + MAX_POSTPONE 週內、這些日期「所有場館」的占用課程。"""
    venue_names = venue_names or {}
    duration = timedelta(minutes=duration_minutes)
    candidate_dates = weekly_dates(first_date, weeks + MAX_POSTPONE)
    busy_by_date: dict[date, list[BusySlot]] = {d: [] for d in candidate_dates}
    for slot in busy:
        if slot.start.date() in busy_by_date:
            busy_by_date[slot.start.date()].append(slot)

    # 開始時間：整點，落在學生時段內，整堂在工作時段內
    starts: list[time] = []
    t = datetime.combine(first_date, max(time_from, WORK_START))
    if t.minute or t.second:
        t = t.replace(minute=0, second=0) + STEP
    day_end = datetime.combine(first_date, WORK_END)
    while t.time() < time_to and t + duration <= day_end:
        starts.append(t.time())
        t += STEP

    options: list[RecurringOption] = []
    for venue_id in sorted(venue_ids):
        for start_t in starts:
            dates: list[date] = []
            skipped: list[SkippedWeek] = []
            adjacent = same_venue = 0
            for d in candidate_dates:
                if len(dates) == weeks:
                    break
                start = datetime.combine(d, start_t)
                end = start + duration
                window = [TimeWindow(start=datetime.combine(d, time_from), end=datetime.combine(d, time_to))]
                day_busy = busy_by_date[d]
                if _is_candidate(start, end, venue_id, window, day_busy, travel, now):
                    dates.append(d)
                    here = [s for s in day_busy if s.venue_id == venue_id]
                    same_venue += bool(here)
                    adjacent += any(s.end == start or s.start == end for s in here)
                else:
                    skipped.append(
                        SkippedWeek(date=d, reason=_explain(start, end, venue_id, day_busy, travel, venue_names, now))
                    )
            if len(dates) < weeks:
                continue
            options.append(
                RecurringOption(
                    venue_id=venue_id,
                    start_time=start_t,
                    end_time=(datetime.combine(first_date, start_t) + duration).time(),
                    dates=dates,
                    skipped=skipped,
                    adjacent_weeks=adjacent,
                    same_venue_weeks=same_venue,
                )
            )

    options.sort(key=lambda o: (len(o.skipped), -o.adjacent_weeks, -o.same_venue_weeks, o.start_time, o.venue_id))
    return options[:MAX_OPTIONS]


# ---- 指定時段逐週排排看 ----
#
# 教練先指定「每週六 10:00、快羽」，系統逐週檢查並提示：
# - 撞課／趕不到：列出當天同一個館其他可行的時段，最方便的排前面（教練決定只在
#   同一個館換時段，不換館）。
# - 有空但當天前後 2 小時內有課可以接：提示改成接課比較方便（例如 8–9 有課，
#   10–11 雖然空著，改 9–10 就能接在一起）。
#
# 接課的候選跟著既有課程的時間走（13:30 下課就從 13:30 開始），其他空檔只用整點。

SUGGEST_WITHIN = timedelta(hours=2)
MAX_ALTERNATIVES = 4


class SlotChoice(BaseModel):
    start_time: time
    end_time: time
    adjacent: bool  # 緊接同館既有課程前後
    note: str  # 給教練看的說明，例如「接在 08:00-09:00 那堂後面」


class WeekPlan(BaseModel):
    date: date
    preferred_ok: bool
    preferred_adjacent: bool
    preferred_reason: str | None  # 不行的原因（只給教練看）
    suggestion: SlotChoice | None  # 指定時段可以，但改這個能接課比較方便
    alternatives: list[SlotChoice]  # 指定時段不行時，當天同館其他可行時段
    day_busy: list[BusySlot]  # 當天已占用的時段（不限場館），給教練參考


def _adjacent_note(start: datetime, end: datetime, here: list[BusySlot]) -> str:
    for s in here:
        if s.end == start:
            return f"接在 {s.start:%H:%M}-{s.end:%H:%M} 那堂後面"
        if s.start == end:
            return f"接在 {s.start:%H:%M}-{s.end:%H:%M} 那堂前面"
    return ""


def plan_weeks(
    *,
    busy: list[BusySlot],
    first_date: date,
    weeks: int,
    preferred_start: time,
    venue_id: int,
    time_from: time,
    time_to: time,
    duration_minutes: int,
    travel: TravelLookup,
    now: datetime,
    venue_names: dict[int, str] | None = None,
) -> list[WeekPlan]:
    """回傳 weeks + MAX_POSTPONE 週的逐週狀況，多出來的週給「這週跳過、往後順延」用。"""
    venue_names = venue_names or {}
    duration = timedelta(minutes=duration_minutes)
    plans: list[WeekPlan] = []
    for d in weekly_dates(first_date, weeks + MAX_POSTPONE):
        day_busy = sorted((s for s in busy if s.start.date() == d), key=lambda s: s.start)
        here = [s for s in day_busy if s.venue_id == venue_id]
        window = [TimeWindow(start=datetime.combine(d, time_from), end=datetime.combine(d, time_to))]
        pref_start = datetime.combine(d, preferred_start)

        def ok(start: datetime) -> bool:
            return _is_candidate(start, start + duration, venue_id, window, day_busy, travel, now)

        def choice(start: datetime) -> SlotChoice:
            end = start + duration
            note = _adjacent_note(start, end, here)
            return SlotChoice(start_time=start.time(), end_time=end.time(), adjacent=bool(note), note=note or "空檔")

        # 同館接課的候選：每堂既有課程的前後
        adjacent: dict[datetime, SlotChoice] = {}
        for s in here:
            for start in (s.end, s.start - duration):
                if start.date() == d and ok(start):
                    adjacent.setdefault(start, choice(start))

        preferred_ok = ok(pref_start)
        preferred_adjacent = preferred_ok and bool(_adjacent_note(pref_start, pref_start + duration, here))

        def distance(c: SlotChoice) -> timedelta:
            return abs(datetime.combine(d, c.start_time) - pref_start)

        suggestion = None
        alternatives: list[SlotChoice] = []
        reason = None
        if preferred_ok:
            if not preferred_adjacent:
                near = [c for start, c in adjacent.items() if start != pref_start and distance(c) <= SUGGEST_WITHIN]
                if near:
                    suggestion = min(near, key=lambda c: (distance(c), c.start_time))
        else:
            reason = _explain(pref_start, pref_start + duration, venue_id, day_busy, travel, venue_names, now)
            free: list[SlotChoice] = []
            t = datetime.combine(d, max(time_from, WORK_START))
            if t.minute or t.second:
                t = t.replace(minute=0, second=0) + STEP
            while t.time() < time_to and t + duration <= datetime.combine(d, WORK_END):
                if t not in adjacent and ok(t):
                    free.append(choice(t))
                t += STEP
            ranked_adjacent = sorted(adjacent.values(), key=lambda c: (distance(c), c.start_time))
            ranked_free = sorted(free, key=lambda c: (distance(c), c.start_time))
            alternatives = (ranked_adjacent + ranked_free)[:MAX_ALTERNATIVES]

        plans.append(
            WeekPlan(
                date=d,
                preferred_ok=preferred_ok,
                preferred_adjacent=preferred_adjacent,
                preferred_reason=reason,
                suggestion=suggestion,
                alternatives=alternatives,
                day_busy=day_busy,
            )
        )
    return plans
