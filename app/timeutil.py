"""統一取得「台灣當地時間」。

課程時間在資料庫裡存的是沒有時區的台灣當地時間，所以程式裡的「現在／今天」
也一定要是台灣時間。不能用 datetime.now()／date.today()：那是「伺服器所在時區」
的時間，家裡 Windows 電腦剛好設台灣時區所以沒事，但雲端主機跟 Docker 容器預設是
UTC，會慢 8 小時——2026-09-29 上雲端後「上課前一小時提醒」就因此延遲約 8 小時。
"""
from datetime import date, datetime, timedelta, timezone

TAIWAN_TZ = timezone(timedelta(hours=8))


def now_taipei() -> datetime:
    """台灣當地時間，不帶時區（跟資料庫的存法一致，可以直接跟課程時間比較）。"""
    return datetime.now(TAIWAN_TZ).replace(tzinfo=None)


def today_taipei() -> date:
    return now_taipei().date()
