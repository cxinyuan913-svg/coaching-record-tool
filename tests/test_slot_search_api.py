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
    assert [(b["start"], b["end"], b["venue_names"]) for b in body["open_blocks"]] == [
        ("2030-01-07T19:00:00", "2030-01-07T22:00:00", ["動智館"])
    ]
    # 給學生看的訊息不能有「接課」「空檔」「既有課程」這類內部用語
    assert body["message"] == (
        "我這幾個時段最方便：\n"
        "・1/7(一) 19:00-20:00 動智館\n"
        "\n"
        "其他有空的時段（場館可以選）：\n"
        "・1/7(一) 19:00-22:00 動智館"
    )


def test_leave_and_cancelled_free_the_slot(api):
    s = create_student(api)["id"]
    v = create_venue(api)["id"]
    add_lesson(s, v, time(18))
    add_lesson(s, v, time(19), status=models.LessonStatus.LEAVE)
    add_lesson(s, v, time(17), status=models.LessonStatus.CANCELLED)

    starts = [c["start"][11:16] for c in search(api, [v]).json()["anchored_candidates"]]
    assert starts == ["17:00", "19:00"]


def test_open_blocks_merge_venues_across_days(api):
    a = create_venue(api, "A館")["id"]
    b = create_venue(api, "B館")["id"]
    body = search(api, [a, b], date_to=date(2030, 1, 8), time_from="18:00", time_to="22:00", duration_minutes=120).json()
    assert body["anchored_candidates"] == []
    # 整點開始：18:00、19:00、20:00 都可以，兩小時的課最晚 22:00 下課；兩館時段相同合併成一行
    assert body["message"] == (
        "其他有空的時段（場館可以選）：\n"
        "・1/7(一) 18:00-22:00 A館、B館\n"
        "・1/8(二) 18:00-22:00 A館、B館"
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


# ---- 固定時段排課 POST /api/slot-search/recurring ----

def test_recurring_finds_weekly_slot_with_postpone_and_message(api):
    s = create_student(api)["id"]
    v = create_venue(api, "快羽會館")["id"]
    # 2030-01-07 是週一 → 第一個週六是 1/12；第二週（1/19）16:00 已經有課
    add_lesson(s, v, time(16), day=date(2030, 1, 19))
    res = api.post("/api/slot-search/recurring", json={
        "weekday": 5, "date_from": "2030-01-07", "weeks": 8,
        "time_from": "16:00", "time_to": "17:00", "venue_ids": [v],
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["first_date"] == "2030-01-12"
    [opt] = body["options"]
    assert opt["start_time"] == "16:00:00" and opt["venue_name"] == "快羽會館"
    assert [sk["date"] for sk in opt["skipped"]] == ["2030-01-19"]
    assert opt["dates"][0] == "2030-01-12" and opt["dates"][-1] == "2030-03-09"
    assert "撞到" in opt["skipped"][0]["reason"]
    assert "message" not in opt  # 給學生的訊息由前端用課程套組的格式組


def test_recurring_first_date_can_be_same_day(api):
    v = create_venue(api)["id"]
    body = api.post("/api/slot-search/recurring", json={
        "weekday": 0, "date_from": "2030-01-07", "weeks": 2, "venue_ids": [v],
    }).json()
    assert body["first_date"] == "2030-01-07"  # 起始日本身就是週一
    assert body["options"][0]["start_time"] == "08:00:00"


@pytest.mark.parametrize(
    "extra",
    [{"weekday": 7}, {"weeks": 21}, {"weeks": 0}, {"venue_ids": [999]}, {"time_from": "18:00", "time_to": "17:00"}],
)
def test_recurring_invalid_requests(api, extra):
    create_venue(api)
    body = {"weekday": 5, "date_from": "2030-01-07", "venue_ids": [1], **extra}
    assert api.post("/api/slot-search/recurring", json=body).status_code == 422


# ---- 指定時段逐週排排看 POST /api/slot-search/recurring/plan ----

def test_recurring_plan_week_by_week(api):
    s = create_student(api)["id"]
    v = create_venue(api, "快羽會館")["id"]
    add_lesson(s, v, time(8), day=date(2030, 1, 12))   # 第 1 週 8–9 有課 → 提示改 9–10 接課
    add_lesson(s, v, time(10), day=date(2030, 1, 19))  # 第 2 週 10–11 撞課 → 列替代時段
    res = api.post("/api/slot-search/recurring/plan", json={
        "weekday": 5, "date_from": "2030-01-07", "weeks": 8,
        "preferred_start": "10:00", "venue_id": v,
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["venue_name"] == "快羽會館" and body["preferred_end"] == "11:00:00"
    weeks = body["week_plans"]
    assert len(weeks) == 10  # 8 週 + 最多順延 2 週
    assert weeks[0]["preferred_ok"] and weeks[0]["suggestion"]["start_time"] == "09:00:00"
    assert weeks[0]["day_busy"][0]["venue_name"] == "快羽會館"
    assert not weeks[1]["preferred_ok"] and "撞到" in weeks[1]["preferred_reason"]
    assert [c["start_time"] for c in weeks[1]["alternatives"]][:2] == ["09:00:00", "11:00:00"]
    assert all(w["preferred_ok"] for w in weeks[2:])


def test_recurring_plan_unknown_venue(api):
    res = api.post("/api/slot-search/recurring/plan", json={
        "weekday": 5, "date_from": "2030-01-07", "preferred_start": "10:00", "venue_id": 999,
    })
    assert res.status_code == 422
