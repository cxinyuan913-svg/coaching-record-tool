"""公開預約網站 v2 用的整合端點：場館清單、可約時段、場地費試算、建立課程帶金額、
取消與標記已付款。全部只用 public_booking_api_token，不需要網頁登入。"""
from datetime import date, datetime, timedelta

import pytest

from app.auth import PUBLIC_BOOKING_API_TOKEN
from app.main import app
from app.routers.slot_search import get_now
from conftest import create_student, create_venue

AUTH = {"Authorization": f"Bearer {PUBLIC_BOOKING_API_TOKEN}"}
DAY = date(2026, 10, 17)  # 週六


@pytest.fixture()
def fixed_now():
    app.dependency_overrides[get_now] = lambda: datetime(2026, 10, 1, 9, 0)
    yield
    app.dependency_overrides.pop(get_now, None)


def _lesson(client, venue_id, start="10:00:00", day=DAY, duration=60):
    student = create_student(client, name=f"學生{start}")
    res = client.post(
        "/api/lessons",
        json={
            "student_id": student["id"],
            "venue_id": venue_id,
            "date": day.isoformat(),
            "start_time": start,
            "duration": duration,
            "headcount": 1,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_這些端點不帶token一律401(anon_client):
    for method, url, body in (
        ("get", "/api/integrations/public/venues", None),
        ("post", "/api/integrations/availability", {"days": []}),
        ("post", "/api/integrations/venue-fee-quote", {}),
        ("post", "/api/integrations/lessons/1/cancel", None),
        ("post", "/api/integrations/lessons/1/mark-paid", {"payment_date": "2026-10-01"}),
    ):
        res = getattr(anon_client, method)(url, json=body) if body is not None else getattr(anon_client, method)(url)
        assert res.status_code == 401, url


def test_場館清單含地區且不用網頁登入(client, anon_client):
    venue = create_venue(client, name="快羽會館")
    create_venue(client, name="晴天羽球館")
    # 地區表沒有設定 API，直接寫資料庫
    from app import models
    from app.database import SessionLocal

    with SessionLocal() as db:
        db.add(models.VenueArea(venue_id=venue["id"], area="台北"))
        db.commit()
    client.post("/api/auth/logout")

    res = anon_client.get("/api/integrations/public/venues", headers=AUTH)
    assert res.status_code == 200, res.text
    assert res.json() == [
        {"name": "快羽會館", "areas": ["台北"]},
        {"name": "晴天羽球館", "areas": []},
    ]


def test_可約時段扣掉既有課程並標出同館接課_不帶學生資料(client, fixed_now):
    venue = create_venue(client, name="快羽會館")
    _lesson(client, venue["id"], start="10:00:00")
    res = client.post(
        "/api/integrations/availability",
        headers=AUTH,
        json={
            "duration_minutes": 60,
            "days": [{"date": DAY.isoformat(), "time_from": "08:00", "time_to": "12:00", "venue_names": ["快羽會館"]}],
        },
    )
    assert res.status_code == 200, res.text
    slots = res.json()["slots"]
    assert [(s["start_time"], s["adjacent"]) for s in slots] == [
        ("08:00:00", False),
        ("09:00:00", True),
        ("11:00:00", True),
    ]
    assert set(slots[0]) == {"date", "start_time", "end_time", "venue_name", "adjacent"}


def test_可約時段場館名稱不存在回400(client, fixed_now):
    res = client.post(
        "/api/integrations/availability",
        headers=AUTH,
        json={"days": [{"date": DAY.isoformat(), "time_from": "08:00", "time_to": "12:00", "venue_names": ["不存在"]}]},
    )
    assert res.status_code == 400
    assert "不存在" in res.json()["detail"]


def test_場地費試算(client):
    venue = create_venue(client, name="快羽會館")
    client.put(
        f"/api/venues/{venue['id']}/fee-rates",
        json=[{"weekdays": [5, 6], "start_time": "08:00", "end_time": "22:00", "fee_per_hour": 500}],
    )
    body = {"venue_name": "快羽會館", "date": DAY.isoformat(), "start_time": "10:00", "duration": 90}
    res = client.post("/api/integrations/venue-fee-quote", headers=AUTH, json=body)
    assert res.status_code == 200, res.text
    assert res.json() == {"venue_fee": 750}

    weekday = (DAY - timedelta(days=4)).isoformat()  # 週二沒設定價目
    res = client.post("/api/integrations/venue-fee-quote", headers=AUTH, json={**body, "date": weekday})
    assert res.status_code == 400
    assert "場地費沒有設定" in res.json()["detail"]


def _create_public_lesson(client, **overrides):
    venue = create_venue(client, name="快羽會館")
    payload = {
        "venue_name": venue["name"],
        "student_name": "線上學生",
        "student_contact": "0912000000",
        "date": DAY.isoformat(),
        "start_time": "14:00:00",
        "duration": 60,
        "coach_fee": 1500,
        "venue_fee": 500,
        "source_booking_id": 42,
    }
    payload.update(overrides)
    res = client.post("/api/integrations/lessons", headers=AUTH, json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_建立課程時帶入的教練費與場地費會直接採用(client):
    created = _create_public_lesson(client)
    assert created["revenue_amount"] == 1500
    assert created["venue_fee_amount"] == 500
    lesson = client.get(f"/api/lessons/{created['lesson_id']}").json()
    assert lesson["revenue_amount"] == 1500
    assert lesson["venue_fee_amount"] == 500
    assert lesson["payment_status"] == "unpaid"


def test_沒帶金額時照舊依價目表推算(client):
    created = _create_public_lesson(client, coach_fee=None, venue_fee=None, source_booking_id=None)
    assert created["revenue_amount"] == 1600  # 新生 1 小時
    assert created["venue_fee_amount"] == 0


def test_取消課程後時段釋放且可重複呼叫(client):
    created = _create_public_lesson(client)
    for _ in range(2):
        res = client.post(f"/api/integrations/lessons/{created['lesson_id']}/cancel", headers=AUTH)
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "cancelled"
    # 同一時段可以再建立一堂（已取消的課不占用時段）
    res = client.post(
        "/api/integrations/lessons",
        headers=AUTH,
        json={"venue_name": "快羽會館", "student_name": "另一位", "date": DAY.isoformat(), "start_time": "14:00:00", "duration": 60},
    )
    assert res.status_code == 201, res.text


def test_標記已付款(client):
    created = _create_public_lesson(client)
    res = client.post(
        f"/api/integrations/lessons/{created['lesson_id']}/mark-paid", headers=AUTH, json={"payment_date": "2026-10-08"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["payment_status"] == "paid"
    assert res.json()["payment_date"] == "2026-10-08"


def test_教練自己排的課預約網站不能取消或改付款狀態(client):
    venue = create_venue(client, name="快羽會館")
    lesson = _lesson(client, venue["id"])
    assert client.post(f"/api/integrations/lessons/{lesson['id']}/cancel", headers=AUTH).status_code == 403
    res = client.post(f"/api/integrations/lessons/{lesson['id']}/mark-paid", headers=AUTH, json={"payment_date": "2026-10-08"})
    assert res.status_code == 403
    assert client.post("/api/integrations/lessons/99999/cancel", headers=AUTH).status_code == 404
