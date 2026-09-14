"""包制批次排課、剩餘堂數重算、請假順延邏輯（見 SPEC.md 包制批次排課／請假順延）。"""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.models import LessonStatus, PackageStatus


def generate_package_lessons(db: Session, package: models.Package) -> None:
    """依包的起始日、週幾、時段，一次產生 total_sessions 筆 lessons。"""
    for i in range(package.total_sessions):
        lesson = models.Lesson(
            student_id=package.student_id,
            venue_id=package.default_venue_id,
            package_id=package.id,
            date=package.start_date + timedelta(weeks=i),
            start_time=package.recur_start_time,
            duration=package.session_duration,
            headcount=1,
            sequence_no=i + 1,
            status=LessonStatus.SCHEDULED,
            deduct_session=True,
            payment_status=package.payment_status,
            payment_date=package.payment_date,
            revenue_amount=package.price_per_session,
        )
        db.add(lesson)


def recompute_remaining_sessions(db: Session, package: models.Package) -> None:
    """剩餘堂數 = 總堂數 − 已扣堂（完成或取消且 deduct_session=True）的堂數。"""
    used = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.package_id == package.id,
            models.Lesson.deduct_session.is_(True),
            models.Lesson.status.in_([LessonStatus.COMPLETED, LessonStatus.CANCELLED]),
        )
        .count()
    )
    package.remaining_sessions = max(package.total_sessions - used, 0)
    if package.remaining_sessions == 0 and package.status == PackageStatus.ACTIVE:
        package.status = PackageStatus.COMPLETED
    elif package.remaining_sessions > 0 and package.status == PackageStatus.COMPLETED:
        package.status = PackageStatus.ACTIVE


def mark_leave_and_reschedule(
    db: Session,
    lesson: models.Lesson,
    makeup_date=None,
    makeup_start_time=None,
) -> models.Lesson:
    """標記請假並順延一堂（見 SPEC.md 請假順延）。回傳新產生的順延 lesson。"""
    package = db.get(models.Package, lesson.package_id)
    if package is None:
        raise HTTPException(status_code=400, detail="此堂非包制課程，無需順延")

    lesson.deduct_session = False
    lesson.revenue_amount = 0
    lesson.status = LessonStatus.LEAVE

    if makeup_date is None:
        last_date = (
            db.query(models.Lesson.date)
            .filter(models.Lesson.package_id == package.id)
            .order_by(models.Lesson.date.desc())
            .first()
        )[0]
        makeup_date = last_date + timedelta(weeks=1)
    if makeup_start_time is None:
        makeup_start_time = package.recur_start_time

    conflict = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.date == makeup_date,
            models.Lesson.start_time == makeup_start_time,
            models.Lesson.status != LessonStatus.CANCELLED,
            models.Lesson.id != lesson.id,
        )
        .first()
    )
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail=f"{makeup_date} {makeup_start_time} 已有其他課程，請指定其他順延時間",
        )

    makeup_lesson = models.Lesson(
        student_id=package.student_id,
        venue_id=package.default_venue_id,
        package_id=package.id,
        date=makeup_date,
        start_time=makeup_start_time,
        duration=package.session_duration,
        headcount=1,
        sequence_no=None,
        status=LessonStatus.SCHEDULED,
        deduct_session=True,
        makeup_for_lesson_id=lesson.id,
        payment_status=package.payment_status,
        payment_date=package.payment_date,
        revenue_amount=package.price_per_session,
    )
    db.add(makeup_lesson)
    recompute_remaining_sessions(db, package)
    return makeup_lesson
