"""POST /api/booking-requests/parse 的整合測試（規格 1.7 的 Phase 1 完成
條件）。用 FastAPI 的 dependency override 換掉真正的 Anthropic client，
不會真的打 API、也不需要 ANTHROPIC_API_KEY。
"""
from app.main import app
from app.routers import booking_parser

from conftest import create_student
from test_booking_parser_service import FakeExtractionClient, _new_booking_raw


def _override_client(fake: FakeExtractionClient):
    app.dependency_overrides[booking_parser.get_extraction_client] = lambda: fake


def test_parse端點正常回傳解析結果(client):
    student = create_student(client, name="王小明")
    fake = FakeExtractionClient([_new_booking_raw(student_name="王小明")])
    _override_client(fake)
    try:
        res = client.post(
            "/api/booking-requests/parse",
            json={"text": "王小明想約明天晚上", "reference_datetime": "2026-09-28T10:00:00+08:00"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "ok"
        assert body["student_match"]["matched_student_id"] == student["id"]
        assert len(body["resolved_windows"]) == 1
    finally:
        app.dependency_overrides.pop(booking_parser.get_extraction_client, None)


def test_parse端點對驗證失敗的訊息回傳needs_review而不是500錯誤(client):
    fake = FakeExtractionClient([{"intent": "not-a-real-intent"}] * 3)
    _override_client(fake)
    try:
        res = client.post(
            "/api/booking-requests/parse",
            json={"text": "亂七八糟的訊息"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "needs_review"
    finally:
        app.dependency_overrides.pop(booking_parser.get_extraction_client, None)


def test_沒設定ANTHROPIC_API_KEY時回傳清楚的錯誤訊息而不是不知所云的例外(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = client.post("/api/booking-requests/parse", json={"text": "隨便一句話"})
    assert res.status_code == 500
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]
