"""公開預約網站介接端點（POST /api/integrations/lessons）的測試。"""
from datetime import date, timedelta, time

from app.auth import PUBLIC_BOOKING_API_TOKEN

from conftest import create_student, create_venue

AUTH_HEADERS = {"Authorization": f"Bearer {PUBLIC_BOOKING_API_TOKEN}"}


def _payload(venue_name: str, **overrides) -> dict:
    payload = {
        "venue_name": venue_name,
        "student_name": "新學生",
        "student_contact": "0912345678",
        "date": (date.today() + timedelta(days=10)).isoformat(),
        "start_time": "18:00:00",
        "duration": 60,
    }
    payload.update(overrides)
    return payload


def test_缺少或錯誤的token會被拒絕(client):
    venue = create_venue(client)
    res = client.post("/api/integrations/lessons", json=_payload(venue["name"]))
    assert res.status_code == 401

    res = client.post(
        "/api/integrations/lessons",
        json=_payload(venue["name"]),
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert res.status_code == 401


def test_場館名稱不存在時回400(client):
    res = client.post(
        "/api/integrations/lessons", json=_payload("不存在的場館"), headers=AUTH_HEADERS
    )
    assert res.status_code == 400


def test_同時段教練已有其他課程時回409(client):
    """驗證行為：不分場地，同一個時間點教練只能上一堂課（比照
    package_logic.mark_leave_and_reschedule 的衝突判斷邏輯）。"""
    venue = create_venue(client)
    another_venue = create_venue(client, name="另一個場地")
    student = create_student(client)
    clash_date = (date.today() + timedelta(days=10)).isoformat()

    res = client.post(
        "/api/lessons",
        json={
            "student_id": student["id"],
            "venue_id": venue["id"],
            "date": clash_date,
            "start_time": "18:00:00",
            "duration": 60,
            "headcount": 1,
            "payment_status": "unpaid",
            "revenue_amount": 1000,
            "venue_fee_amount": 0,
        },
    )
    assert res.status_code == 201, res.text

    res = client.post(
        "/api/integrations/lessons",
        json=_payload(another_venue["name"], date=clash_date, start_time="18:00:00"),
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 409, res.text


def test_找不到相符的學生時會自動新增一筆新生等級的學生(client):
    venue = create_venue(client)
    res = client.post(
        "/api/integrations/lessons",
        json=_payload(venue["name"], student_name="從沒見過的學生", student_contact="0900000000"),
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["student_created"] is True

    student = client.get(f"/api/students/{body['student_id']}").json()
    assert student["name"] == "從沒見過的學生"
    assert student["tier"] == "new"

    lesson = client.get(f"/api/lessons/{body['lesson_id']}").json()
    assert lesson["payment_status"] == "unpaid"
    # tier=new、60 分鐘、1 人：查價目表應為 1600
    assert body["revenue_amount"] == 1600
    assert lesson["revenue_amount"] == 1600


def test_姓名與聯絡方式都相符時沿用既有學生不重複建立(client):
    student = create_student(client, name="老學生")
    client_update = client.put(
        f"/api/students/{student['id']}",
        json={"name": "老學生", "contact": "0911111111", "tier": student["tier"]},
    )
    assert client_update.status_code == 200, client_update.text

    venue = create_venue(client)
    res = client.post(
        "/api/integrations/lessons",
        json=_payload(venue["name"], student_name="老學生", student_contact="0911111111"),
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["student_created"] is False
    assert body["student_id"] == student["id"]
