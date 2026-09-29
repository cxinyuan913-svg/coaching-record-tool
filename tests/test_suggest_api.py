"""POST /api/booking-requests/{id}/suggest 整合測試。

課程跟約課紀錄直接寫進測試資料庫（不透過建課 API，免得牽扯價目計算），
「現在」用 dependency override 固定在 2030-01-01，日期都用 2030-01-07（週一）。
"""
import json
from datetime import date, datetime, time

import pytest

from app import models
from app.database import SessionLocal
from app.main import app
from app.routers.booking_parser import get_now
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


def add_request(windows, student_name=None, area=None, duration=None) -> int:
    parsed = {
        "intent": "new_booking", "student_name": student_name, "area": area,
        "windows": [], "duration_minutes": duration, "ambiguities": [],
    }
    resolved = [
        {"date": s.date().isoformat(), "start": s.isoformat() + "+08:00", "end": e.isoformat() + "+08:00"}
        for s, e in windows
    ]
    with SessionLocal() as db:
        r = models.BookingRequest(
            raw_text="測試", reference_datetime=datetime(2030, 1, 1),
            parsed_json=json.dumps(parsed, ensure_ascii=False),
            resolved_json=json.dumps(resolved), status=models.BookingRequestStatus.OK,
        )
        db.add(r)
        db.commit()
        return r.id


def evening(day=DAY):
    return (datetime.combine(day, time(18)), datetime.combine(day, time(22)))


def whole_day(day=DAY):
    return (datetime.combine(day, time(8)), datetime.combine(day, time(22)))


def test_same_venue_candidates_and_message(api):
    s = create_student(api, name="小明")["id"]
    v = create_venue(api, "動智館")["id"]
    add_lesson(s, v, time(18))
    rid = add_request([evening()])

    res = api.post(f"/api/booking-requests/{rid}/suggest")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["duration_source"] == "default"
    assert [(c["start"], c["venue_name"]) for c in body["anchored_candidates"]] == [
        ("2030-01-07T19:00:00", "動智館")
    ]
    assert body["message"] == "貼靠候選（交通最省）：\n・1/7(一) 19:00-20:00，動智館（緊接既有課程）"


def test_leave_and_cancelled_free_the_slot(api):
    s = create_student(api)["id"]
    v = create_venue(api)["id"]
    add_lesson(s, v, time(18))
    add_lesson(s, v, time(19), status=models.LessonStatus.LEAVE)
    add_lesson(s, v, time(17), status=models.LessonStatus.CANCELLED)
    rid = add_request([whole_day()])

    starts = [c["start"][11:16] for c in api.post(f"/api/booking-requests/{rid}/suggest").json()["anchored_candidates"]]
    assert starts == ["17:00", "19:00"]


def test_duration_from_students_last_lesson(api):
    s = create_student(api, name="小華")["id"]
    v = create_venue(api)["id"]
    add_lesson(s, v, time(10), duration=120, day=date(2029, 12, 20))
    add_lesson(s, v, time(14), duration=120)
    rid = add_request([whole_day()], student_name="小華")

    body = api.post(f"/api/booking-requests/{rid}/suggest").json()
    assert (body["duration_minutes"], body["duration_source"]) == (120, "student_last_lesson")
    assert body["student_id"] == s
    # 手動指定優先
    body = api.post(f"/api/booking-requests/{rid}/suggest", json={"duration_minutes": 90}).json()
    assert (body["duration_minutes"], body["duration_source"]) == (90, "request")


def test_area_limits_venues_and_unknown_area_falls_back(api):
    s = create_student(api)["id"]
    a = create_venue(api, "竹北館")["id"]
    b = create_venue(api, "新竹館")["id"]
    with SessionLocal() as db:
        db.add(models.VenueArea(venue_id=a, area="竹北"))
        db.commit()
    add_lesson(s, a, time(10))
    add_lesson(s, b, time(15))

    rid = add_request([whole_day()], area="竹北")
    body = api.post(f"/api/booking-requests/{rid}/suggest").json()
    assert body["venue_ids"] == [a]
    assert {c["venue_id"] for c in body["anchored_candidates"]} == {a}

    rid = add_request([whole_day()], area="火星")
    body = api.post(f"/api/booking-requests/{rid}/suggest").json()
    assert body["venue_ids"] == [a, b]
    assert any("火星" in n for n in body["notes"])


def test_dedicated_day_message_uses_student_window(api):
    create_venue(api)
    rid = add_request([evening()])
    body = api.post(f"/api/booking-requests/{rid}/suggest").json()
    assert body["anchored_candidates"] == []
    assert body["message"] == "專程候選（需要專程前往）：\n・1/7(一) 18:00-22:00 之間可談，需自行決定時段"

    rid = add_request([whole_day()])
    assert "全天可談" in api.post(f"/api/booking-requests/{rid}/suggest").json()["message"]


def test_no_candidates_message(api):
    s = create_student(api)["id"]
    v = create_venue(api)["id"]
    # 18-22 被課程排滿，而且當天有課所以也不是專程日
    add_lesson(s, v, time(17), duration=300)
    rid = add_request([evening()])
    assert api.post(f"/api/booking-requests/{rid}/suggest").json()["message"] == "這段時間目前排不進去，要不要換個日期？"


def test_errors(api):
    assert api.post("/api/booking-requests/999/suggest").status_code == 404
    rid = add_request([])
    res = api.post(f"/api/booking-requests/{rid}/suggest")
    assert res.status_code == 422
    assert "沒有可用的日期時段" in res.json()["detail"]
    rid = add_request([evening()])
    assert api.post(f"/api/booking-requests/{rid}/suggest", json={"venue_ids": [999]}).status_code == 422
