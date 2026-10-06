"""課程衝突檢查的回歸測試：時段重疊就擋、跨場館、首尾相接不算、請假／取消不占時段。

以前三個入口只比對「開始時間完全相同」：既有 16:00–18:00 的課，再排 17:00 開始
的課不會被擋，教練直接撞課。現在統一走 package_logic.find_overlapping_lesson。
"""
from datetime import date, time, timedelta

import pytest

from app import models
from app.auth import PUBLIC_BOOKING_API_TOKEN
from app.database import SessionLocal
from conftest import create_package, create_student, create_venue

DAY = date.today() + timedelta(days=30)  # 未來日期，避開「日期已過算用掉」等規則
AUTH = {"Authorization": f"Bearer {PUBLIC_BOOKING_API_TOKEN}"}


def add_lesson(student_id, venue_id, start: time, duration=120, status=models.LessonStatus.SCHEDULED, day=DAY):
    with SessionLocal() as db:
        db.add(models.Lesson(
            student_id=student_id, venue_id=venue_id, date=day, start_time=start,
            duration=duration, status=status,
        ))
        db.commit()


# ---- 公開預約網站建立課程 POST /api/integrations/lessons ----

def booking(venue_name, start, duration=60):
    return {
        "venue_name": venue_name, "student_name": "預約學生", "student_contact": "0900000000",
        "date": DAY.isoformat(), "start_time": start, "duration": duration,
    }


@pytest.mark.parametrize(
    "start, expected",
    [
        ("17:00:00", 409),  # 開始時間不同但落在 16:00–18:00 裡面（以前會放行）
        ("15:30:00", 409),  # 15:30–16:30 尾巴蓋到既有課程的開頭
        ("16:00:00", 409),  # 開始時間完全相同
        ("18:00:00", 201),  # 首尾剛好相接不算衝突
        ("15:00:00", 201),  # 15:00–16:00 剛好在前面結束
    ],
)
def test_integrations_rejects_overlap_across_venues(client, start, expected):
    student = create_student(client)
    a = create_venue(client, "A館")
    b = create_venue(client, "B館")
    add_lesson(student["id"], a["id"], time(16, 0))  # A 館 16:00–18:00
    # 新課在 B 館：教練同一時間只能上一堂，跨場館一樣要擋
    res = client.post("/api/integrations/lessons", json=booking("B館", start), headers=AUTH)
    assert res.status_code == expected, res.text
    if expected == 409:
        assert "16:00-18:00" in res.json()["detail"]


@pytest.mark.parametrize("status", [models.LessonStatus.LEAVE, models.LessonStatus.CANCELLED])
def test_integrations_ignores_leave_and_cancelled(client, status):
    student = create_student(client)
    venue = create_venue(client, "A館")
    add_lesson(student["id"], venue["id"], time(16, 0), status=status)
    res = client.post("/api/integrations/lessons", json=booking("A館", "17:00:00"), headers=AUTH)
    assert res.status_code == 201, res.text


# ---- 請假順延 POST /api/lessons/{id}/leave ----

def test_leave_makeup_rejects_overlap_with_other_venue(client):
    student = create_student(client)
    other = create_student(client, name="別的學生")
    venue = create_venue(client, "A館")
    other_venue = create_venue(client, "B館")
    package = create_package(client, student["id"], venue["id"], [DAY.isoformat()])  # 套組 18:00、60 分鐘
    [lesson] = client.get(f"/api/packages/{package['id']}/lessons").json()
    makeup_day = DAY + timedelta(weeks=1)
    add_lesson(other["id"], other_venue["id"], time(17, 30), duration=60, day=makeup_day)  # B 館 17:30–18:30

    res = client.post(f"/api/lessons/{lesson['id']}/leave",
                      json={"makeup_date": makeup_day.isoformat(), "makeup_start_time": "18:00:00"})
    assert res.status_code == 409
    assert "17:30-18:30" in res.json()["detail"]
    # 擋下時整筆不成立：原本那堂維持排定，不會變成請假
    assert client.get(f"/api/packages/{package['id']}/lessons").json()[0]["status"] == "scheduled"

    # 首尾相接（順延 18:30 開始）就可以
    res = client.post(f"/api/lessons/{lesson['id']}/leave",
                      json={"makeup_date": makeup_day.isoformat(), "makeup_start_time": "18:30:00"})
    assert res.status_code == 200, res.text


# ---- 一鍵建立套組 POST /api/packages（check_conflicts）----

def test_package_quick_create_rejects_partial_overlap(client):
    student = create_student(client)
    venue = create_venue(client, "A館")
    other_venue = create_venue(client, "B館")
    add_lesson(student["id"], other_venue["id"], time(16, 0))  # B 館 16:00–18:00
    res = client.post("/api/packages", json={
        "student_id": student["id"], "name": "測試", "session_duration": 60,
        "coach_fee_per_hour": 1000, "venue_fee_per_hour": 0, "purchased_date": DAY.isoformat(),
        "recur_start_time": "17:00:00", "default_venue_id": venue["id"], "payment_status": "unpaid",
        "sessions": [{"date": DAY.isoformat(), "start_time": "17:00:00"}], "check_conflicts": True,
    })
    assert res.status_code == 409
    assert "已有 16:00-18:00 的課" in res.json()["detail"]
