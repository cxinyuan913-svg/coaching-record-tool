"""套組批次排課、剩餘堂數重算、請假順延邏輯（見 SPEC.md 套組批次排課／請假順延）。"""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.models import AdjustmentType, LessonStatus, PackageStatus
from app.pricing import resolve_price


def generate_package_lessons(db: Session, package: models.Package) -> None:
    """依套組的起始日、週幾、時段，一次產生 total_sessions 筆 lessons。"""
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


def recompute_package_pricing(db: Session, package: models.Package) -> None:
    """依各堂實際時長比例重新分配套組總價（見對話紀錄：時長不同時金額按比例分攤）。

    以套組標準時長（session_duration）為 1 個單位，例如某堂時長是標準的 2 倍就算 2 個單位；
    所有非請假堂的單位數加總，總價除以單位總數得出「單位價」，每堂金額 = 單位價 × 自己的單位數。
    每次呼叫都會對套組內所有非請假堂重新分配（不保留舊金額），異動會反映到既有收入統計。
    """
    if not package.session_duration:
        return
    lessons = (
        db.query(models.Lesson)
        .filter(models.Lesson.package_id == package.id, models.Lesson.status != LessonStatus.LEAVE)
        .all()
    )
    total_units = sum(lesson.duration / package.session_duration for lesson in lessons)
    if total_units <= 0:
        return
    unit_price = package.total_price / total_units
    package.price_per_session = round(unit_price, 2)
    for lesson in lessons:
        lesson.revenue_amount = round(unit_price * (lesson.duration / package.session_duration), 2)


def mark_leave_and_reschedule(
    db: Session,
    lesson: models.Lesson,
    makeup_date=None,
    makeup_start_time=None,
) -> models.Lesson:
    """標記請假並順延一堂（見 SPEC.md 請假順延）。回傳新產生的順延 lesson。"""
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

    diff = resolve_price(db, student.tier, lesson.headcount) - resolve_price(db, student.tier, 1)
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
