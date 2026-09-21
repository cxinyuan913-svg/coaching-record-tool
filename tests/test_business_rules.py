"""核心業務規則的自動化測試。

每一個測試都是獨立的（見 conftest.py 的 client fixture，每個測試前都會
重建一份乾淨資料庫），不依賴其他測試先跑過、也不依賴執行順序。
"""
from datetime import date, timedelta

import pytest

from conftest import create_package, create_student, create_venue


def test_建立套組後正確產生連續八週的課程並依序編號(client):
    """驗證行為：新增一個 8 堂的套組之後，底下要剛好產生 8 筆課程，日期
    要跟建立時選的日期一致、全部落在同一個星期幾、而且依日期順序編號
    第 1 堂到第 8 堂。"""
    student = create_student(client, tier="new")
    venue = create_venue(client)
    start = date(2026, 10, 6)  # 星期二
    dates = [(start + timedelta(weeks=i)).isoformat() for i in range(8)]

    package = create_package(client, student["id"], venue["id"], dates)
    assert package["total_sessions"] == 8

    lessons = client.get(f"/api/packages/{package['id']}/lessons").json()
    lessons.sort(key=lambda item: item["date"])

    assert len(lessons) == 8
    assert [item["date"] for item in lessons] == dates
    weekdays = {date.fromisoformat(item["date"]).weekday() for item in lessons}
    assert weekdays == {start.weekday()}
    assert [item["sequence_no"] for item in lessons] == list(range(1, 9))


def test_請假不扣堂數且自動順延補課(client):
    """驗證行為：把某堂標記請假之後——那一堂不應該再算進「已用掉」的堂
    數（`remaining_sessions` 不變）、那一堂的金額要歸零；同時系統要在
    套組目前最後一堂的下一週自動新增一筆補課，補課要標明它是從哪一堂
    請假順延過來的（`makeup_for_lesson_id`）。"""
    student = create_student(client)
    venue = create_venue(client)
    # 用未來日期，確保不會被「日期已過就自動算用掉」的規則干擾這個測試
    start = date.today() + timedelta(days=60)
    dates = [(start + timedelta(weeks=i)).isoformat() for i in range(3)]
    package = create_package(client, student["id"], venue["id"], dates)

    lessons = client.get(f"/api/packages/{package['id']}/lessons").json()
    lessons.sort(key=lambda item: item["date"])
    target = lessons[0]
    last_date = date.fromisoformat(lessons[-1]["date"])

    remaining_before = client.get(f"/api/packages/{package['id']}").json()["remaining_sessions"]

    res = client.post(f"/api/lessons/{target['id']}/leave", json={})
    assert res.status_code == 200, res.text
    result = res.json()

    assert result["leave_lesson"]["status"] == "leave"
    assert result["leave_lesson"]["deduct_session"] is False
    assert result["leave_lesson"]["revenue_amount"] == 0

    assert result["makeup_lesson"]["makeup_for_lesson_id"] == target["id"]
    assert result["makeup_lesson"]["status"] == "scheduled"
    assert result["makeup_lesson"]["date"] == (last_date + timedelta(weeks=1)).isoformat()

    remaining_after = client.get(f"/api/packages/{package['id']}").json()["remaining_sessions"]
    assert remaining_after == remaining_before


@pytest.mark.parametrize(
    "tier,headcount,duration,expected",
    [
        ("new", 1, 60, 1600),
        ("friend", 1, 60, 1400),
        ("regular", 1, 60, 1200),
        ("new", 2, 60, 1800),
        ("friend", 2, 60, 1600),
        ("regular", 2, 60, 1400),
        ("new", 3, 60, 1800),
        ("regular", 5, 60, 1500),
        ("friend", 3, 60, 1500),  # edge case：3 人以上查無朋友價，退回熟客價 1500
        ("regular", 1, 120, 2400),  # 時長是 2 小時，金額要跟著乘 2 倍
    ],
)
def test_價目表依人數與等級算出正確金額(client, tier, headcount, duration, expected):
    """驗證行為：不同人數／等級／時長組合，查出來的金額要跟價目表定義
    的完全一致，特別是「3 人以上找不到朋友價時要退回熟客價 1500」這個
    例外規則。"""
    res = client.get(
        f"/api/price_rules/resolve?tier={tier}&headcount={headcount}&duration={duration}"
    )
    assert res.status_code == 200, res.text
    assert res.json()["price"] == expected


def test_套組課程改兩人時產生正確金額的人數差額且該堂攤提金額不變(client):
    """驗證行為：套組課程原本是以單人價預收的，如果某一堂臨時改成 2 人
    上課，系統要另外產生一筆「人數差額」的額外費用（金額＝該學生等級
    的 2 人價減 1 人價），而且這一堂原本的攤提金額不能因此被改動——多
    收的錢要透過額外費用另外記，不能污染套組本身的攤提金額。"""
    student = create_student(client, tier="new")
    venue = create_venue(client)
    start = date.today() + timedelta(days=30)
    package = create_package(
        client,
        student["id"],
        venue["id"],
        [start.isoformat()],
        coach_fee_per_hour=1000,
        venue_fee_per_hour=0,
    )

    lesson = client.get(f"/api/packages/{package['id']}/lessons").json()[0]
    original_revenue = lesson["revenue_amount"]

    res = client.put(
        f"/api/lessons/{lesson['id']}",
        json={
            "student_id": lesson["student_id"],
            "venue_id": lesson["venue_id"],
            "date": lesson["date"],
            "start_time": lesson["start_time"],
            "duration": lesson["duration"],
            "headcount": 2,
            "payment_status": lesson["payment_status"],
            "revenue_amount": lesson["revenue_amount"],
            "venue_fee_amount": lesson["venue_fee_amount"],
            "status": lesson["status"],
        },
    )
    assert res.status_code == 200, res.text
    updated = res.json()

    assert updated["revenue_amount"] == original_revenue

    adjustments = client.get(f"/api/adjustments?lesson_id={lesson['id']}").json()
    diff_adjustments = [item for item in adjustments if item["type"] == "headcount_diff"]
    assert len(diff_adjustments) == 1
    # tier=new：2 人價 1800 - 1 人價 1600 = 200（時長剛好 60 分鐘，不用再比例換算）
    assert diff_adjustments[0]["amount"] == 200


def test_收入統計只加總已收款未取消的課程與已結清的差額(client):
    """驗證行為：總收入只能包含「已收款」而且「沒有被取消」的課程金額，
    加上「已結清」的額外費用；未收款的課程、已取消的課程（即使標記已
    收款）、還沒結清的額外費用，都不應該被算進收入數字。"""
    student = create_student(client)
    venue = create_venue(client)
    today = date.today().isoformat()

    def make_lesson(payment_status: str, revenue: float, status: str | None = None) -> dict:
        res = client.post(
            "/api/lessons",
            json={
                "student_id": student["id"],
                "venue_id": venue["id"],
                "date": today,
                "start_time": "10:00:00",
                "duration": 60,
                "headcount": 1,
                "payment_status": payment_status,
                "revenue_amount": revenue,
                "venue_fee_amount": 0,
            },
        )
        assert res.status_code == 201, res.text
        lesson = res.json()
        if status is not None:
            res = client.put(
                f"/api/lessons/{lesson['id']}",
                json={
                    "student_id": lesson["student_id"],
                    "venue_id": lesson["venue_id"],
                    "date": lesson["date"],
                    "start_time": lesson["start_time"],
                    "duration": lesson["duration"],
                    "headcount": lesson["headcount"],
                    "payment_status": lesson["payment_status"],
                    "revenue_amount": lesson["revenue_amount"],
                    "venue_fee_amount": lesson["venue_fee_amount"],
                    "status": status,
                },
            )
            assert res.status_code == 200, res.text
            lesson = res.json()
        return lesson

    paid_lesson = make_lesson("paid", 1000)  # 應該算入
    make_lesson("unpaid", 2000)  # 未收款，不應該算入
    make_lesson("paid", 3000, status="cancelled")  # 已收款但已取消，不應該算入

    res = client.post(
        "/api/adjustments",
        json={"lesson_id": paid_lesson["id"], "type": "other", "amount": 500, "note": "已結清"},
    )
    settled = res.json()
    client.patch(f"/api/adjustments/{settled['id']}/settle")

    client.post(
        "/api/adjustments",
        json={"lesson_id": paid_lesson["id"], "type": "other", "amount": 700, "note": "未結清"},
    )

    res = client.get("/api/stats/revenue")
    assert res.status_code == 200
    assert res.json()["total"] == 1000 + 500


def test_刪除有額外費用的課程不會因為外鍵限制而失敗(client):
    """驗證行為：一堂課如果掛了額外費用（例如臨時加收），刪除這堂課時要
    連同底下的額外費用一起刪掉。adjustments.lesson_id 是 NOT NULL，如果
    刪除課程時沒有先清掉關聯的額外費用，ORM 想把外鍵設成 NULL 會直接違反
    資料庫限制，讓整個刪除動作失敗（曾經實際發生過的 bug）。"""
    student = create_student(client)
    venue = create_venue(client)
    res = client.post(
        "/api/lessons",
        json={
            "student_id": student["id"],
            "venue_id": venue["id"],
            "date": "2026-10-01",
            "start_time": "18:00:00",
            "duration": 60,
            "headcount": 1,
            "payment_status": "unpaid",
            "revenue_amount": 1000,
            "venue_fee_amount": 0,
        },
    )
    lesson_id = res.json()["id"]

    res = client.post(
        "/api/adjustments",
        json={"lesson_id": lesson_id, "type": "other", "amount": 200, "note": "臨時加收"},
    )
    assert res.status_code == 201

    res = client.delete(f"/api/lessons/{lesson_id}")
    assert res.status_code == 204, res.text

    assert client.get("/api/adjustments").json() == []


def _package_update_payload(package: dict, **overrides) -> dict:
    payload = {
        "name": package["name"],
        "session_duration": package["session_duration"],
        "total_sessions": package["total_sessions"],
        "coach_fee_per_hour": package["coach_fee_per_hour"],
        "venue_fee_per_hour": package["venue_fee_per_hour"],
        "purchased_date": package["purchased_date"],
        "start_date": package["start_date"],
        "recur_weekday": package["recur_weekday"],
        "recur_start_time": package["recur_start_time"],
        "default_venue_id": package["default_venue_id"],
    }
    payload.update(overrides)
    return payload


def test_套組總堂數不能改得比已經排定的堂數還少(client):
    """驗證行為：一個套組如果已經有 3 堂課掛在上面，把 total_sessions 改
    成比 3 小的數字要被擋下來（400），改成剛好等於已排堂數則允許——避免
    套組欄位說「只剩 N 堂」，但行事曆上其實還有更多堂沒被算進去的資料
    不一致（曾經實際發生過的 bug）。"""
    student = create_student(client)
    venue = create_venue(client)
    start = date.today() + timedelta(days=30)
    dates = [(start + timedelta(weeks=i)).isoformat() for i in range(3)]
    package = create_package(client, student["id"], venue["id"], dates)
    assert package["total_sessions"] == 3

    res = client.put(
        f"/api/packages/{package['id']}",
        json=_package_update_payload(package, total_sessions=2),
    )
    assert res.status_code == 400, res.text

    res = client.put(
        f"/api/packages/{package['id']}",
        json=_package_update_payload(package, total_sessions=3),
    )
    assert res.status_code == 200, res.text


def test_連環請假後復原最早那堂會清掉整條補課鏈(client):
    """驗證行為：A 請假產生補課 B，B 自己又請假產生補課 C，這時候把最早
    的 A 復原回正常上課，系統要把整條鏈（B、C）都清掉，不能只看「A 直接
    補的那一堂」——曾經實際發生過只清到 B 這一層、C 留在資料庫裡造成套
    組堂數被多佔用的 bug。"""
    student = create_student(client)
    venue = create_venue(client)
    start = date.today() + timedelta(days=60)
    package = create_package(client, student["id"], venue["id"], [start.isoformat()], total_sessions=1)

    lesson_a = client.get(f"/api/packages/{package['id']}/lessons").json()[0]

    res = client.post(f"/api/lessons/{lesson_a['id']}/leave", json={})
    assert res.status_code == 200, res.text
    lesson_b = res.json()["makeup_lesson"]

    res = client.post(f"/api/lessons/{lesson_b['id']}/leave", json={})
    assert res.status_code == 200, res.text
    lesson_c = res.json()["makeup_lesson"]

    # 把 A 復原回正常上課
    res = client.put(
        f"/api/lessons/{lesson_a['id']}",
        json={
            "student_id": lesson_a["student_id"],
            "venue_id": lesson_a["venue_id"],
            "date": lesson_a["date"],
            "start_time": lesson_a["start_time"],
            "duration": lesson_a["duration"],
            "headcount": lesson_a["headcount"],
            "payment_status": lesson_a["payment_status"],
            "revenue_amount": lesson_a["revenue_amount"],
            "venue_fee_amount": lesson_a["venue_fee_amount"],
            "status": "scheduled",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["deduct_session"] is True

    remaining_ids = {item["id"] for item in client.get(f"/api/packages/{package['id']}/lessons").json()}
    assert remaining_ids == {lesson_a["id"]}
    assert client.get(f"/api/lessons/{lesson_b['id']}").status_code == 404
    assert client.get(f"/api/lessons/{lesson_c['id']}").status_code == 404


def test_補課鏈裡有堂已完成時復原請假會被擋下不自動刪除(client):
    """驗證行為：A 請假產生補課 B，B 已經被標記完成（代表真的上過課、
    可能也收過錢），這時候如果把 A 復原回正常上課，系統不能自動把 B 刪
    掉（會憑空消滅一筆已經發生的歷史紀錄），要擋下來（409）讓人工處理。"""
    student = create_student(client)
    venue = create_venue(client)
    start = date.today() + timedelta(days=60)
    package = create_package(client, student["id"], venue["id"], [start.isoformat()], total_sessions=1)

    lesson_a = client.get(f"/api/packages/{package['id']}/lessons").json()[0]

    res = client.post(f"/api/lessons/{lesson_a['id']}/leave", json={})
    assert res.status_code == 200, res.text
    lesson_b = res.json()["makeup_lesson"]

    res = client.put(
        f"/api/lessons/{lesson_b['id']}",
        json={
            "student_id": lesson_b["student_id"],
            "venue_id": lesson_b["venue_id"],
            "date": lesson_b["date"],
            "start_time": lesson_b["start_time"],
            "duration": lesson_b["duration"],
            "headcount": lesson_b["headcount"],
            "payment_status": lesson_b["payment_status"],
            "revenue_amount": lesson_b["revenue_amount"],
            "venue_fee_amount": lesson_b["venue_fee_amount"],
            "status": "completed",
        },
    )
    assert res.status_code == 200, res.text

    res = client.put(
        f"/api/lessons/{lesson_a['id']}",
        json={
            "student_id": lesson_a["student_id"],
            "venue_id": lesson_a["venue_id"],
            "date": lesson_a["date"],
            "start_time": lesson_a["start_time"],
            "duration": lesson_a["duration"],
            "headcount": lesson_a["headcount"],
            "payment_status": lesson_a["payment_status"],
            "revenue_amount": lesson_a["revenue_amount"],
            "venue_fee_amount": lesson_a["venue_fee_amount"],
            "status": "scheduled",
        },
    )
    assert res.status_code == 409, res.text

    assert client.get(f"/api/lessons/{lesson_b['id']}").json()["status"] == "completed"
