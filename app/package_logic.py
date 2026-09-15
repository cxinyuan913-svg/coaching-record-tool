"""套組批次排課、剩餘堂數重算、請假順延邏輯（見 SPEC.md 套組批次排課／請假順延）。"""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.models import AdjustmentType, LessonStatus, PackageStatus
from app.pricing import resolve_price


def generate_package_lessons(db: Session, package: models.Package) -> None:
    """依套組的起始日、週幾、時段，一次產生 total_sessions 筆 lessons。"""
    hours = package.session_duration / 60
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
            revenue_amount=round(package.coach_fee_per_hour * hours, 2),
            venue_fee_amount=round(package.venue_fee_per_hour * hours, 2),
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


def recompute_package_pricing(db: Session, package: models.Package) -> None:
    """依「堂課費／場地費（每小時）」費率與各堂實際時長，重新算出每堂金額與套組總價。

    每堂互不影響：堂課費 = coach_fee_per_hour × 時長(小時)，場地費 = venue_fee_per_hour × 時長(小時)。
    某堂時長變長只會讓那一堂變貴，不會動到其他堂。price_per_session／total_price 為依標準時長／
    目前所有非請假堂加總算出的參考值，供畫面顯示「這堂大概多少錢」「總共要收多少」用。
    """
    lessons = (
        db.query(models.Lesson)
        .filter(models.Lesson.package_id == package.id, models.Lesson.status != LessonStatus.LEAVE)
        .all()
    )
    for lesson in lessons:
        hours = lesson.duration / 60
        lesson.revenue_amount = round(package.coach_fee_per_hour * hours, 2)
        lesson.venue_fee_amount = round(package.venue_fee_per_hour * hours, 2)

    standard_hours = package.session_duration / 60 if package.session_duration else 0
    package.price_per_session = round(
        (package.coach_fee_per_hour + package.venue_fee_per_hour) * standard_hours, 2
    )
    package.total_price = round(
        sum(lesson.revenue_amount + lesson.venue_fee_amount for lesson in lessons), 2
    )


def mark_leave_and_reschedule(
    db: Session,
    lesson: models.Lesson,
    makeup_date=None,
    makeup_start_time=None,
) -> models.Lesson:
    """標記請假並在套組目前最後一堂的下一週補一堂（見 SPEC.md 請假順延）。"""
    package = db.get(models.Package, lesson.package_id)
    if package is None:
        raise HTTPException(status_code=400, detail="此堂非套組課程，無需順延")

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
    db.flush()  # 確保 recompute 能查到剛新增的 makeup_lesson
    recompute_remaining_sessions(db, package)
    recompute_package_pricing(db, package)
    return makeup_lesson


def sync_headcount_diff_adjustment(
    db: Session, lesson: models.Lesson, student: models.Student
) -> None:
    """套組以單人價預收，人數改為 N 人時自動算出差額（見 SPEC.md 人數差額）。"""
    existing = (
        db.query(models.Adjustment)
        .filter(
            models.Adjustment.lesson_id == lesson.id,
            models.Adjustment.type == AdjustmentType.HEADCOUNT_DIFF,
            models.Adjustment.settled.is_(False),
        )
        .first()
    )
    if lesson.headcount <= 1:
        if existing is not None:
            db.delete(existing)
        return

    diff = resolve_price(db, student.tier, lesson.headcount, lesson.duration) - resolve_price(
        db, student.tier, 1, lesson.duration
    )
    if existing is not None:
        existing.amount = diff
    else:
        db.add(
            models.Adjustment(
                lesson_id=lesson.id,
                package_id=lesson.package_id,
                type=AdjustmentType.HEADCOUNT_DIFF,
                amount=diff,
                note="人數差額（自動計算）",
                settled=False,
            )
        )
