"""約課訊息解析主流程（app/booking_parser/service.py）的測試。全部用假的
ExtractionClient，不會真的呼叫 Anthropic API。
"""
from app import models
from app.booking_parser.service import MAX_RETRIES, parse_message
from app.database import SessionLocal
from app.models import BookingRequestStatus

from conftest import create_student


class FakeExtractionClient:
    name = "fake"
    model = "fake-model"

    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.calls: list[dict] = []
        self.last_latency_ms = 15
        self.last_input_tokens = 120
        self.last_output_tokens = 30

    def extract(self, text, reference_datetime, retry_errors=None):
        self.calls.append({"text": text, "retry_errors": retry_errors})
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx]


def _new_booking_raw(**overrides) -> dict:
    payload = {
        "intent": "new_booking",
        "student_name": None,
        "area": None,
        "windows": [{"date": {"day_offset": 1}, "part_of_day": "evening"}],
        "duration_minutes": None,
        "ambiguities": [],
    }
    payload.update(overrides)
    return payload


def test_第一次就成功且學生地區都比對得到時狀態是ok(client):
    student = create_student(client, name="王小明")
    fake = FakeExtractionClient([_new_booking_raw(student_name="王小明")])

    with SessionLocal() as db:
        result = parse_message(db, fake, "王小明想約明天晚上", reference_datetime=None)

    assert len(fake.calls) == 1
    assert result.retry_count == 0
    assert result.status == BookingRequestStatus.OK
    assert result.student_match.matched_student_id == student["id"]
    assert len(result.resolved_windows) == 1

    with SessionLocal() as db:
        row = db.get(models.BookingRequest, result.booking_request_id)
        assert row.status == BookingRequestStatus.OK
        assert row.retry_count == 0
        assert row.model == "fake-model"


def test_格式驗證失敗一次後第二次成功會重試且帶上錯誤訊息(client):
    bad = {"intent": "not-a-real-intent"}  # 不是合法的 Intent，會驗證失敗
    good = _new_booking_raw()
    fake = FakeExtractionClient([bad, good])

    with SessionLocal() as db:
        result = parse_message(db, fake, "隨便約一下", reference_datetime=None)

    assert len(fake.calls) == 2
    assert fake.calls[1]["retry_errors"] is not None  # 第二次呼叫要帶著上次的錯誤訊息
    assert result.retry_count == 1
    assert result.status == BookingRequestStatus.OK


def test_一直驗證失敗到重試用完會標記needs_review且不拋例外(client):
    bad = {"intent": "not-a-real-intent"}
    fake = FakeExtractionClient([bad, bad, bad])

    with SessionLocal() as db:
        result = parse_message(db, fake, "亂七八糟的訊息", reference_datetime=None)

    assert len(fake.calls) == MAX_RETRIES + 1
    assert result.retry_count == MAX_RETRIES
    assert result.status == BookingRequestStatus.NEEDS_REVIEW
    assert result.parsed is None


def test_日期換算失敗算驗證失敗也會重試(client):
    """刻意用 week_offset+weekday 組合算出過去日期，藉此驗證「schema 過了
    但日期換算失敗」也會觸發重試。"""
    past_window_raw = _new_booking_raw(windows=[{"date": {"week_offset": 0, "weekday": 1}}])
    good_raw = _new_booking_raw()
    fake = FakeExtractionClient([past_window_raw, good_raw])

    from datetime import datetime

    # 2026-09-30 是週三，「這週一」已經過了，會讓 resolve_window 丟
    # DateResolutionError，觸發重試
    ref = datetime.fromisoformat("2026-09-30T10:00:00+08:00")

    with SessionLocal() as db:
        result = parse_message(db, fake, "這週一晚上可以嗎", reference_datetime=ref)

    assert len(fake.calls) == 2
    assert result.retry_count == 1
    assert result.status == BookingRequestStatus.OK


def test_intent不是new_booking時狀態是not_booking(client):
    fake = FakeExtractionClient([{"intent": "other", "windows": [], "ambiguities": []}])

    with SessionLocal() as db:
        result = parse_message(db, fake, "教練最近好嗎", reference_datetime=None)

    assert result.status == BookingRequestStatus.NOT_BOOKING
    assert result.resolved_windows == []


def test_學生比對不到時狀態是needs_review(client):
    fake = FakeExtractionClient([_new_booking_raw(student_name="從沒見過的學生")])

    with SessionLocal() as db:
        result = parse_message(db, fake, "從沒見過的學生想約課", reference_datetime=None)

    assert result.status == BookingRequestStatus.NEEDS_REVIEW
    assert result.student_match.matched_student_id is None
    assert result.student_match.needs_review is True


def test_LLM自己列出ambiguity時狀態是needs_review(client):
    fake = FakeExtractionClient([_new_booking_raw(ambiguities=["不確定是哪個場地"])])

    with SessionLocal() as db:
        result = parse_message(db, fake, "隨便約一下", reference_datetime=None)

    assert result.status == BookingRequestStatus.NEEDS_REVIEW
    assert "不確定是哪個場地" in result.ambiguities
