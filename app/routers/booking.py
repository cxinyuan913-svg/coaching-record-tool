"""訂場檢查 API（見 SPEC.md 訂場開放時間）。"""
from datetime import date as date_type
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.models import BookingStatus, LessonStatus

router = APIRouter(prefix="/api/booking", tags=["booking"])


def _booking_open_at(lesson: models.Lesson, venue: models.Venue) -> datetime | None:
    """回傳開放訂場時刻；場地無 booking_open_days_before/time 設定時代表隨時可訂，回傳 None。"""
    if venue.booking_open_days_before is None or venue.booking_open_time is None:
        return None
    open_date = lesson.date - timedelta(days=venue.booking_open_days_before)
    return datetime.combine(open_date, venue.booking_open_time)


@router.get("/check", response_model=schemas.BookingCheckSummary)
def booking_check(db: Session = Depends(get_db)):
    from app.routers.lessons import _to_out as lesson_to_out

    now = datetime.now()
    lessons = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.status == LessonStatus.SCHEDULED,
            models.Lesson.date >= date_type.today(),  # 日期已過的課程不用再提醒訂場
        )
        .order_by(models.Lesson.date, models.Lesson.start_time)
        .all()
    )

    need_booking = []
    not_yet_open = []
    booked = []

    for lesson in lessons:
        open_at = _booking_open_at(lesson, lesson.venue)
        item = schemas.BookingCheckItem(lesson=lesson_to_out(lesson), booking_open_at=open_at)
        if lesson.booking_status == BookingStatus.BOOKED:
            booked.append(item)
        elif open_at is None or now >= open_at:
            need_booking.append(item)
        else:
            not_yet_open.append(item)

    return schemas.BookingCheckSummary(
        need_booking=need_booking, not_yet_open=not_yet_open, booked=booked
    )


@router.patch("/{lesson_id}", response_model=schemas.LessonOut)
def update_booking_status(
    lesson_id: int, payload: schemas.BookingStatusUpdate, db: Session = Depends(get_db)
):
    from app.routers.lessons import _to_out as lesson_to_out

    lesson = db.get(models.Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="課程不存在")
    lesson.booking_status = payload.booking_status
    lesson.booked_at = datetime.now() if payload.booking_status == BookingStatus.BOOKED else None
    db.commit()
    db.refresh(lesson)
    return lesson_to_out(lesson)
