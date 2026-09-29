"""給外部自動化系統用的資料介接端點（動智館自動訂場系統、公開預約網站）。

這裡的端點都需要帶 `Authorization: Bearer <token>`（見 app/auth.py；唯讀的
venue-schedule 另外接受網頁已登入的狀態，原因見 verify_booking_token_or_login），
跟網站本身給瀏覽器用的其他 API 是分開的兩件事：這裡是特地開給「無人
值守、排程觸發」或「另一個系統呼叫」用的資料介面。兩個外部系統各自
驗證各自的 token，不共用，所以這個 router 不能整個掛統一的
`dependencies=`，改成每個端點各自指定要用哪一個。
"""
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import verify_booking_token_or_login, verify_public_booking_token
from app.database import get_db
from app.models import LessonStatus, PaymentStatus, Tier
from app.pricing import resolve_price

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

TAIWAN_TZ = timezone(timedelta(hours=8))


@router.get(
    "/venue-schedule",
    response_model=schemas.VenueScheduleOut,
    dependencies=[Depends(verify_booking_token_or_login)],
)
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


@router.post(
    "/lessons",
    response_model=schemas.PublicBookingLessonOut,
    status_code=201,
    dependencies=[Depends(verify_public_booking_token)],
)
def create_lesson_from_public_booking(
    payload: schemas.PublicBookingLessonCreate, db: Session = Depends(get_db)
):
    """公開預約網站核准一筆申請後呼叫，自動建立一堂正式課程，教練不用手動
    謄一次（見兩個專案之間的介接約定）。"""
    venue = db.query(models.Venue).filter(models.Venue.name == payload.venue_name).first()
    if venue is None:
        raise HTTPException(status_code=400, detail=f"找不到場館「{payload.venue_name}」")

    # 衝突判斷比照 app/package_logic.py 的 mark_leave_and_reschedule：同一個
    # 時間點教練只能上一堂課，不分場地——這是教練自己的行事曆衝突，不是
    # 場地容量問題
    conflict = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.date == payload.date,
            models.Lesson.start_time == payload.start_time,
            models.Lesson.status != LessonStatus.CANCELLED,
        )
        .first()
    )
    if conflict is not None:
        raise HTTPException(status_code=409, detail="這個時間教練已經有其他課程了")

    # v1 刻意簡化：姓名＋聯絡方式完全相符才算同一人，找不到就新增一筆新學生，
    # 不做模糊比對／自動合併，重複學生由教練事後自己在教練工具裡手動處理
    student = (
        db.query(models.Student)
        .filter(
            models.Student.name == payload.student_name,
            models.Student.contact == payload.student_contact,
        )
        .first()
    )
    student_created = student is None
    if student is None:
        student = models.Student(
            name=payload.student_name, contact=payload.student_contact, tier=Tier.NEW
        )
        db.add(student)
        db.flush()  # 取得 student.id 供下面建立 Lesson 用

    revenue_amount = resolve_price(db, student.tier, headcount=1, duration_minutes=payload.duration)

    lesson = models.Lesson(
        student_id=student.id,
        venue_id=venue.id,
        date=payload.date,
        start_time=payload.start_time,
        duration=payload.duration,
        headcount=1,
        status=LessonStatus.SCHEDULED,
        payment_status=PaymentStatus.UNPAID,
        revenue_amount=revenue_amount,
        venue_fee_amount=0,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)

    return schemas.PublicBookingLessonOut(
        lesson_id=lesson.id,
        student_id=student.id,
        student_created=student_created,
        revenue_amount=revenue_amount,
    )
