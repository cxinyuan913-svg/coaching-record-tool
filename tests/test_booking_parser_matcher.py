"""學生/地區本地比對（app/booking_parser/matcher.py）的測試。"""
from app import models
from app.booking_parser.matcher import match_area, match_student
from app.database import SessionLocal

from conftest import create_student, create_venue


def test_姓名完全相符時直接比對成功不需要人工確認(client):
    student = create_student(client, name="王小明")
    create_student(client, name="陳大文")

    with SessionLocal() as db:
        result = match_student(db, "王小明")

    assert result.matched_student_id == student["id"]
    assert result.match_type == "exact"
    assert result.needs_review is False


def test_姓名重複時回傳候選清單並標記需要人工確認(client):
    a = create_student(client, name="王小明")
    b = create_student(client, name="王小明")

    with SessionLocal() as db:
        result = match_student(db, "王小明")

    assert result.matched_student_id is None
    assert result.needs_review is True
    assert set(result.candidates) == {a["id"], b["id"]}


def test_別名比對成功(client):
    student = create_student(client, name="王小明")
    with SessionLocal() as db:
        db.add(models.StudentAlias(student_id=student["id"], alias="小明"))
        db.commit()

        result = match_student(db, "小明")

    assert result.matched_student_id == student["id"]
    assert result.match_type == "alias"
    assert result.needs_review is False


def test_模糊比對即使只有一個候選也標記需要人工確認不自動選(client):
    student = create_student(client, name="王小明")

    with SessionLocal() as db:
        result = match_student(db, "王曉明")  # 差一個同音字，應該落在模糊比對門檻內

    assert result.matched_student_id is None
    assert result.needs_review is True
    assert result.candidates == [student["id"]]


def test_完全找不到相符的學生(client):
    create_student(client, name="王小明")

    with SessionLocal() as db:
        result = match_student(db, "完全不相關的名字XYZ")

    assert result.matched_student_id is None
    assert result.needs_review is True
    assert result.candidates == []


def test_地區比對成功且可以對應多個場地(client):
    venue_a = create_venue(client, name="場地A")
    venue_b = create_venue(client, name="場地B")
    create_venue(client, name="場地C")  # 不屬於竹北，不該出現在結果裡

    with SessionLocal() as db:
        db.add(models.VenueArea(venue_id=venue_a["id"], area="竹北"))
        db.add(models.VenueArea(venue_id=venue_b["id"], area="竹北"))
        db.commit()

        result = match_area(db, "竹北")

    assert set(result.matched_venue_ids) == {venue_a["id"], venue_b["id"]}
    assert result.needs_review is False


def test_地區比對不到時標記需要人工確認(client):
    with SessionLocal() as db:
        result = match_area(db, "從沒設定過的地區")

    assert result.matched_venue_ids == []
    assert result.needs_review is True
