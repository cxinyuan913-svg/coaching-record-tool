"""固定時段排課 recurring_finder.find_recurring 的單元測試（純函式，不用資料庫）。

場館：A=1、B=2 之間車程 20 分鐘；C=3 沒設定車程。
從 2026-10-10（週六）起排 8 週，「現在」是 2026-10-01。
"""
from datetime import date, datetime, time, timedelta

from app.booking_parser.recurring_finder import MAX_POSTPONE, find_recurring, weekly_dates
from app.booking_parser.slot_finder import BusySlot, make_travel_lookup

A, B, C = 1, 2, 3
TRAVEL = make_travel_lookup({(A, B): 20})
NOW = datetime(2026, 10, 1)
FIRST = date(2026, 10, 10)
SATURDAYS = weekly_dates(FIRST, 8 + MAX_POSTPONE)

_ids = iter(range(1, 10000))


def lesson(venue, d, start_h, end_h):
    return BusySlot(
        lesson_id=next(_ids), venue_id=venue,
        start=datetime.combine(d, time(start_h)), end=datetime.combine(d, time(end_h)),
    )


def every_saturday(venue, start_h, end_h):
    return [lesson(venue, d, start_h, end_h) for d in SATURDAYS]


def run(busy, venue_ids, time_from=time(8), time_to=time(22, 30), weeks=8):
    return find_recurring(
        busy=busy, first_date=FIRST, weeks=weeks, time_from=time_from, time_to=time_to,
        venue_ids=venue_ids, duration_minutes=60, travel=TRAVEL, now=NOW,
        venue_names={A: "A館", B: "B館", C: "C館"},
    )


def starts(options):
    return [(o.start_time.strftime("%H:%M"), o.venue_id) for o in options]


def test_empty_calendar_every_hour_works():
    options = run([], {A})
    assert len(options) == 10  # 只列前 10 名
    assert starts(options)[0] == ("08:00", A)
    assert options[0].dates == SATURDAYS[:8]
    assert options[0].skipped == []


def test_only_whole_hours_and_must_end_by_work_end():
    options = run([], {A}, time_from=time(20, 30))
    assert starts(options) == [("21:00", A)]  # 20:30 不是整點；22:00 開始會超過 22:30


def test_adjacent_to_weekly_lesson_ranked_first():
    options = run(every_saturday(A, 15, 16), {A})
    assert starts(options)[:2] == [("14:00", A), ("16:00", A)]
    assert options[0].adjacent_weeks == 8 and options[0].same_venue_weeks == 8


def test_same_venue_day_beats_dedicated_trip():
    # A 館每週六早上有課，B 館沒課：下午同樣是空的，A 館（不用專程跑）排前面
    options = run(every_saturday(A, 10, 11), {A, B}, time_from=time(15), time_to=time(16))
    assert starts(options) == [("15:00", A), ("15:00", B)]
    assert options[0].same_venue_weeks == 8 and options[0].adjacent_weeks == 0
    assert options[1].same_venue_weeks == 0


def test_conflict_week_is_postponed():
    # 第 3 週（10/24）16:00 已經有課 → 跳過，往後補到第 9 週（12/5）
    busy = [lesson(A, SATURDAYS[2], 16, 17)]
    [option] = run(busy, {A}, time_from=time(16), time_to=time(17))
    assert [s.date for s in option.skipped] == [date(2026, 10, 24)]
    assert "撞到 16:00-17:00 A館" in option.skipped[0].reason
    assert option.dates[-1] == date(2026, 12, 5)
    assert len(option.dates) == 8


def test_more_than_max_postpone_not_listed():
    busy = [lesson(A, d, 16, 17) for d in SATURDAYS[:MAX_POSTPONE + 1]]
    assert run(busy, {A}, time_from=time(16), time_to=time(17)) == []


def test_fewer_postpones_ranked_before_better_location():
    # 16:00 有一週要順延但每週都接課；17:00 不用順延 → 不用順延的排前面
    busy = every_saturday(A, 15, 16) + [lesson(A, SATURDAYS[1], 16, 17)]
    options = run(busy, {A}, time_from=time(16), time_to=time(18))
    assert starts(options) == [("17:00", A), ("16:00", A)]
    assert options[1].skipped and options[1].adjacent_weeks == 8


def test_travel_time_from_other_venue():
    # 第 2 週 B 館 15-16 有課，A 館 16:00 開始趕不過來（車程 20 分鐘）
    busy = [lesson(B, SATURDAYS[1], 15, 16)]
    [option] = run(busy, {A}, time_from=time(16), time_to=time(17))
    assert option.skipped[0].date == SATURDAYS[1]
    assert "前一堂 16:00 在B館下課，趕不過來" == option.skipped[0].reason


def test_unknown_travel_time_counts_as_unreachable():
    # 每週六 C 館都有課，C 跟 A 沒車程 → A 館當天任何時段都排不了
    assert run(every_saturday(C, 10, 11), {A}) == []


def test_postponed_dates_keep_weekly_rhythm():
    [option] = run([lesson(A, SATURDAYS[0], 16, 17)], {A}, time_from=time(16), time_to=time(17))
    gaps = {(b - a).days for a, b in zip(option.dates, option.dates[1:])}
    assert gaps == {7}
    assert option.dates[0] == SATURDAYS[1]
    assert option.dates[-1] == SATURDAYS[0] + timedelta(weeks=8)
