"""收入統計與未收款清單 API（見 SPEC.md 收入統計／未收款清單）。"""
from datetime import date as date_type
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.models import LessonStatus, PackageStatus, PaymentStatus

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _sum_lessons(db: Session, start: date_type | None, end: date_type | None) -> float:
    query = db.query(func.coalesce(func.sum(models.Lesson.revenue_amount), 0)).filter(
        models.Lesson.payment_status == PaymentStatus.PAID,
        models.Lesson.status != LessonStatus.CANCELLED,
    )
    if start is not None:
        query = query.filter(models.Lesson.date >= start)
    if end is not None:
        query = query.filter(models.Lesson.date <= end)
    return query.scalar()


def _sum_adjustments(db: Session, start: date_type | None, end: date_type | None) -> float:
    query = db.query(func.coalesce(func.sum(models.Adjustment.amount), 0)).filter(
        models.Adjustment.settled.is_(True)
    )
    if start is not None:
        query = query.filter(func.date(models.Adjustment.settled_at) >= start)
    if end is not None:
        query = query.filter(func.date(models.Adjustment.settled_at) <= end)
    return query.scalar()


def _revenue(db: Session, start: date_type | None, end: date_type | None) -> float:
    return _sum_lessons(db, start, end) + _sum_adjustments(db, start, end)


@router.get("/revenue", response_model=schemas.RevenueStats)
def revenue_stats(db: Session = Depends(get_db)):
    today = date_type.today()
    week_start = today - timedelta(days=today.weekday())  # 週一為週起始
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)
    next_month_start = (
        month_start.replace(year=month_start.year + 1, month=1)
        if month_start.month == 12
        else month_start.replace(month=month_start.month + 1)
    )
    month_end = next_month_start - timedelta(days=1)
    year_start = today.replace(month=1, day=1)
    year_end = today.replace(month=12, day=31)

    return schemas.RevenueStats(
        week=_revenue(db, week_start, week_end),
        month=_revenue(db, month_start, month_end),
        year=_revenue(db, year_start, year_end),
        total=_revenue(db, None, None),
    )


def _revenue_by_student(
    db: Session, payment_status: PaymentStatus, settled: bool
) -> list[schemas.StudentRevenueItem]:
    """依學生彙總教練費 + 差額；payment_status/settled 決定要算已收款還是未收款。"""
    totals: dict[int, float] = {}

    lesson_rows = (
        db.query(models.Lesson.student_id, func.sum(models.Lesson.revenue_amount))
        .filter(
            models.Lesson.payment_status == payment_status,
            models.Lesson.status != LessonStatus.CANCELLED,
        )
        .group_by(models.Lesson.student_id)
        .all()
    )
    for student_id, amount in lesson_rows:
        totals[student_id] = totals.get(student_id, 0) + (amount or 0)

    adj_rows = (
        db.query(models.Lesson.student_id, func.sum(models.Adjustment.amount))
        .join(models.Adjustment, models.Adjustment.lesson_id == models.Lesson.id)
        .filter(models.Adjustment.settled.is_(settled))
        .group_by(models.Lesson.student_id)
        .all()
    )
    for student_id, amount in adj_rows:
        totals[student_id] = totals.get(student_id, 0) + (amount or 0)

    totals = {sid: amount for sid, amount in totals.items() if amount}
    if not totals:
        return []
    students = db.query(models.Student).filter(models.Student.id.in_(totals.keys())).all()
    name_map = {s.id: s.name for s in students}
    result = [
        schemas.StudentRevenueItem(
            student_id=sid, student_name=name_map.get(sid, "?"), total_revenue=round(amount, 2)
        )
        for sid, amount in totals.items()
    ]
    result.sort(key=lambda r: -r.total_revenue)
    return result


@router.get("/by_student", response_model=list[schemas.StudentRevenueItem])
def revenue_by_student(db: Session = Depends(get_db)):
    """依學生彙總已收款教練費 + 已結清差額，供視覺化每位學生的總學費使用。"""
    return _revenue_by_student(db, PaymentStatus.PAID, settled=True)


@router.get("/unpaid_by_student", response_model=list[schemas.StudentRevenueItem])
def unpaid_by_student(db: Session = Depends(get_db)):
    """依學生彙總未收款教練費 + 未結清差額，供視覺化每位學生的應收未收金額使用。"""
    return _revenue_by_student(db, PaymentStatus.UNPAID, settled=False)


@router.get("/by_month", response_model=list[schemas.MonthRevenueItem])
def revenue_by_month(db: Session = Depends(get_db)):
    """依月份彙總已收款教練費 + 已結清差額，供視覺化每月學費使用。"""
    totals: dict[str, float] = {}

    lesson_rows = (
        db.query(func.strftime("%Y-%m", models.Lesson.date), func.sum(models.Lesson.revenue_amount))
        .filter(
            models.Lesson.payment_status == PaymentStatus.PAID,
            models.Lesson.status != LessonStatus.CANCELLED,
        )
        .group_by(func.strftime("%Y-%m", models.Lesson.date))
        .all()
    )
    for month, amount in lesson_rows:
        totals[month] = totals.get(month, 0) + (amount or 0)

    adj_rows = (
        db.query(
            func.strftime("%Y-%m", models.Adjustment.settled_at), func.sum(models.Adjustment.amount)
        )
        .filter(models.Adjustment.settled.is_(True))
        .group_by(func.strftime("%Y-%m", models.Adjustment.settled_at))
        .all()
    )
    for month, amount in adj_rows:
        if month is None:
            continue
        totals[month] = totals.get(month, 0) + (amount or 0)

    return [
        schemas.MonthRevenueItem(month=month, total_revenue=round(amount, 2))
        for month, amount in sorted(totals.items())
    ]


@router.get("/unpaid", response_model=schemas.UnpaidSummary)
def unpaid_summary(db: Session = Depends(get_db)):
    from app.routers.lessons import _to_out as lesson_to_out
    from app.routers.packages import _to_out as package_to_out

    unpaid_lessons = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.package_id.is_(None),
            models.Lesson.payment_status == PaymentStatus.UNPAID,
            models.Lesson.status != LessonStatus.CANCELLED,
        )
        .order_by(models.Lesson.date)
        .all()
    )
    unpaid_packages = (
        db.query(models.Package)
        .filter(models.Package.payment_status == PaymentStatus.UNPAID)
        .order_by(models.Package.id)
        .all()
    )
    unsettled_adjustments = (
        db.query(models.Adjustment)
        .filter(models.Adjustment.settled.is_(False))
        .order_by(models.Adjustment.id)
        .all()
    )
    return schemas.UnpaidSummary(
        unpaid_lessons=[lesson_to_out(lesson) for lesson in unpaid_lessons],
        unpaid_packages=[package_to_out(p) for p in unpaid_packages],
        unsettled_adjustments=[
            schemas.AdjustmentOut.model_validate(a) for a in unsettled_adjustments
        ],
    )
