"""取消的套組課程不扣堂的回歸測試。

以前取消的課在「剩餘堂數」算成用掉，在「可再排堂數」卻不算占用：取消一堂、
再補排一堂後，排定的堂數跟總堂數一樣，剩餘卻少一堂（實際案例：13 堂套組顯示 12/13）。
"""
from datetime import date, timedelta

from app import models
from app.database import SessionLocal
from conftest import create_package, create_student, create_venue


def set_status(lesson_id, status):
    with SessionLocal() as db:
        db.get(models.Lesson, lesson_id).status = status
        db.commit()


def test_cancel_then_rebook_keeps_full_remaining(client):
    student = create_student(client)
    venue = create_venue(client, "A館")
    future = [(date.today() + timedelta(weeks=w + 1)).isoformat() for w in range(3)]
    package = create_package(client, student["id"], venue["id"], future)
    lessons = client.get(f"/api/packages/{package['id']}/lessons").json()

    set_status(lessons[1]["id"], models.LessonStatus.CANCELLED)
    pkg = client.get(f"/api/packages/{package['id']}").json()
    assert pkg["remaining_sessions"] == 3  # 取消不算用掉
    assert pkg["available_sessions"] == 1  # 額度還回來，可以補排一堂

    # 補排一堂掛回套組：三堂排定、一堂取消，剩餘仍是 3/3
    res = client.post("/api/lessons", json={
        "student_id": student["id"], "venue_id": venue["id"], "package_id": package["id"],
        "date": (date.today() + timedelta(weeks=5)).isoformat(), "start_time": "18:00:00",
        "duration": 60, "headcount": 1,
    })
    assert res.status_code == 201, res.text
    pkg = client.get(f"/api/packages/{package['id']}").json()
    assert pkg["remaining_sessions"] == 3
    assert pkg["available_sessions"] == 0
    assert pkg["status"] == "active"


def test_past_cancelled_lesson_not_counted_as_used(client):
    student = create_student(client)
    venue = create_venue(client, "A館")
    dates = [(date.today() - timedelta(days=7)).isoformat(), (date.today() + timedelta(days=7)).isoformat()]
    package = create_package(client, student["id"], venue["id"], dates)
    lessons = client.get(f"/api/packages/{package['id']}/lessons").json()

    # 日期已過但被取消的那堂也不扣；沒取消的過去課程照樣扣
    assert client.get(f"/api/packages/{package['id']}").json()["remaining_sessions"] == 1
    set_status(lessons[0]["id"], models.LessonStatus.CANCELLED)
    assert client.get(f"/api/packages/{package['id']}").json()["remaining_sessions"] == 2
