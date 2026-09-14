"""課程 CRUD API。單堂制（package_id 為 NULL）可自由編輯金額與收款狀態；
套組課程（package_id 有值）的金額與收款狀態一律由所屬套組控管，並提供請假順延端點。"""
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.models import LessonStatus, PaymentStatus
from app.package_logic import (
    mark_leave_and_reschedule,
    recompute_package_pricing,
    recompute_remaining_sessions,
    sync_headcount_diff_adjustment,
)
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
        package_total_sessions=lesson.package.total_sessions if lesson.package_id else None,
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
        venue_fee_amount=lesson.venue_fee_amount,
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
    """僅建立單堂制課程；套組課程一律透過「新增套組」批次產生。"""
    student = db.get(models.Student, lesson.student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="學生不存在")
    venue = db.get(models.Venue, lesson.venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="場地不存在")

    revenue_amount = lesson.revenue_amount
    if revenue_amount is None:
        revenue_amount = resolve_price(db, student.tier, lesson.headcount, lesson.duration)

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
        venue_fee_amount=lesson.venue_fee_amount,
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

    is_package_lesson = db_lesson.package_id is not None

    if is_package_lesson and lesson.status == LessonStatus.LEAVE and db_lesson.status != LessonStatus.LEAVE:
        raise HTTPException(
            status_code=400,
            detail="套組課程請假請使用 /api/lessons/{id}/leave 端點（會自動順延一堂）",
        )

    was_leave = db_lesson.status == LessonStatus.LEAVE

    db_lesson.student_id = lesson.student_id
    db_lesson.venue_id = lesson.venue_id
    db_lesson.date = lesson.date
    db_lesson.start_time = lesson.start_time
    db_lesson.duration = lesson.duration
    db_lesson.headcount = lesson.headcount
    db_lesson.status = lesson.status
    db_lesson.venue_fee_amount = lesson.venue_fee_amount  # 場地費為代收代付，不受套組金額控管

    if is_package_lesson:
        if was_leave and lesson.status != LessonStatus.LEAVE:
            # 復原請假：移除當初順延補的那堂（若尚未上課過），並恢復扣堂
            makeup = (
                db.query(models.Lesson)
                .filter(
                    models.Lesson.makeup_for_lesson_id == db_lesson.id,
                    models.Lesson.status == LessonStatus.SCHEDULED,
                )
                .first()
            )
            if makeup is not None:
                db.delete(makeup)
            db_lesson.deduct_session = True

        # 套組課程的收款狀態一律隨套組；金額依該堂時長占套組總時長的比例重新分攤（見對話紀錄）
        package = db.get(models.Package, db_lesson.package_id)
        db_lesson.payment_status = package.payment_status
        db_lesson.payment_date = package.payment_date
        db.flush()  # 確保 recompute 查不到剛刪除的補課堂
        recompute_remaining_sessions(db, package)
        recompute_package_pricing(db, package)
        sync_headcount_diff_adjustment(db, db_lesson, student)
    else:
        if db_lesson.payment_status != lesson.payment_status:
            db_lesson.payment_date = (
                date_type.today() if lesson.payment_status == PaymentStatus.PAID else None
            )
        db_lesson.payment_status = lesson.payment_status
        db_lesson.revenue_amount = lesson.revenue_amount

    db.commit()
    db.refresh(db_lesson)
    return _to_out(db_lesson)


@router.post("/{lesson_id}/leave", response_model=schemas.LessonLeaveResult)
def leave_lesson(
    lesson_id: int, payload: schemas.LessonLeaveRequest, db: Session = Depends(get_db)
):
    """套組課程請假順延：標記該堂請假並自動產生順延一堂（見 SPEC.md 請假順延）。"""
    db_lesson = db.get(models.Lesson, lesson_id)
    if db_lesson is None:
        raise HTTPException(status_code=404, detail="課程不存在")
    if db_lesson.package_id is None:
        raise HTTPException(status_code=400, detail="單堂制課程無需順延，請直接編輯狀態")

    makeup_lesson = mark_leave_and_reschedule(
        db, db_lesson, payload.makeup_date, payload.makeup_start_time
    )
    db.commit()
    db.refresh(db_lesson)
    db.refresh(makeup_lesson)
    return schemas.LessonLeaveResult(
        leave_lesson=_to_out(db_lesson), makeup_lesson=_to_out(makeup_lesson)
    )


@router.patch("/{lesson_id}/payment", response_model=schemas.LessonOut)
def update_payment_status(
    lesson_id: int, payload: schemas.LessonPaymentUpdate, db: Session = Depends(get_db)
):
    db_lesson = db.get(models.Lesson, lesson_id)
    if db_lesson is None:
        raise HTTPException(status_code=404, detail="課程不存在")
    if db_lesson.package_id is not None:
        raise HTTPException(
            status_code=400, detail="套組課程的收款狀態請透過該套組的付款端點切換"
        )
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
    package_id = db_lesson.package_id
    db.delete(db_lesson)
    if package_id is not None:
        db.flush()  # 確保 recompute 查詢時已經看不到被刪除的這堂
        package = db.get(models.Package, package_id)
        if package is not None:
            recompute_remaining_sessions(db, package)
            recompute_package_pricing(db, package)
    db.commit()
