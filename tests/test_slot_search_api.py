"""POST /api/slot-search 與 GET /api/slot-search/areas 整合測試。

課程直接寫進測試資料庫（不透過建課 API，免得牽扯價目計算），「現在」用
dependency override 固定在 2030-01-01，日期都用 2030-01-07（週一）起。
"""
from datetime import date, datetime, time

import pytest

from app import models
from app.database import SessionLocal
from app.main import app
from app.routers.slot_search import get_now
from tests.conftest import create_student, create_venue

DAY = date(2030, 1, 7)


@pytest.fixture()
def api(client):
    app.dependency_overrides[get_now] = lambda: datetime(2030, 1, 1, 0, 0)
    yield client
    app.dependency_overrides.pop(get_now, None)


def add_lesson(student_id, venue_id, start: time, duration=60, status=models.LessonStatus.SCHEDULED, day=DAY):
    with SessionLocal() as db:
        db.add(models.Lesson(
            student_id=student_id, venue_id=venue_id, date=day,
            start_time=start, duration=duration, status=status,
        ))
        db.commit()


def search(api, venue_ids, date_from=DAY, date_to=DAY, **extra):
    body = {"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "venue_ids": venue_ids, **extra}
    return api.post("/api/slot-search", json=body)


def test_anchored_candidates_and_student_facing_message(api):
    s = create_student(api)["id"]
    v = create_venue(api, "動智館")["id"]
    add_lesson(s, v, time(18))

    res = search(api, [v], time_from="18:00", time_to="22:00")
    assert res.status_code == 200, res.text
    body = res.json()
    assert [(c["start"], c["venue_name"]) for c in body["anchored_candidates"]] == [("2030-01-07T19:00:00", "動智館")]
    # 給學生看的訊息不能有「貼靠」「專程」「既有課程」這類內部用語
    assert body["message"] == "我這幾個時段可以：\n・1/7(一) 19:00-20:00 動智館"


def test_leave_and_cancelled_free_the_slot(api):
    s = create_student(api)["id"]
    v = create_venue(api)["id"]
    add_lesson(s, v, time(18))
    add_lesson(s, v, time(19), status=models.LessonStatus.LEAVE)
    add_lesson(s, v, time(17), status=models.LessonStatus.CANCELLED)

    starts = [c["start"][11:16] for c in search(api, [v]).json()["anchored_candidates"]]
    assert starts == ["17:00", "19:00"]


def test_flexible_days_listed_with_time_spans(api):
    v = create_venue(api)["id"]
    body = search(api, [v], date_to=date(2030, 1, 8), time_from="18:00", time_to="22:00", duration_minutes=120).json()
    assert body["anchored_candidates"] == []
    # 開始時間 18:00-21:30 都可以，但兩小時的課最晚 22:30 下課
    assert body["message"] == (
        "這幾天比較彈性，時間可以再討論：\n"
        "・1/7(一) 18:00-22:30\n"
        "・1/8(二) 18:00-22:30"
    )


def test_no_candidates_message(api):
    s = create_student(api)["id"]
    v = create_venue(api)["id"]
    add_lesson(s, v, time(17), duration=330)  # 17:00-22:30 排滿
    body = search(api, [v], time_from="18:00", time_to="22:00").json()
    assert body["message"] == "這段時間目前排不進去，要不要換個日期？"


def test_area_presets(api):
    a = create_venue(api, "三重館")["id"]
    b = create_venue(api, "竹北館")["id"]
    with SessionLocal() as db:
        db.add_all([models.VenueArea(venue_id=a, area="台北"), models.VenueArea(venue_id=b, area="新竹")])
        db.commit()
    assert api.get("/api/slot-search/areas").json() == {"台北": [a], "新竹": [b]}


@pytest.mark.parametrize(
    "extra",
    [
        {"date_to": "2030-01-06"},  # 結束早於開始
        {"date_to": "2030-03-01"},  # 超過 31 天
        {"time_from": "20:00", "time_to": "18:00"},
        {"venue_ids": []},
        {"venue_ids": [999]},
    ],
)
def test_invalid_requests(api, extra):
    create_venue(api)
    body = {"date_from": "2030-01-07", "date_to": "2030-01-07", "venue_ids": [1], **extra}
    assert api.post("/api/slot-search", json=body).status_code == 422
