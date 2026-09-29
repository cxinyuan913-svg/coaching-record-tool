"""找空檔排班的核心演算法（見 spec/scheduling-agent.md「候選時段演算法」）。

這裡刻意寫成純函式：輸入是已經撈好的占用課程、學生時段、車程表，輸出是
候選清單，完全不碰資料庫也不呼叫 LLM，所以結果可預期、測試不用準備資料庫。
撈資料跟組訊息文字是 suggest.py 的工作。

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

# 跨館候選所在場館當天至少要連續待這麼久，去回程才划算
MIN_CROSS_VENUE_BLOCK_MINUTES = 120

MAX_ANCHORED_CANDIDATES = 5

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
    """貼靠候選：緊貼某一堂既有課程的具體時段。"""

    date: date
    start: datetime
    end: datetime
    venue_id: int
    cross_venue: bool  # 候選場館跟錨點課程不同館
    anchor_lesson_id: int


class DedicatedDate(BaseModel):
    """專程候選：當天在相關場館沒有任何課程，只列日期，時段由教練自己決定。"""

    date: date
    other_busy: list[BusySlot]  # 當天在其他場館已占用的時段，給教練參考


class SlotSearchResult(BaseModel):
    anchored: list[AnchoredCandidate]
    dedicated: list[DedicatedDate]


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
    """只要求「開始時間」落在學生時段內，不要求整堂課都在裡面：學生說「七點」
    時 resolver 給的時段是 19:00-20:00，但兩小時的課 19:00-21:00 也是學生
    要的意思。結束時間另外由工作時段把關。"""
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


def _contiguous_block_minutes(start: datetime, end: datetime, venue_id: int, busy: list[BusySlot]) -> int:
    """候選本身加上同館首尾相接（間隔 0 分鐘）的既有課程，總共連續幾分鐘。
    其他候選不算進來：候選之間是互斥的選項，學生最後只會選一個。"""
    same_venue = [s for s in busy if s.venue_id == venue_id]
    block_start, block_end = start, end
    extended = True
    while extended:
        extended = False
        for s in same_venue:
            if s.end == block_start:
                block_start = s.start
                extended = True
            elif s.start == block_end:
                block_end = s.end
                extended = True
    return int((block_end - block_start).total_seconds() // 60)


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
    window_dates = {w.start.date() for w in windows}

    found: dict[tuple[date, datetime, datetime, int], AnchoredCandidate] = {}
    for anchor in busy:
        if anchor.start.date() not in window_dates:
            continue
        for venue_id in venue_ids:
            minutes = travel(anchor.venue_id, venue_id)
            if minutes is None:
                continue
            gap = timedelta(minutes=minutes)
            after_start = anchor.end + gap
            before_end = anchor.start - gap
            for start, end in ((after_start, after_start + duration), (before_end - duration, before_end)):
                if start < now:
                    continue
                if not _within_work_hours(start, end):
                    continue
                if not _starts_in_any_window(start, windows):
                    continue
                if not _is_reachable(start, end, venue_id, busy, travel):
                    continue
                cross = anchor.venue_id != venue_id
                if cross and _contiguous_block_minutes(start, end, venue_id, busy) < MIN_CROSS_VENUE_BLOCK_MINUTES:
                    continue

                key = (start.date(), start, end, venue_id)
                existing = found.get(key)
                # 同一個時段可能同時是同館貼靠又是跨館貼靠，保留同館的說法
                if existing is None or (existing.cross_venue and not cross):
                    found[key] = AnchoredCandidate(
                        date=start.date(),
                        start=start,
                        end=end,
                        venue_id=venue_id,
                        cross_venue=cross,
                        anchor_lesson_id=anchor.lesson_id,
                    )

    anchored = sorted(found.values(), key=lambda c: (c.cross_venue, c.start, c.venue_id))
    anchored = anchored[:MAX_ANCHORED_CANDIDATES]

    dedicated: list[DedicatedDate] = []
    for day in sorted(window_dates):
        if day < now.date():
            continue
        today_busy = sorted((s for s in busy if s.start.date() == day), key=lambda s: s.start)
        if any(s.venue_id in venue_ids for s in today_busy):
            continue
        dedicated.append(DedicatedDate(date=day, other_busy=today_busy))

    return SlotSearchResult(anchored=anchored, dedicated=dedicated)
