"""app/timeutil.py：不管測試機器是什麼時區，now_taipei() 都要等於 UTC+8。"""
from datetime import datetime, timedelta, timezone

from app.timeutil import now_taipei, today_taipei


def test_now_taipei_is_utc_plus_8_and_naive():
    expected = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
    actual = now_taipei()
    assert actual.tzinfo is None  # 跟資料庫一樣不帶時區，才能直接跟課程時間比較
    assert abs(actual - expected) < timedelta(seconds=5)
    assert today_taipei() == actual.date() or abs(actual - expected) < timedelta(seconds=5)
