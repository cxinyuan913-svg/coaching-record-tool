"""一次預訂多堂（單堂收費）的批次建立測試。

這個功能跟課程套組是不同概念：套組一次收一筆費用、每堂扣一次額度；
這裡每一堂都是各自獨立的單堂課，一律未收款、不掛套組，之後逐堂收費。
"""
from datetime import date, timedelta

from conftest import create_package, create_student, create_venue


def _batch_payload(student_id: int, venue_id: int, dates: list[str], **overrides) -> dict:
    payload = {
        "student_id": student_id,
        "venue_id": venue_id,
        "dates": dates,
        "start_time": "18:00:00",
        "duration": 60,
        "headcount": 1,
        "venue_fee_amount": 0,
    }
    payload.update(overrides)
    return payload


def test_批次建立多個日期的課程且每堂都獨立未收款不掛套組(client):
    """驗證行為：一次送 4 個日期，要建出 4 堂課，日期跟送出的一致，
    每一堂都是未收款、沒有掛套組、不扣任何套組額度。"""
    student = create_student(client, tier="new")
    venue = create_venue(client)
    start = date(2026, 11, 3)
    dates = [(start + timedelta(weeks=i)).isoformat() for i in range(4)]

    res = client.post("/api/lessons/batch", json=_batch_payload(student["id"], venue["id"], dates))
    assert res.status_code == 201, res.text
    result = res.json()

    assert result["created"] == 4
    assert [item["date"] for item in result["lessons"]] == dates
    for lesson in result["lessons"]:
        assert lesson["payment_status"] == "unpaid"
        assert lesson["package_id"] is None
        assert lesson["deduct_session"] is False
        assert lesson["sequence_no"] is None
        assert lesson["status"] == "scheduled"


def test_任一日期撞課時整批都不建立(client):
    """驗證行為：先有一堂 16:00-18:00 的課，批次裡有一天的 17:00 會跟它
    時段重疊（不是完全相同的開始時間），這時整批都不能建立——不可以
    「其他照建、只跳過撞到的那天」，資料庫裡只能剩原本那一堂。"""
    student = create_student(client, tier="new")
    venue = create_venue(client)
    clash_day = date(2026, 11, 10)

    existing = client.post(
        "/api/lessons",
        json={
            "student_id": student["id"],
            "venue_id": venue["id"],
            "date": clash_day.isoformat(),
            "start_time": "16:00:00",
            "duration": 120,
            "headcount": 1,
            "payment_status": "unpaid",
            "venue_fee_amount": 0,
        },
    )
    assert existing.status_code == 201, existing.text

    dates = [
        date(2026, 11, 3).isoformat(),
        clash_day.isoformat(),  # 17:00 開始，會卡進 16:00-18:00 的中間
        date(2026, 11, 17).isoformat(),
    ]
    res = client.post(
        "/api/lessons/batch",
        json=_batch_payload(student["id"], venue["id"], dates, start_time="17:00:00"),
    )
    assert res.status_code == 409, res.text
    assert clash_day.isoformat() in res.json()["detail"]

    all_lessons = client.get("/api/lessons").json()
    assert len(all_lessons) == 1
    assert all_lessons[0]["start_time"] == "16:00:00"


def test_撞到套組課程也會整批擋下(client):
    """驗證行為：撞課檢查不分課程來源，套組底下的課同樣會擋住批次建立。"""
    student = create_student(client, tier="new")
    venue = create_venue(client)
    package_day = date(2026, 11, 3)
    create_package(
        client,
        student["id"],
        venue["id"],
        [(package_day + timedelta(weeks=i)).isoformat() for i in range(2)],
    )

    res = client.post(
        "/api/lessons/batch",
        json=_batch_payload(student["id"], venue["id"], [package_day.isoformat()]),
    )
    assert res.status_code == 409, res.text


def test_重複選到同一天只會建立一堂(client):
    """驗證行為：日期清單裡有重複的同一天時，去重後只建立一堂，
    不會自己跟自己撞課。"""
    student = create_student(client, tier="new")
    venue = create_venue(client)
    day = date(2026, 11, 3).isoformat()

    res = client.post(
        "/api/lessons/batch", json=_batch_payload(student["id"], venue["id"], [day, day, day])
    )
    assert res.status_code == 201, res.text
    assert res.json()["created"] == 1


def test_沒指定金額時依學生身份別與人數查價目表帶入(client):
    """驗證行為：不給 revenue_amount 時，每一堂的金額都要依學生身份別與
    人數自動查價目表算出來（熟客 1 人 1 小時＝1200）。"""
    student = create_student(client, tier="regular")
    venue = create_venue(client)
    dates = [date(2026, 11, 3).isoformat(), date(2026, 11, 10).isoformat()]

    payload = _batch_payload(student["id"], venue["id"], dates)
    payload.pop("venue_fee_amount")
    res = client.post("/api/lessons/batch", json=payload)
    assert res.status_code == 201, res.text

    for lesson in res.json()["lessons"]:
        assert lesson["revenue_amount"] == 1200


def test_日期清單為空時回四百(client):
    """驗證行為：沒選任何日期就送出，要明確擋下來而不是建立 0 堂。"""
    student = create_student(client, tier="new")
    venue = create_venue(client)

    res = client.post("/api/lessons/batch", json=_batch_payload(student["id"], venue["id"], []))
    assert res.status_code == 400, res.text
