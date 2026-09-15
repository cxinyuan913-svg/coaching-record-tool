"""套組課程 CRUD API：批次排課、剩餘堂數、付款狀態。"""
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.models import LessonStatus, PackageStatus, PaymentStatus
from app.package_logic import (
    available_sessions,
    generate_package_lessons,
    recompute_package_pricing,
    recompute_remaining_sessions,
)

router = APIRouter(prefix="/api/packages", tags=["packages"])


def _to_out(package: models.Package) -> schemas.PackageOut:
    return schemas.PackageOut(
        id=package.id,
        student_id=package.student_id,
        student_name=package.student.name,
        name=package.name,
        session_duration=package.session_duration,
        total_sessions=package.total_sessions,
        remaining_sessions=package.remaining_sessions,
        available_sessions=available_sessions(package),
        coach_fee_per_hour=package.coach_fee_per_hour,
        venue_fee_per_hour=package.venue_fee_per_hour,
        total_price=package.total_price,
        price_per_session=package.price_per_session,
        purchased_date=package.purchased_date,
        start_date=package.start_date,
        recur_weekday=package.recur_weekday,
        recur_start_time=package.recur_start_time,
        default_venue_id=package.default_venue_id,
        venue_name=package.default_venue.name,
        status=package.status,
        payment_status=package.payment_status,
        payment_date=package.payment_date,
    )


@router.get("", response_model=list[schemas.PackageOut])
def list_packages(
    student_id: int | None = Query(None),
    status: PackageStatus | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(models.Package)
    if student_id is not None:
        query = query.filter(models.Package.student_id == student_id)
    if status is not None:
        query = query.filter(models.Package.status == status)
    packages = query.order_by(models.Package.id.desc()).all()
    return [_to_out(p) for p in packages]


@router.post("", response_model=schemas.PackageOut, status_code=201)
def create_package(package: schemas.PackageCreate, db: Session = Depends(get_db)):
    student = db.get(models.Student, package.student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="學生不存在")
    venue = db.get(models.Venue, package.default_venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="場地不存在")
    dates = sorted(set(package.session_dates))
    if dates:
        total_sessions = len(dates)
        start_date = dates[0]
    else:
        # 臨時約時間：先收款開一張額度，之後在行事曆逐堂新增再掛回這個套組
        if not package.total_sessions or package.total_sessions < 1:
            raise HTTPException(status_code=400, detail="請選擇上課日期，或填寫預購堂數（臨時約時間）")
        total_sessions = package.total_sessions
        start_date = package.purchased_date
    recur_weekday = (start_date.weekday() + 1) % 7  # 對齊前端 JS Date.getDay()：0=週日

    db_package = models.Package(
        student_id=package.student_id,
        name=package.name,
        session_duration=package.session_duration,
        total_sessions=total_sessions,
        remaining_sessions=total_sessions,
        coach_fee_per_hour=package.coach_fee_per_hour,
        venue_fee_per_hour=package.venue_fee_per_hour,
        total_price=0,
        price_per_session=0,
        purchased_date=package.purchased_date,
        start_date=start_date,
        recur_weekday=recur_weekday,
        recur_start_time=package.recur_start_time,
        default_venue_id=package.default_venue_id,
        status=PackageStatus.ACTIVE,
        payment_status=package.payment_status,
        payment_date=date_type.today() if package.payment_status == PaymentStatus.PAID else None,
    )
    db.add(db_package)
    db.flush()  # 取得 db_package.id 供 lessons 使用
    if dates:
        generate_package_lessons(db, db_package, dates)
        db.flush()
    recompute_package_pricing(db, db_package)
    db.commit()
    db.refresh(db_package)
    return _to_out(db_package)


@router.get("/{package_id}", response_model=schemas.PackageOut)
def get_package(package_id: int, db: Session = Depends(get_db)):
    package = db.get(models.Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="套組不存在")
    return _to_out(package)


@router.put("/{package_id}", response_model=schemas.PackageOut)
def update_package(package_id: int, payload: schemas.PackageUpdate, db: Session = Depends(get_db)):
    """套組設定完後可編輯基本資料；金額調整會連動更新底下所有堂的攤提金額。"""
    package = db.get(models.Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="套組不存在")
    venue = db.get(models.Venue, payload.default_venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="場地不存在")
    if not 0 <= payload.recur_weekday <= 6:
        raise HTTPException(status_code=400, detail="recur_weekday 必須介於 0-6")

    if payload.total_sessions < 1:
        raise HTTPException(status_code=400, detail="total_sessions 必須至少為 1")

    duration_changed = payload.session_duration != package.session_duration

    package.name = payload.name
    package.session_duration = payload.session_duration
    package.total_sessions = payload.total_sessions
    package.coach_fee_per_hour = payload.coach_fee_per_hour
    package.venue_fee_per_hour = payload.venue_fee_per_hour
    package.purchased_date = payload.purchased_date
    package.start_date = payload.start_date
    package.recur_weekday = payload.recur_weekday
    package.recur_start_time = payload.recur_start_time
    package.default_venue_id = payload.default_venue_id

    if duration_changed:
        # 套組標準時長改變時，既有（非請假）堂的時長一併同步為新標準，金額才會照新時長算
        db.query(models.Lesson).filter(
            models.Lesson.package_id == package_id, models.Lesson.status != LessonStatus.LEAVE
        ).update({"duration": payload.session_duration})

    # 總堂數或金額變動都會影響剩餘堂數與每堂攤提金額，一併重算
    recompute_remaining_sessions(db, package)
    recompute_package_pricing(db, package)
    db.commit()
    db.refresh(package)
    return _to_out(package)


@router.get("/{package_id}/lessons", response_model=list[schemas.LessonOut])
def list_package_lessons(package_id: int, db: Session = Depends(get_db)):
    from app.routers.lessons import _to_out as lesson_to_out  # 避免循環 import

    package = db.get(models.Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="套組不存在")
    lessons = (
        db.query(models.Lesson)
        .filter(models.Lesson.package_id == package_id)
        .order_by(models.Lesson.date)
        .all()
    )
    return [lesson_to_out(lesson) for lesson in lessons]


@router.patch("/{package_id}/payment", response_model=schemas.PackageOut)
def update_package_payment(
    package_id: int, payload: schemas.PackagePaymentUpdate, db: Session = Depends(get_db)
):
    package = db.get(models.Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="套組不存在")
    package.payment_status = payload.payment_status
    package.payment_date = (
        date_type.today() if payload.payment_status == PaymentStatus.PAID else None
    )
    # 套組的付款狀態變更時，底下所有 lessons 的付款狀態跟著同步
    db.query(models.Lesson).filter(models.Lesson.package_id == package_id).update(
        {
            "payment_status": package.payment_status,
            "payment_date": package.payment_date,
        }
    )
    db.commit()
    db.refresh(package)
    return _to_out(package)


@router.get("/{package_id}/settlement", response_model=schemas.PackageSettlement)
def get_package_settlement(package_id: int, db: Session = Depends(get_db)):
    """彙整該套組目前未結清的差額（人數差額／場地費等），供期末結算參考。"""
    package = db.get(models.Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="套組不存在")
    adjustments = (
        db.query(models.Adjustment)
        .filter(models.Adjustment.package_id == package_id, models.Adjustment.settled.is_(False))
        .order_by(models.Adjustment.id)
        .all()
    )
    total = sum(a.amount for a in adjustments)
    return schemas.PackageSettlement(
        adjustments=[schemas.AdjustmentOut.model_validate(a) for a in adjustments], total=total
    )


@router.patch("/{package_id}/settlement/settle", response_model=schemas.PackageSettlement)
def settle_package(package_id: int, db: Session = Depends(get_db)):
    """將該套組所有未結清差額整批標記為已結清。"""
    from datetime import datetime

    package = db.get(models.Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="套組不存在")
    adjustments = (
        db.query(models.Adjustment)
        .filter(models.Adjustment.package_id == package_id, models.Adjustment.settled.is_(False))
        .all()
    )
    now = datetime.now()
    for a in adjustments:
        a.settled = True
        a.settled_at = now
    db.commit()
    return schemas.PackageSettlement(
        adjustments=[schemas.AdjustmentOut.model_validate(a) for a in adjustments],
        total=sum(a.amount for a in adjustments),
    )


@router.delete("/{package_id}", status_code=204)
def delete_package(package_id: int, db: Session = Depends(get_db)):
    package = db.get(models.Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="套組不存在")
    lesson_ids = [
        lid
        for (lid,) in db.query(models.Lesson.id).filter(models.Lesson.package_id == package_id)
    ]
    if lesson_ids:
        db.query(models.Adjustment).filter(models.Adjustment.lesson_id.in_(lesson_ids)).delete(
            synchronize_session=False
        )
        db.query(models.Lesson).filter(models.Lesson.package_id == package_id).delete(
            synchronize_session=False
        )
    db.delete(package)
    db.commit()
