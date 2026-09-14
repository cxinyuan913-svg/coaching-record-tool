"""包制課程 CRUD API：批次排課、剩餘堂數、付款狀態。"""
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.models import PackageStatus, PaymentStatus
from app.package_logic import generate_package_lessons

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
    if not 0 <= package.recur_weekday <= 6:
        raise HTTPException(status_code=400, detail="recur_weekday 必須介於 0-6")

    db_package = models.Package(
        student_id=package.student_id,
        name=package.name,
        session_duration=package.session_duration,
        total_sessions=package.total_sessions,
        remaining_sessions=package.total_sessions,
        total_price=package.total_price,
        price_per_session=round(package.total_price / package.total_sessions, 2),
        purchased_date=package.purchased_date,
        start_date=package.start_date,
        recur_weekday=package.recur_weekday,
        recur_start_time=package.recur_start_time,
        default_venue_id=package.default_venue_id,
        status=PackageStatus.ACTIVE,
        payment_status=package.payment_status,
        payment_date=date_type.today() if package.payment_status == PaymentStatus.PAID else None,
    )
    db.add(db_package)
    db.flush()  # 取得 db_package.id 供 lessons 使用
    generate_package_lessons(db, db_package)
    db.commit()
    db.refresh(db_package)
    return _to_out(db_package)


@router.get("/{package_id}", response_model=schemas.PackageOut)
def get_package(package_id: int, db: Session = Depends(get_db)):
    package = db.get(models.Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="包不存在")
    return _to_out(package)


@router.get("/{package_id}/lessons", response_model=list[schemas.LessonOut])
def list_package_lessons(package_id: int, db: Session = Depends(get_db)):
    from app.routers.lessons import _to_out as lesson_to_out  # 避免循環 import

    package = db.get(models.Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="包不存在")
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
        raise HTTPException(status_code=404, detail="包不存在")
    package.payment_status = payload.payment_status
    package.payment_date = (
        date_type.today() if payload.payment_status == PaymentStatus.PAID else None
    )
    # 包的付款狀態變更時，底下所有 lessons 的付款狀態跟著同步
    db.query(models.Lesson).filter(models.Lesson.package_id == package_id).update(
        {
            "payment_status": package.payment_status,
            "payment_date": package.payment_date,
        }
    )
    db.commit()
    db.refresh(package)
    return _to_out(package)


@router.delete("/{package_id}", status_code=204)
def delete_package(package_id: int, db: Session = Depends(get_db)):
    package = db.get(models.Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="包不存在")
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
