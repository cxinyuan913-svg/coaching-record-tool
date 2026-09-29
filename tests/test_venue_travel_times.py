"""場館車程對照表 API 測試。"""
from tests.conftest import create_venue


def test_upsert_normalizes_order_and_updates(client):
    a = create_venue(client, "A館")["id"]
    b = create_venue(client, "B館")["id"]

    # 反方向送也要存成 a < b
    res = client.put("/api/venue-travel-times", json=[{"venue_a_id": b, "venue_b_id": a, "travel_minutes": 20}])
    assert res.status_code == 200, res.text
    assert res.json() == [{"venue_a_id": a, "venue_b_id": b, "travel_minutes": 20}]

    # 再送一次同一組是更新，不會多一筆
    client.put("/api/venue-travel-times", json=[{"venue_a_id": a, "venue_b_id": b, "travel_minutes": 30}])
    assert client.get("/api/venue-travel-times").json() == [
        {"venue_a_id": a, "venue_b_id": b, "travel_minutes": 30}
    ]


def test_none_deletes_pair(client):
    a = create_venue(client, "A館")["id"]
    b = create_venue(client, "B館")["id"]
    client.put("/api/venue-travel-times", json=[{"venue_a_id": a, "venue_b_id": b, "travel_minutes": 20}])
    res = client.put("/api/venue-travel-times", json=[{"venue_a_id": a, "venue_b_id": b, "travel_minutes": None}])
    assert res.json() == []


def test_invalid_items_reject_whole_batch(client):
    a = create_venue(client, "A館")["id"]
    b = create_venue(client, "B館")["id"]
    res = client.put(
        "/api/venue-travel-times",
        json=[
            {"venue_a_id": a, "venue_b_id": b, "travel_minutes": 20},
            {"venue_a_id": a, "venue_b_id": a, "travel_minutes": 5},
        ],
    )
    assert res.status_code == 422
    # 有一筆不合法，前面合法的那筆也不能寫進去
    assert client.get("/api/venue-travel-times").json() == []

    res = client.put("/api/venue-travel-times", json=[{"venue_a_id": a, "venue_b_id": 999, "travel_minutes": 5}])
    assert res.status_code == 422


def test_delete_venue_removes_its_travel_times(client):
    a = create_venue(client, "A館")["id"]
    b = create_venue(client, "B館")["id"]
    client.put("/api/venue-travel-times", json=[{"venue_a_id": a, "venue_b_id": b, "travel_minutes": 20}])
    assert client.delete(f"/api/venues/{b}").status_code == 204
    assert client.get("/api/venue-travel-times").json() == []
