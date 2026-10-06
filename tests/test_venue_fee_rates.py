"""場館 × 時段場地費價目表：設定 API 與計價（公開預約網站用）。"""
from datetime import date, time

import pytest

from app.database import SessionLocal
from app.pricing import VenueFeeNotSet, compute_venue_fee
from conftest import create_venue

WEEKDAYS = [0, 1, 2, 3, 4]
WEEKEND = [5, 6]


def _set_rates(client, venue_id, items):
    return client.put(f"/api/venues/{venue_id}/fee-rates", json=items)


def _fee(venue_id, d, start, minutes):
    with SessionLocal() as db:
        return compute_venue_fee(db, venue_id, d, start, minutes)


def test_整批設定價目表後查得到且重設會整個取代(client):
    venue = create_venue(client)
    res = _set_rates(client, venue["id"], [
        {"weekdays": WEEKDAYS, "start_time": "08:00", "end_time": "18:00", "fee_per_hour": 300},
        {"weekdays": [4, 0, 4], "start_time": "18:00", "end_time": "23:00", "fee_per_hour": 450},
    ])
    assert res.status_code == 200, res.text
    assert len(res.json()) == 2
    assert {tuple(r["weekdays"]) for r in res.json()} == {(0, 1, 2, 3, 4), (0, 4)}

    res = _set_rates(client, venue["id"], [
        {"weekdays": WEEKEND, "start_time": "08:00", "end_time": "22:00", "fee_per_hour": 500},
    ])
    assert [r["fee_per_hour"] for r in res.json()] == [500]
    assert client.get(f"/api/venues/{venue['id']}/fee-rates").json() == res.json()


def test_同一星期時段重疊會整批擋下(client):
    venue = create_venue(client)
    _set_rates(client, venue["id"], [
        {"weekdays": WEEKDAYS, "start_time": "08:00", "end_time": "18:00", "fee_per_hour": 300},
    ])
    res = _set_rates(client, venue["id"], [
        {"weekdays": [0, 1], "start_time": "08:00", "end_time": "18:00", "fee_per_hour": 300},
        {"weekdays": [1, 2], "start_time": "17:00", "end_time": "22:00", "fee_per_hour": 450},
    ])
    assert res.status_code == 422
    assert "週二" in res.json()["detail"]
    # 原本的設定不受影響
    assert len(client.get(f"/api/venues/{venue['id']}/fee-rates").json()) == 1


def test_首尾相接不算重疊_不同星期同時段也可以(client):
    venue = create_venue(client)
    res = _set_rates(client, venue["id"], [
        {"weekdays": WEEKDAYS, "start_time": "08:00", "end_time": "18:00", "fee_per_hour": 300},
        {"weekdays": WEEKDAYS, "start_time": "18:00", "end_time": "23:00", "fee_per_hour": 450},
        {"weekdays": WEEKEND, "start_time": "08:00", "end_time": "23:00", "fee_per_hour": 500},
    ])
    assert res.status_code == 200, res.text


def test_欄位檢查(client):
    venue = create_venue(client)
    for bad in (
        {"weekdays": [], "start_time": "08:00", "end_time": "18:00", "fee_per_hour": 300},
        {"weekdays": [7], "start_time": "08:00", "end_time": "18:00", "fee_per_hour": 300},
        {"weekdays": [0], "start_time": "18:00", "end_time": "08:00", "fee_per_hour": 300},
        {"weekdays": [0], "start_time": "08:00", "end_time": "18:00", "fee_per_hour": -1},
    ):
        assert _set_rates(client, venue["id"], [bad]).status_code == 422, bad
    assert _set_rates(client, 9999, []).status_code == 404


def test_場地費依時段計價且跨時段按分鐘比例(client):
    venue = create_venue(client)
    _set_rates(client, venue["id"], [
        {"weekdays": WEEKDAYS, "start_time": "08:00", "end_time": "18:00", "fee_per_hour": 300},
        {"weekdays": WEEKDAYS, "start_time": "18:00", "end_time": "23:00", "fee_per_hour": 450},
        {"weekdays": WEEKEND, "start_time": "08:00", "end_time": "23:00", "fee_per_hour": 500},
    ])
    tuesday, saturday = date(2026, 10, 13), date(2026, 10, 17)
    assert _fee(venue["id"], tuesday, time(10, 0), 60) == 300
    assert _fee(venue["id"], tuesday, time(19, 0), 90) == 675
    assert _fee(venue["id"], tuesday, time(17, 30), 60) == 375  # 半小時 300 價 + 半小時 450 價
    assert _fee(venue["id"], saturday, time(17, 30), 60) == 500


def test_價目表沒涵蓋到的時段不猜預設值(client):
    venue = create_venue(client, name="快羽會館")
    _set_rates(client, venue["id"], [
        {"weekdays": WEEKDAYS, "start_time": "08:00", "end_time": "18:00", "fee_per_hour": 300},
    ])
    with pytest.raises(VenueFeeNotSet, match="快羽會館"):
        _fee(venue["id"], date(2026, 10, 13), time(17, 30), 60)  # 18:00 之後沒設定
    with pytest.raises(VenueFeeNotSet):
        _fee(venue["id"], date(2026, 10, 17), time(10, 0), 60)  # 週末沒設定


def test_刪除場地會一併刪除價目表(client):
    venue = create_venue(client)
    _set_rates(client, venue["id"], [
        {"weekdays": WEEKDAYS, "start_time": "08:00", "end_time": "18:00", "fee_per_hour": 300},
    ])
    assert client.delete(f"/api/venues/{venue['id']}").status_code == 204
    from app import models
    with SessionLocal() as db:
        assert db.query(models.VenueFeeRate).count() == 0
