"""給外部自動化系統用的資料介接端點（見動智館自動訂場系統的介接需求文件）。

這裡的端點都需要帶 `Authorization: Bearer <token>`（見 app/auth.py），
跟網站本身給瀏覽器用的其他 API 是分開的兩件事：這裡是特地開給「無人
值守、排程觸發」的外部系統呼叫用的資料介面。
"""
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import verify_booking_token
from app.database import get_db

router = APIRouter(
    prefix="/api/integrations",
    tags=["integrations"],
    dependencies=[Depends(verify_booking_token)],
)

TAIWAN_TZ = timezone(timedelta(hours=8))


@router.get("/venue-schedule", response_model=schemas.VenueScheduleOut)
def venue_schedule(
    venue: str = Query(..., description="場館名稱，需完全符合場地管理裡的名稱"),
    from_: date_type = Query(..., alias="from", description="起始日期（含）"),
    to: date_type = Query(..., description="結束日期（含）"),
    db: Session = Depends(get_db),
):
    """回傳指定場館、指定日期區間內的所有課程（不論狀態／訂場狀態都列出，
    由呼叫端自己判斷哪些該訂、哪些是孤兒訂單）。日期/時間一律為台灣當地
    時間，沒有時區轉換。"""
    if from_ > to:
        raise HTTPException(status_code=400, detail="from 不能晚於 to")

    venue_row = db.query(models.Venue).filter(models.Venue.name == venue).first()
    if venue_row is None:
        raise HTTPException(status_code=400, detail=f"找不到場館「{venue}」")

    lessons = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.venue_id == venue_row.id,
            models.Lesson.date >= from_,
            models.Lesson.date <= to,
        )
        .order_by(models.Lesson.date, models.Lesson.start_time)
        .all()
    )

    def _end_time(lesson: models.Lesson):
        start_dt = datetime.combine(lesson.date, lesson.start_time)
        return (start_dt + timedelta(minutes=lesson.duration)).time()

    items = [
        schemas.VenueScheduleLesson(
            lesson_id=lesson.id,
            date=lesson.date,
            start_time=lesson.start_time,
            end_time=_end_time(lesson),
            student_name=lesson.student.name,
            status=lesson.status,
            booking_status=lesson.booking_status,
            booked_at=lesson.booked_at,
        )
        for lesson in lessons
    ]

    return schemas.VenueScheduleOut(
        venue=venue_row.name,
        venue_id=venue_row.id,
        from_=from_,
        to=to,
        generated_at=datetime.now(TAIWAN_TZ),
        lessons=items,
    )
