"""找空檔的核心演算法（見 spec/scheduling-agent.md「候選時段演算法」）。

這裡刻意寫成純函式：輸入是已經撈好的占用課程、學生時段、車程表，輸出是
兩組候選，完全不碰資料庫也不呼叫 LLM，所以結果可預期、測試不用準備資料庫。
撈資料跟組訊息文字是 slot_search.py 的工作。

- 第一組「同館接課」：緊接在既有課程前後、同一個場館的具體時段，交通最省。
- 第二組「大空檔」：每個場館各自算出趕得到的連續空檔（至少 2 小時），時段
  相同的場館合併成一筆。

車程的用法：教練同一時間只有一個人，候選時段前後最接近的那兩堂課（不限
場館）決定他來不來得及到場、來不來得及離開。只看「最接近的前一堂 / 後一堂」
就夠了，因為更早的課程要趕過來，一定得先經過最接近的那一堂。
"""
from collections.abc import Callable
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel

# 工作時段：候選不得早於 WORK_START 開始、不得晚於 WORK_END 結束
WORK_START = time(8, 0)
WORK_END = time(22, 30)

MAX_ANCHORED_CANDIDATES = 5

# 大空檔至少要多長才列出（從最早開始到最晚下課）
MIN_OPEN_BLOCK = timedelta(hours=2)

# 大空檔的掃描間隔：開始時間只考慮整點與半點
OPEN_BLOCK_STEP = timedelta(minutes=30)

# travel(a, b) → 分鐘；同場館回 0；查不到回 None（代表不可銜接）
TravelLookup = Callable[[int, int], int | None]


class BusySlot(BaseModel):
    """一堂占用時段的既有課程（status 為 scheduled / completed）。"""

    lesson_id: int
    venue_id: int
    start: datetime
    end: datetime


class TimeWindow(BaseModel):
    start: datetime
    end: datetime


class AnchoredCandidate(BaseModel):
    """同館接課：緊接在某一堂既有課程前後、同一個場館的具體時段。"""

    date: date
    start: datetime
    end: datetime
    venue_id: int
    anchor_lesson_id: int


class OpenBlock(BaseModel):
    """大空檔：這些場館都能在 start 之後開始上課、最晚 end 下課的連續時段。"""

    date: date
    start: datetime
    end: datetime
    venue_ids: list[int]
    other_busy: list[BusySlot]  # 當天已占用的時段（不限場館），給教練參考


class SlotSearchResult(BaseModel):
    anchored: list[AnchoredCandidate]
    open_blocks: list[OpenBlock]


def make_travel_lookup(pairs: dict[tuple[int, int], int]) -> TravelLookup:
    """pairs 的 key 是 (較小 id, 較大 id)，跟資料表存法一致。"""

    def travel(a: int, b: int) -> int | None:
        if a == b:
            return 0
        return pairs.get((min(a, b), max(a, b)))

    return travel


def _within_work_hours(start: datetime, end: datetime) -> bool:
    day = start.date()
    return (
        end.date() == day
        and start >= datetime.combine(day, WORK_START)
        and end <= datetime.combine(day, WORK_END)
    )


def _starts_in_any_window(start: datetime, windows: list[TimeWindow]) -> bool:
    """只要求「開始時間」落在學生時段內，不要求整堂課都在裡面：例如晚上
    18:00-22:00，21:30 開始、22:30 下課的課也算。結束時間另外由工作時段把關。"""
    return any(w.start <= start < w.end for w in windows)


def _is_reachable(
    start: datetime, end: datetime, venue_id: int, busy: list[BusySlot], travel: TravelLookup
) -> bool:
    """候選跟任何既有課程不重疊，而且來得及從前一堂趕到、來得及趕去下一堂。"""
    prev: BusySlot | None = None
    nxt: BusySlot | None = None
    for slot in busy:
        if slot.start < end and start < slot.end:
            return False  # 時間直接重疊
        if slot.end <= start and slot.start.date() == start.date():
            if prev is None or slot.end > prev.end:
                prev = slot
        if slot.start >= end and slot.start.date() == start.date():
            if nxt is None or slot.start < nxt.start:
                nxt = slot

    if prev is not None:
        minutes = travel(prev.venue_id, venue_id)
        if minutes is None or prev.end + timedelta(minutes=minutes) > start:
            return False
    if nxt is not None:
        minutes = travel(venue_id, nxt.venue_id)
        if minutes is None or end + timedelta(minutes=minutes) > nxt.start:
            return False
    return True


def _is_candidate(
    start: datetime,
    end: datetime,
    venue_id: int,
    windows: list[TimeWindow],
    busy: list[BusySlot],
    travel: TravelLookup,
    now: datetime,
) -> bool:
    return (
        start >= now
        and _within_work_hours(start, end)
        and _starts_in_any_window(start, windows)
        and _is_reachable(start, end, venue_id, busy, travel)
    )


def _open_spans(
    day: date,
    windows: list[TimeWindow],
    busy: list[BusySlot],
    venue_id: int,
    duration: timedelta,
    travel: TravelLookup,
    now: datetime,
) -> list[tuple[datetime, datetime]]:
    """某場館當天趕得到的連續時段 (最早開始, 最晚下課)。以半小時為單位掃描
    開始時間，可行的開始時間連在一起就合併成一段。"""
    spans: list[tuple[datetime, datetime]] = []
    last_ok: datetime | None = None
    s = datetime.combine(day, WORK_START)
    last_start = datetime.combine(day, WORK_END) - duration
    while s <= last_start:
        if _is_candidate(s, s + duration, venue_id, windows, busy, travel, now):
            if last_ok is not None and s - OPEN_BLOCK_STEP == last_ok:
                spans[-1] = (spans[-1][0], s + duration)
            else:
                spans.append((s, s + duration))
            last_ok = s
        s += OPEN_BLOCK_STEP
    return spans


def find_slots(
    *,
    busy: list[BusySlot],
    windows: list[TimeWindow],
    venue_ids: set[int],
    duration_minutes: int,
    travel: TravelLookup,
    now: datetime,
) -> SlotSearchResult:
    """busy 要包含學生時段涵蓋日期內「所有場館」的占用課程，不只相關場館。"""
    duration = timedelta(minutes=duration_minutes)
    days = sorted({w.start.date() for w in windows})

    # 第一組：同館接課，每堂既有課程往前、往後各長出一個候選
    found: dict[tuple[datetime, int], AnchoredCandidate] = {}
    for anchor in busy:
        if anchor.venue_id not in venue_ids or anchor.start.date() not in days:
            continue
        for start in (anchor.end, anchor.start - duration):
            end = start + duration
            if not _is_candidate(start, end, anchor.venue_id, windows, busy, travel, now):
                continue
            # 同一個時段可能被前後兩堂課同時長出來，只留一筆
            found.setdefault(
                (start, anchor.venue_id),
                AnchoredCandidate(
                    date=start.date(),
                    start=start,
                    end=end,
                    venue_id=anchor.venue_id,
                    anchor_lesson_id=anchor.lesson_id,
                ),
            )
    anchored = sorted(found.values(), key=lambda c: (c.start, c.venue_id))[:MAX_ANCHORED_CANDIDATES]

    # 第二組：大空檔，每個場館各自算，時段完全相同的場館合併成一筆
    open_blocks: list[OpenBlock] = []
    for day in days:
        today_busy = sorted((s for s in busy if s.start.date() == day), key=lambda s: s.start)
        day_windows = [w for w in windows if w.start.date() == day]
        grouped: dict[tuple[datetime, datetime], list[int]] = {}
        for venue_id in sorted(venue_ids):
            for start, end in _open_spans(day, day_windows, today_busy, venue_id, duration, travel, now):
                if end - start >= MIN_OPEN_BLOCK:
                    grouped.setdefault((start, end), []).append(venue_id)
        for (start, end), ids in sorted(grouped.items()):
            open_blocks.append(
                OpenBlock(date=day, start=start, end=end, venue_ids=ids, other_busy=today_busy)
            )

    return SlotSearchResult(anchored=anchored, open_blocks=open_blocks)
