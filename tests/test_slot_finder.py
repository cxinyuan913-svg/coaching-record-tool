"""找空檔演算法 slot_finder.find_slots 的單元測試（純函式，不用資料庫）。

場館設定：A=1、B=2 之間車程 20 分鐘；C=3 跟誰都沒設定車程（不可銜接）。
日期統一用 2026-10-06（週二），「現在」是 2026-10-01。
"""
from datetime import datetime

from app.booking_parser.slot_finder import (
    BusySlot,
    TimeWindow,
    _merge_overlapping,
    find_slots,
    make_travel_lookup,
)

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


def run(busy_slots, venue_ids, duration=60, windows=WHOLE_DAY, now=NOW, travel=TRAVEL):
    return find_slots(
        busy=busy_slots, windows=windows, venue_ids=venue_ids,
        duration_minutes=duration, travel=travel, now=now,
    )


def spans(result):
    return [(c.start.strftime("%H:%M"), c.end.strftime("%H:%M"), c.venue_id) for c in result.anchored]


def blocks(result):
    return [(b.start.strftime("%H:%M"), b.end.strftime("%H:%M"), b.venue_ids) for b in result.open_blocks]


# ---- 第一組：同館接課 ----

def test_same_venue_before_and_after():
    r = run([busy(A, at(18), at(19))], {A})
    assert spans(r) == [("17:00", "18:00", A), ("19:00", "20:00", A)]


def test_no_cross_venue_anchored_candidates():
    # 只查 B 館，A 館的課不會長出接課候選（換館的情況交給大空檔）
    r = run([busy(A, at(10), at(11))], {B})
    assert r.anchored == []


def test_cannot_reach_next_lesson_at_other_venue():
    # A 館 19:00-20:00 下課要 20:20 才到得了 B 館，趕不上 B 館 20:10 的課
    r = run([busy(A, at(18), at(19)), busy(B, at(20, 10), at(21, 10))], {A})
    assert spans(r) == [("17:00", "18:00", A)]


def test_unknown_travel_time_blocks_connection():
    # C 館跟 A 館沒有車程資料 → 緊接在 C 館課程之前的候選視為趕不上
    r = run([busy(A, at(18), at(19)), busy(C, at(20), at(21))], {A})
    assert spans(r) == [("17:00", "18:00", A)]


def test_work_hours_boundary():
    assert spans(run([busy(A, at(21, 30), at(22, 30))], {A})) == [("20:30", "21:30", A)]
    assert spans(run([busy(A, at(8, 30), at(9, 30))], {A})) == [("09:30", "10:30", A)]
    # 剛好 22:30 下課可以
    assert ("21:30", "22:30", A) in spans(run([busy(A, at(21), at(21, 30))], {A}))


def test_start_time_must_fall_in_student_window():
    evening = [TimeWindow(start=at(18), end=at(22))]
    r = run([busy(A, at(17), at(18))], {A}, windows=evening)
    assert spans(r) == [("18:00", "19:00", A)]
    # 只要求開始時間在時段內：19:00 開始的兩小時課 19:00-21:00 也算
    seven = [TimeWindow(start=at(19), end=at(20))]
    r = run([busy(A, at(17), at(19))], {A}, duration=120, windows=seven)
    assert spans(r) == [("19:00", "21:00", A)]


def test_candidates_in_the_past_excluded():
    r = run([busy(A, at(18), at(19))], {A}, now=at(18, 30))
    assert spans(r) == [("19:00", "20:00", A)]


def test_same_slot_from_two_lessons_kept_once():
    # 11:00-12:00 同時是 10:00 那堂之後、12:00 那堂之前
    r = run([busy(A, at(10), at(11)), busy(A, at(12), at(13))], {A})
    assert spans(r).count(("11:00", "12:00", A)) == 1


def test_sorted_by_time_and_capped_at_five():
    lessons = [busy(A, at(h), at(h + 1)) for h in (9, 12, 15, 18)]
    r = run(lessons, {A})
    assert len(r.anchored) == 5
    starts = [c.start for c in r.anchored]
    assert starts == sorted(starts)


# ---- 第二組：大空檔 ----

def test_open_blocks_around_lessons():
    # 只用整點開始：一小時的課最晚 21:00 開始，所以大空檔到 22:00
    r = run([busy(A, at(18), at(19))], {A})
    assert blocks(r) == [("08:00", "18:00", [A]), ("19:00", "22:00", [A])]


def test_venues_with_same_block_are_merged():
    r = run([], {A, B})
    assert blocks(r) == [("08:00", "22:00", [A, B])]


def test_overlapping_blocks_merged_to_common_time():
    # A 館 10-11 有課：A 館 11:00 就能接著上，B 館加 20 分鐘車程要 12:00（整點）
    # → 合併成一行，時段取兩館都可以的 12:00-22:00（教練要求，訊息短比較重要）
    # 早上 A 館 08:00-10:00；B 館要趕回 A 館 10:00 的課，只剩 08:00-09:00 不到 2 小時
    r = run([busy(A, at(10), at(11))], {A, B})
    assert blocks(r) == [("08:00", "10:00", [A]), ("12:00", "22:00", [A, B])]


def test_merge_rules():
    # 時段差不多（開始、結束都相差 ≤ 1 小時）→ 合併，取共同時段
    assert _merge_overlapping([(at(16), at(22), A), (at(17), at(22), B)]) == [(at(17), at(22), [A, B])]
    # 開始相差 2 小時：合併會讓 A 館少掉一半 → 分開列
    assert _merge_overlapping([(at(8), at(12), A), (at(10), at(12), B)]) == [
        (at(8), at(12), [A]),
        (at(10), at(12), [B]),
    ]
    # 相差 ≤ 1 小時但共同時段不到 2 小時 → 分開列
    assert _merge_overlapping([(at(8), at(10), A), (at(9), at(11), B)]) == [
        (at(8), at(10), [A]),
        (at(9), at(11), [B]),
    ]


def test_venue_without_travel_time_not_listed():
    # 當天在 A 館有課，C 館跟 A 館沒車程 → C 館整天趕不到，只列 A 館
    r = run([busy(A, at(11), at(22, 30))], {A, C})
    assert blocks(r) == [("08:00", "11:00", [A])]


def test_open_block_includes_travel_from_other_area():
    # 真實案例 10/4：白天在新竹（這裡用 B，車程 77 分鐘）上課到 19:00，
    # 台北（A）最早 21:00（整點）才趕得到，只剩 21:00-22:00 不到 2 小時 → 不列；
    # 14:00-16:00 的空檔來回車程不夠也不能算進來
    far = make_travel_lookup({(A, B): 77})
    r = run([busy(B, at(8), at(14)), busy(B, at(16), at(19))], {A}, travel=far)
    assert blocks(r) == []
    r = run([busy(B, at(8), at(14)), busy(B, at(16), at(18))], {A}, travel=far)
    assert blocks(r) == [("20:00", "22:00", [A])]


def test_open_block_shorter_than_two_hours_not_listed():
    # 08:00-09:30 只有 1.5 小時，不算大空檔；但 08:30 的同館接課還是列在第一組
    r = run([busy(A, at(9, 30), at(22, 30))], {A})
    assert blocks(r) == []
    assert spans(r) == [("08:30", "09:30", A)]


def test_open_block_needs_known_travel_time():
    # 當天在 C 館有課，C 跟 A 沒有車程資料 → 前後都視為趕不到
    r = run([busy(C, at(10), at(11))], {A})
    assert blocks(r) == []


def test_open_block_skips_start_times_already_past():
    r = run([], {A}, now=at(15, 10))
    assert blocks(r) == [("16:00", "22:00", [A])]


def test_open_block_lists_days_other_lessons_for_coach():
    lesson = busy(B, at(8), at(9))
    r = run([lesson], {A})
    assert all(b.other_busy == [lesson] for b in r.open_blocks)
