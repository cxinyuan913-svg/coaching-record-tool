"""找空檔演算法 slot_finder.find_slots 的單元測試（純函式，不用資料庫）。

場館設定：A=1、B=2 之間車程 20 分鐘；C=3 跟誰都沒設定車程（不可銜接）。
日期統一用 2026-10-06（週二），「現在」是 2026-10-01。
"""
from datetime import datetime

from app.booking_parser.slot_finder import BusySlot, TimeWindow, find_slots, make_travel_lookup

A, B, C = 1, 2, 3
TRAVEL = make_travel_lookup({(A, B): 20})
NOW = datetime(2026, 10, 1, 0, 0)
DAY = (2026, 10, 6)


def at(hh: int, mm: int = 0, day=DAY) -> datetime:
    return datetime(*day, hh, mm)


_next_id = iter(range(1, 1000))


def busy(venue: int, start: datetime, end: datetime) -> BusySlot:
    return BusySlot(lesson_id=next(_next_id), venue_id=venue, start=start, end=end)


WHOLE_DAY = [TimeWindow(start=at(8), end=at(22, 30))]


def run(busy_slots, venue_ids, duration=60, windows=WHOLE_DAY, now=NOW):
    return find_slots(
        busy=busy_slots, windows=windows, venue_ids=venue_ids,
        duration_minutes=duration, travel=TRAVEL, now=now,
    )


def spans(result):
    return [(c.start.strftime("%H:%M"), c.end.strftime("%H:%M"), c.venue_id, c.cross_venue) for c in result.anchored]


def test_same_venue_before_and_after():
    r = run([busy(A, at(18), at(19))], {A})
    assert spans(r) == [("17:00", "18:00", A, False), ("19:00", "20:00", A, False)]
    assert r.dedicated == []


def test_cross_venue_adds_travel_time():
    # A 館 10-11 下課，開車 20 分鐘到 B 館，兩小時的課 11:20 開始
    r = run([busy(A, at(10), at(11))], {B}, duration=120)
    assert spans(r) == [("11:20", "13:20", B, True)]


def test_cross_venue_under_120_minutes_rejected():
    anchor = busy(A, at(10), at(11))
    r = run([anchor], {B}, duration=60)
    assert r.anchored == []
    # B 館當天沒課 → 列為專程，附註當天 A 館已占用的時段
    assert [d.date for d in r.dedicated] == [at(0).date()]
    assert r.dedicated[0].other_busy == [anchor]


def test_same_slot_from_two_anchors_kept_once_as_same_venue():
    # 11:20-12:20 在 B 館：既是 A 館課程的跨館貼靠，也是 B 館 12:20 那堂的同館貼靠
    r = run([busy(A, at(10), at(11)), busy(B, at(12, 20), at(13, 20))], {B})
    assert ("11:20", "12:20", B, False) in spans(r)
    assert ("11:20", "12:20", B, True) not in spans(r)


def test_cannot_reach_next_lesson_at_other_venue():
    # A 館 19:00-20:00 下課要 20:20 才到得了 B 館，趕不上 B 館 20:10 的課
    r = run([busy(A, at(18), at(19)), busy(B, at(20, 10), at(21, 10))], {A})
    assert spans(r) == [("17:00", "18:00", A, False)]


def test_unknown_travel_time_blocks_connection():
    # C 館跟 A 館沒有車程資料 → 候選緊接在 C 館課程之前也視為不可銜接
    r = run([busy(A, at(18), at(19)), busy(C, at(20), at(21))], {A})
    assert spans(r) == [("17:00", "18:00", A, False)]
    # 目標場館是 C，錨點在 A → 查不到車程，根本不會長出候選
    r = run([busy(A, at(10), at(12))], {C}, duration=120)
    assert r.anchored == []


def test_work_hours_boundary():
    assert run([busy(A, at(21, 30), at(22, 30))], {A}).anchored[-1].end == at(21, 30)
    assert spans(run([busy(A, at(8, 30), at(9, 30))], {A})) == [("09:30", "10:30", A, False)]
    # 剛好 22:30 結束可以
    assert ("21:30", "22:30", A, False) in spans(run([busy(A, at(21), at(21, 30))], {A}))


def test_start_time_must_fall_in_student_window():
    evening = [TimeWindow(start=at(18), end=at(22))]
    r = run([busy(A, at(17), at(18))], {A}, windows=evening)
    assert spans(r) == [("18:00", "19:00", A, False)]
    # 學生說「七點」→ 19:00-20:00，兩小時的課 19:00-21:00 也算符合
    seven = [TimeWindow(start=at(19), end=at(20))]
    r = run([busy(A, at(17), at(19))], {A}, duration=120, windows=seven)
    assert spans(r) == [("19:00", "21:00", A, False)]


def test_candidates_in_the_past_excluded():
    r = run([busy(A, at(18), at(19))], {A}, now=at(18, 30))
    assert spans(r) == [("19:00", "20:00", A, False)]


def test_dedicated_only_on_days_without_lessons_in_area():
    day2 = (2026, 10, 7)
    windows = WHOLE_DAY + [TimeWindow(start=at(8, day=day2), end=at(22, 30, day=day2))]
    r = run([busy(A, at(18), at(19))], {A}, windows=windows)
    assert [d.date for d in r.dedicated] == [at(0, day=day2).date()]
    assert r.dedicated[0].other_busy == []


def test_sorted_same_venue_first_and_capped_at_five():
    lessons = [busy(A, at(h), at(h + 1)) for h in (9, 12, 15, 18)] + [busy(B, at(10, 20), at(11, 20))]
    r = run(lessons, {A, B}, duration=60)
    assert len(r.anchored) == 5
    assert all(not c.cross_venue for c in r.anchored)
    starts = [c.start for c in r.anchored]
    assert starts == sorted(starts)


def test_dedicated_when_student_window_free_even_if_day_has_other_lessons():
    # 真實案例：當天白天有課，學生要的晚上整段空著 → 要列專程，不能說排不進去
    morning = busy(A, at(10), at(12))
    afternoon = busy(B, at(13, 30), at(15, 30))
    evening = [TimeWindow(start=at(18), end=at(22))]
    r = run([morning, afternoon], {A, B}, windows=evening)
    assert r.anchored == []
    assert [d.date for d in r.dedicated] == [at(0).date()]
    assert r.dedicated[0].other_busy == [morning, afternoon]


def test_no_dedicated_when_day_has_anchored_candidate_or_no_free_gap():
    # 當天已經有貼靠候選 → 不重複列專程
    r = run([busy(A, at(18), at(19))], {A})
    assert r.anchored and r.dedicated == []
    # 學生時段被塞滿（別館的課也算）→ 沒有空檔，不列專程
    evening = [TimeWindow(start=at(18), end=at(22))]
    r = run([busy(C, at(17), at(22, 30))], {A}, windows=evening)
    assert r.anchored == [] and r.dedicated == []
    # 空檔不夠一整堂：20:00 以後才空，但兩小時的課會超過 22:30
    r = run([busy(C, at(17), at(21))], {A}, duration=120, windows=evening)
    assert r.dedicated == []


def dspans(result):
    return {
        d.date.isoformat(): [(sp.start.strftime("%H:%M"), sp.end.strftime("%H:%M")) for sp in d.spans]
        for d in result.dedicated
    }


def test_dedicated_day_fully_free_is_one_whole_day_span():
    r = run([], {A})
    assert dspans(r) == {"2026-10-06": [("08:00", "22:30")]}


def test_dedicated_spans_include_travel_from_other_area():
    # 真實案例 10/4：白天在新竹（這裡用 B，車程 77 分鐘）上課到 19:00，
    # 台北（A）只有 20:30 以後趕得到；14:00-16:00 的空檔來回車程不夠
    far = make_travel_lookup({(A, B): 77})
    busy_slots = [busy(B, at(8), at(14)), busy(B, at(16), at(19))]
    r = find_slots(busy=busy_slots, windows=WHOLE_DAY, venue_ids={A},
                   duration_minutes=60, travel=far, now=NOW)
    assert r.anchored == []
    assert dspans(r) == {"2026-10-06": [("20:30", "22:30")]}


def test_dedicated_needs_known_travel_time():
    # 當天在 C 館有課，C 跟 A 沒有車程資料 → 前後都視為趕不到，不列專程
    r = run([busy(C, at(10), at(11))], {A})
    assert r.dedicated == []


def test_dedicated_skips_start_times_already_past():
    r = run([], {A}, now=at(15, 10))
    assert dspans(r) == {"2026-10-06": [("15:30", "22:30")]}
