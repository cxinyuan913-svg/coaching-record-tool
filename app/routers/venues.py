"""場地 CRUD API。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/api/venues", tags=["venues"])


@router.get("", response_model=list[schemas.VenueOut])
def list_venues(db: Session = Depends(get_db)):
    return db.query(models.Venue).order_by(models.Venue.id).all()


@router.post("", response_model=schemas.VenueOut, status_code=201)
def create_venue(venue: schemas.VenueCreate, db: Session = Depends(get_db)):
    db_venue = models.Venue(**venue.model_dump())
    db.add(db_venue)
    db.commit()
    db.refresh(db_venue)
    return db_venue


@router.get("/{venue_id}", response_model=schemas.VenueOut)
def get_venue(venue_id: int, db: Session = Depends(get_db)):
    venue = db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="場地不存在")
    return venue


@router.put("/{venue_id}", response_model=schemas.VenueOut)
def update_venue(venue_id: int, venue: schemas.VenueUpdate, db: Session = Depends(get_db)):
    db_venue = db.get(models.Venue, venue_id)
    if db_venue is None:
        raise HTTPException(status_code=404, detail="場地不存在")
    for key, value in venue.model_dump().items():
        setattr(db_venue, key, value)
    db.commit()
    db.refresh(db_venue)
    return db_venue


@router.delete("/{venue_id}", status_code=204)
def delete_venue(venue_id: int, db: Session = Depends(get_db)):
    db_venue = db.get(models.Venue, venue_id)
    if db_venue is None:
        raise HTTPException(status_code=404, detail="場地不存在")
    # 車程表、場地費價目表是場地的附屬資料，場地刪掉就一起清掉，不留孤兒資料
    db.query(models.VenueFeeRate).filter(models.VenueFeeRate.venue_id == venue_id).delete(
        synchronize_session=False
    )
    db.query(models.VenueTravelTime).filter(
        (models.VenueTravelTime.venue_a_id == venue_id) | (models.VenueTravelTime.venue_b_id == venue_id)
    ).delete(synchronize_session=False)
    db.delete(db_venue)
    db.commit()


# ---------- 場地費價目表（見 models.VenueFeeRate） ----------


def _fee_rates_out(db: Session, venue_id: int) -> list[schemas.VenueFeeRateOut]:
    rows = (
        db.query(models.VenueFeeRate)
        .filter(models.VenueFeeRate.venue_id == venue_id)
        .order_by(models.VenueFeeRate.weekdays, models.VenueFeeRate.start_time)
    )
    return [
        schemas.VenueFeeRateOut(
            id=r.id,
            weekdays=r.weekday_list,
            start_time=r.start_time,
            end_time=r.end_time,
            fee_per_hour=r.fee_per_hour,
        )
        for r in rows
    ]


@router.get("/{venue_id}/fee-rates", response_model=list[schemas.VenueFeeRateOut])
def list_fee_rates(venue_id: int, db: Session = Depends(get_db)):
    if db.get(models.Venue, venue_id) is None:
        raise HTTPException(status_code=404, detail="場地不存在")
    return _fee_rates_out(db, venue_id)


@router.put("/{venue_id}/fee-rates", response_model=list[schemas.VenueFeeRateOut])
def replace_fee_rates(venue_id: int, items: list[schemas.VenueFeeRateItem], db: Session = Depends(get_db)):
    """整批取代這個場館的價目表（頁面上一次編輯整張表、一次存檔）。同一個星期
    的時段不能重疊，否則同一分鐘會有兩個價格；有問題就整批不動。"""
    if db.get(models.Venue, venue_id) is None:
        raise HTTPException(status_code=404, detail="場地不存在")

    weekday_names = "一二三四五六日"
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            shared = set(a.weekdays) & set(b.weekdays)
            if shared and a.start_time < b.end_time and b.start_time < a.end_time:
                day = weekday_names[min(shared)]
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"週{day} {a.start_time.strftime('%H:%M')}-{a.end_time.strftime('%H:%M')} 跟 "
                        f"{b.start_time.strftime('%H:%M')}-{b.end_time.strftime('%H:%M')} 時段重疊"
                    ),
                )

    db.query(models.VenueFeeRate).filter(models.VenueFeeRate.venue_id == venue_id).delete(
        synchronize_session=False
    )
    for item in items:
        db.add(
            models.VenueFeeRate(
                venue_id=venue_id,
                weekdays=",".join(str(d) for d in item.weekdays),
                start_time=item.start_time,
                end_time=item.end_time,
                fee_per_hour=item.fee_per_hour,
            )
        )
    db.commit()
    return _fee_rates_out(db, venue_id)
