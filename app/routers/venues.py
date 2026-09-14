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
    db.delete(db_venue)
    db.commit()
