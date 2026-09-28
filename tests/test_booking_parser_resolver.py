"""日期換算（app/booking_parser/resolver.py）的測試，對應功能規格 1.2
列出的必測案例。全部用固定的 reference_datetime，不依賴執行當下的真實
日期，結果才是確定性的。
"""
from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.booking_parser.resolver import DateResolutionError, resolve_date, resolve_window
from app.booking_parser.schemas import DateExpr, PartOfDay, TimeWindowExpr

TAIWAN_TZ_OFFSET = "+08:00"


def _ref(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


def test_day_offset跨月():
    # 2026-09-28 是週一，+5 天跨到 10 月
    ref = _ref("2026-09-28T10:00:00+08:00")
    result, ambiguities = resolve_date(DateExpr(day_offset=5), ref)
    assert result == date(2026, 10, 3)
    assert ambiguities == []


def test_絕對日期已過視為明年並標記ambiguity():
    # 參考時間是 2026-09-28，訊息說「1/15」（今年的 1/15 早就過了）
    ref = _ref("2026-09-28T10:00:00+08:00")
    result, ambiguities = resolve_date(DateExpr(absolute_month=1, absolute_day=15), ref)
    assert result == date(2027, 1, 15)
    assert len(ambiguities) == 1
    assert "明年" in ambiguities[0]


def test_絕對日期還沒到就用今年不標記ambiguity():
    ref = _ref("2026-09-28T10:00:00+08:00")
    result, ambiguities = resolve_date(DateExpr(absolute_month=12, absolute_day=25), ref)
    assert result == date(2026, 12, 25)
    assert ambiguities == []


def test_這週日剛好是今天():
    # 2026-10-04 是週日
    ref = _ref("2026-10-04T09:00:00+08:00")
    result, _ = resolve_date(DateExpr(week_offset=0, weekday=7), ref)
    assert result == date(2026, 10, 4)


def test_下下週():
    # 2026-09-28 週一，下下週的週三
    ref = _ref("2026-09-28T10:00:00+08:00")
    result, _ = resolve_date(DateExpr(week_offset=2, weekday=3), ref)
    assert result == date(2026, 10, 14)


def test_週日當天說下週一會是明天():
    # 2026-10-04 是週日，「下週一」應該是隔天 10/5，不是再過一週
    ref = _ref("2026-10-04T09:00:00+08:00")
    result, _ = resolve_date(DateExpr(week_offset=1, weekday=1), ref)
    assert result == date(2026, 10, 5)


def test_跨年():
    # 2026-12-29 週二，+5 天跨到隔年 1 月
    ref = _ref("2026-12-29T10:00:00+08:00")
    result, _ = resolve_date(DateExpr(day_offset=5), ref)
    assert result == date(2027, 1, 3)


def test_今年一月一日已過會自動跳到明年不會誤判成過去日期():
    ref = _ref("2026-09-28T10:00:00+08:00")
    result, ambiguities = resolve_date(DateExpr(absolute_month=1, absolute_day=1), ref)
    assert result == date(2027, 1, 1)
    assert len(ambiguities) == 1


def test_換算結果早於今天要驗證失敗():
    # 2026-09-30 是週三，「這週一」已經是兩天前，這是使用者真的有可能
    # 講出來的話（回顧本週），但換算出的日期早於今天，要被擋下來
    ref = _ref("2026-09-30T10:00:00+08:00")
    with pytest.raises(DateResolutionError):
        resolve_date(DateExpr(week_offset=0, weekday=1), ref)


def test_只有時段沒有日期會被pydantic擋下():
    """TimeWindowExpr.date 是必填欄位，只給 part_of_day 不給 date 要直接
    在 schema 驗證階段被擋下，不會流到 resolver 才發現。"""
    with pytest.raises(ValidationError):
        TimeWindowExpr(part_of_day=PartOfDay.evening)


def test_只有part_of_day時用固定時段範圍():
    ref = _ref("2026-09-28T10:00:00+08:00")
    window = TimeWindowExpr(date=DateExpr(day_offset=0), part_of_day=PartOfDay.evening)
    resolved, _ = resolve_window(window, ref)
    assert resolved.start.time().isoformat() == "18:00:00"
    assert resolved.end.time().isoformat() == "22:00:00"


def test_只有日期沒有時段時用整天範圍():
    ref = _ref("2026-09-28T10:00:00+08:00")
    window = TimeWindowExpr(date=DateExpr(day_offset=0))
    resolved, _ = resolve_window(window, ref)
    assert resolved.start.time().isoformat() == "08:00:00"
    assert resolved.end.time().isoformat() == "22:00:00"
