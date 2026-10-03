"""從找空檔一鍵建立課程套組：每堂各自的時間（sessions）、建立前檢查撞課（check_conflicts）。"""
from tests.conftest import create_package, create_student, create_venue


def payload(student_id, venue_id, **overrides):
    body = {
        "student_id": student_id,
        "name": "週六固定 3 堂",
        "session_duration": 60,
        "coach_fee_per_hour": 1000,
        "venue_fee_per_hour": 550,
        "purchased_date": "2030-01-01",
        "recur_start_time": "10:00:00",
        "default_venue_id": venue_id,
        "payment_status": "unpaid",
        "sessions": [
            {"date": "2030-01-12", "start_time": "10:00:00"},
            {"date": "2030-01-19", "start_time": "09:00:00"},  # 這週改成接課的時間
            {"date": "2030-01-26", "start_time": "10:00:00"},
        ],
        "check_conflicts": True,
    }
    body.update(overrides)
    return body


def lesson_times(client, package_id):
    lessons = client.get(f"/api/packages/{package_id}/lessons").json()
    return sorted((l["date"], l["start_time"][:5], l["venue_id"], l["duration"]) for l in lessons)


def test_each_session_keeps_its_own_start_time(client):
    s = create_student(client)["id"]
    v = create_venue(client)["id"]
    res = client.post("/api/packages", json=payload(s, v))
    assert res.status_code == 201, res.text
    pkg = res.json()
    assert pkg["total_sessions"] == 3
    assert lesson_times(client, pkg["id"]) == [
        ("2030-01-12", "10:00", v, 60),
        ("2030-01-19", "09:00", v, 60),
        ("2030-01-26", "10:00", v, 60),
    ]


def test_conflict_blocks_whole_package(client):
    s = create_student(client)["id"]
    other = create_student(client, name="別的學生")["id"]
    v = create_venue(client)["id"]
    # 在別的套組先占掉 1/19 08:30-09:30（套組預設 18:00，改用 recur_start_time 指定）
    create_package(client, other, v, ["2030-01-19"], recur_start_time="08:30:00")
    res = client.post("/api/packages", json=payload(s, v))
    assert res.status_code == 409
    assert "1/19 09:00" in res.json()["detail"]
    # 整筆不建立：學生名下沒有新套組
    assert [p for p in client.get("/api/packages").json() if p["student_id"] == s] == []


def test_without_check_conflicts_behaviour_unchanged(client):
    # 課程套組頁原本的建立方式（session_dates、不檢查衝突）完全不受影響
    s = create_student(client)["id"]
    v = create_venue(client)["id"]
    pkg = create_package(client, s, v, ["2030-01-12", "2030-01-19"])
    assert {t for _, t, _, _ in lesson_times(client, pkg["id"])} == {"18:00"}


def test_duplicate_session_date_rejected(client):
    s = create_student(client)["id"]
    v = create_venue(client)["id"]
    body = payload(s, v, sessions=[
        {"date": "2030-01-12", "start_time": "10:00:00"},
        {"date": "2030-01-12", "start_time": "12:00:00"},
    ])
    assert client.post("/api/packages", json=body).status_code == 400
