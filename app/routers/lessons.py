"""課程 CRUD API（階段一：僅單堂制，package_id 固定為 NULL）。"""
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.models import PaymentStatus
from app.pricing import resolve_price

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


def _to_out(lesson: models.Lesson) -> schemas.LessonOut:
    return schemas.LessonOut(
        id=lesson.id,
        student_id=lesson.student_id,
        student_name=lesson.student.name,
        venue_id=lesson.venue_id,
        venue_name=lesson.venue.name,
        package_id=lesson.package_id,
        date=lesson.date,
        start_time=lesson.start_time,
        duration=lesson.duration,
        headcount=lesson.headcount,
        sequence_no=lesson.sequence_no,
        status=lesson.status,
        deduct_session=lesson.deduct_session,
        makeup_for_lesson_id=lesson.makeup_for_lesson_id,
        booking_status=lesson.booking_status,
        booked_at=lesson.booked_at,
        payment_status=lesson.payment_status,
        payment_date=lesson.payment_date,
        revenue_amount=lesson.revenue_amount,
    )


@router.get("", response_model=list[schemas.LessonOut])
def list_lessons(
    start: date_type | None = Query(None, description="篩選起始日期（含）"),
    end: date_type | None = Query(None, description="篩選結束日期（含）"),
    db: Session = Depends(get_db),
):
    query = db.query(models.Lesson)
    if start is not None:
        query = query.filter(models.Lesson.date >= start)
    if end is not None:
        query = query.filter(models.Lesson.date <= end)
    lessons = query.order_by(models.Lesson.date, models.Lesson.start_time).all()
    return [_to_out(lesson) for lesson in lessons]


@router.post("", response_model=schemas.LessonOut, status_code=201)
def create_lesson(lesson: schemas.LessonCreate, db: Session = Depends(get_db)):
    student = db.get(models.Student, lesson.student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="學生不存在")
    venue = db.get(models.Venue, lesson.venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="場地不存在")

    revenue_amount = lesson.revenue_amount
    if revenue_amount is None:
        revenue_amount = resolve_price(db, student.tier, lesson.headcount)

    db_lesson = models.Lesson(
        student_id=lesson.student_id,
        venue_id=lesson.venue_id,
        package_id=None,
        date=lesson.date,
        start_time=lesson.start_time,
        duration=lesson.duration,
        headcount=lesson.headcount,
        payment_status=lesson.payment_status,
        payment_date=date_type.today() if lesson.payment_status == PaymentStatus.PAID else None,
        revenue_amount=revenue_amount,
    )
    db.add(db_lesson)
    db.commit()
    db.refresh(db_lesson)
    return _to_out(db_lesson)


@router.get("/{lesson_id}", response_model=schemas.LessonOut)
def get_lesson(lesson_id: int, db: Session = Depends(get_db)):
    lesson = db.get(models.Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="課程不存在")
    return _to_out(lesson)


@router.put("/{lesson_id}", response_model=schemas.LessonOut)
def update_lesson(lesson_id: int, lesson: schemas.LessonUpdate, db: Session = Depends(get_db)):
    db_lesson = db.get(models.Lesson, lesson_id)
    if db_lesson is None:
        raise HTTPException(status_code=404, detail="課程不存在")
    student = db.get(models.Student, lesson.student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="學生不存在")
    venue = db.get(models.Venue, lesson.venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="場地不存在")

    if db_lesson.payment_status != lesson.payment_status:
        db_lesson.payment_date = (
            date_type.today() if lesson.payment_status == PaymentStatus.PAID else None
        )

    db_lesson.student_id = lesson.student_id
    db_lesson.venue_id = lesson.venue_id
    db_lesson.date = lesson.date
    db_lesson.start_time = lesson.start_time
    db_lesson.duration = lesson.duration
    db_lesson.headcount = lesson.headcount
    db_lesson.status = lesson.status
    db_lesson.payment_status = lesson.payment_status
    db_lesson.revenue_amount = lesson.revenue_amount

    db.commit()
    db.refresh(db_lesson)
    return _to_out(db_lesson)


@router.patch("/{lesson_id}/payment", response_model=schemas.LessonOut)
def update_payment_status(
    lesson_id: int, payload: schemas.LessonPaymentUpdate, db: Session = Depends(get_db)
):
    db_lesson = db.get(models.Lesson, lesson_id)
    if db_lesson is None:
        raise HTTPException(status_code=404, detail="課程不存在")
    db_lesson.payment_status = payload.payment_status
    db_lesson.payment_date = (
        date_type.today() if payload.payment_status == PaymentStatus.PAID else None
    )
    db.commit()
    db.refresh(db_lesson)
    return _to_out(db_lesson)


@router.delete("/{lesson_id}", status_code=204)
def delete_lesson(lesson_id: int, db: Session = Depends(get_db)):
    db_lesson = db.get(models.Lesson, lesson_id)
    if db_lesson is None:
        raise HTTPException(status_code=404, detail="課程不存在")
    db.delete(db_lesson)
    db.commit()
