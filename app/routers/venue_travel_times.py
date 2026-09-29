"""場館車程對照表 API（見 spec/scheduling-agent.md）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/api/venue-travel-times", tags=["venue-travel-times"])


def _list(db: Session) -> list[schemas.VenueTravelTimeItem]:
    rows = db.query(models.VenueTravelTime).order_by(
        models.VenueTravelTime.venue_a_id, models.VenueTravelTime.venue_b_id
    )
    return [
        schemas.VenueTravelTimeItem(
            venue_a_id=r.venue_a_id, venue_b_id=r.venue_b_id, travel_minutes=r.travel_minutes
        )
        for r in rows
    ]


@router.get("", response_model=list[schemas.VenueTravelTimeItem])
def list_travel_times(db: Session = Depends(get_db)):
    return _list(db)


@router.put("", response_model=list[schemas.VenueTravelTimeItem])
def upsert_travel_times(items: list[schemas.VenueTravelTimeItem], db: Session = Depends(get_db)):
    """整批設定：有給數字就新增或更新，給 None 就刪除；沒列到的組合維持原樣。
    全部檢查通過才寫入，任何一筆有問題就整批不動。"""
    venue_ids = {v.id for v in db.query(models.Venue.id)}
    for item in items:
        if item.venue_a_id == item.venue_b_id:
            raise HTTPException(status_code=422, detail="同場館車程固定為 0，不用設定")
        missing = {item.venue_a_id, item.venue_b_id} - venue_ids
        if missing:
            raise HTTPException(status_code=422, detail=f"場地不存在：{sorted(missing)}")

    for item in items:
        a, b = sorted((item.venue_a_id, item.venue_b_id))
        row = (
            db.query(models.VenueTravelTime)
            .filter_by(venue_a_id=a, venue_b_id=b)
            .one_or_none()
        )
        if item.travel_minutes is None:
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(models.VenueTravelTime(venue_a_id=a, venue_b_id=b, travel_minutes=item.travel_minutes))
        else:
            row.travel_minutes = item.travel_minutes
        # 同一批裡同一組出現兩次時，讓後面那筆查得到前面剛加的
        db.flush()
    db.commit()
    return _list(db)
