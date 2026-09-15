"""差額與額外費用 API（見 SPEC.md 額外費用與期末結算）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/api/adjustments", tags=["adjustments"])


@router.get("", response_model=list[schemas.AdjustmentOut])
def list_adjustments(
    lesson_id: int | None = Query(None),
    package_id: int | None = Query(None),
    settled: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(models.Adjustment)
    if lesson_id is not None:
        query = query.filter(models.Adjustment.lesson_id == lesson_id)
    if package_id is not None:
        query = query.filter(models.Adjustment.package_id == package_id)
    if settled is not None:
        query = query.filter(models.Adjustment.settled == settled)
    return query.order_by(models.Adjustment.id.desc()).all()


@router.post("", response_model=schemas.AdjustmentOut, status_code=201)
def create_adjustment(payload: schemas.AdjustmentCreate, db: Session = Depends(get_db)):
    lesson = db.get(models.Lesson, payload.lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="課程不存在")
    # package_id 一律由該堂課實際所屬的套組決定，不採用前端傳入值，避免資料不一致
    db_adjustment = models.Adjustment(
        lesson_id=payload.lesson_id,
        package_id=lesson.package_id,
        type=payload.type,
        amount=payload.amount,
        note=payload.note,
        settled=False,
    )
    db.add(db_adjustment)
    db.commit()
    db.refresh(db_adjustment)
    return db_adjustment


@router.put("/{adjustment_id}", response_model=schemas.AdjustmentOut)
def update_adjustment(
    adjustment_id: int, payload: schemas.AdjustmentUpdate, db: Session = Depends(get_db)
):
    """編輯差額的類型／金額／備註，不用回到原本那堂課才能改。"""
    adjustment = db.get(models.Adjustment, adjustment_id)
    if adjustment is None:
        raise HTTPException(status_code=404, detail="差額紀錄不存在")
    adjustment.type = payload.type
    adjustment.amount = payload.amount
    adjustment.note = payload.note
    db.commit()
    db.refresh(adjustment)
    return adjustment


@router.patch("/{adjustment_id}/settle", response_model=schemas.AdjustmentOut)
def settle_adjustment(adjustment_id: int, db: Session = Depends(get_db)):
    adjustment = db.get(models.Adjustment, adjustment_id)
    if adjustment is None:
        raise HTTPException(status_code=404, detail="差額紀錄不存在")
    adjustment.settled = True
    adjustment.settled_at = datetime.now()
    db.commit()
    db.refresh(adjustment)
    return adjustment


@router.delete("/{adjustment_id}", status_code=204)
def delete_adjustment(adjustment_id: int, db: Session = Depends(get_db)):
    adjustment = db.get(models.Adjustment, adjustment_id)
    if adjustment is None:
        raise HTTPException(status_code=404, detail="差額紀錄不存在")
    db.delete(adjustment)
    db.commit()
