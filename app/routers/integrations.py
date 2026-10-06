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
from app.package_logic import describe_lesson_time, find_overlapping_lesson
from app.booking_parser.slot_finder import TimeWindow, find_bookable_slots
from app.booking_parser.slot_search import _load_busy, _load_travel
from app.models import LessonStatus, PaymentStatus, Tier
from app.pricing import VenueFeeNotSet, compute_venue_fee, resolve_price
from app.routers.slot_search import get_now

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

    # 時段重疊就擋，不分場地（教練同一時間只能上一堂），見 find_overlapping_lesson
    conflict = find_overlapping_lesson(db, payload.date, payload.start_time, payload.duration)
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail=f"這個時段教練已經有其他課程了（{describe_lesson_time(conflict)}）",
        )

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

    # 預約網站已經跟學生報過價時直接用它的金額，學生看到的、付的、教練記帳的
    # 才會是同一個數字；沒給才照舊依價目表推算
    if payload.coach_fee is not None:
        revenue_amount = payload.coach_fee
    else:
        revenue_amount = resolve_price(db, student.tier, headcount=1, duration_minutes=payload.duration)
    venue_fee_amount = payload.venue_fee if payload.venue_fee is not None else 0

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
        venue_fee_amount=venue_fee_amount,
        source_booking_id=payload.source_booking_id,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)

    return schemas.PublicBookingLessonOut(
        lesson_id=lesson.id,
        student_id=student.id,
        student_created=student_created,
        revenue_amount=revenue_amount,
        venue_fee_amount=venue_fee_amount,
    )


# ---------- 公開預約網站：場館、可約時段、場地費、課程後續處理 ----------
# 以下都用 public_booking_api_token，回應只含必要資訊，不帶任何學生資料。


def _venues_by_name(db: Session, names: list[str]) -> dict[str, models.Venue]:
    rows = {v.name: v for v in db.query(models.Venue).filter(models.Venue.name.in_(names))}
    missing = [n for n in names if n not in rows]
    if missing:
        raise HTTPException(status_code=400, detail=f"找不到場館「{'、'.join(missing)}」")
    return rows


@router.get(
    "/public/venues",
    response_model=list[schemas.PublicVenueOut],
    dependencies=[Depends(verify_public_booking_token)],
)
def public_venues(db: Session = Depends(get_db)):
    """場館名稱與所屬地區，給預約網站後台設定「每週可教時間」時選場館用，
    名稱直接從這裡來，建立課程時才不會因為差一個空格對不上。"""
    areas: dict[int, list[str]] = {}
    for row in db.query(models.VenueArea).order_by(models.VenueArea.area):
        areas.setdefault(row.venue_id, []).append(row.area)
    return [
        schemas.PublicVenueOut(name=v.name, areas=areas.get(v.id, []))
        for v in db.query(models.Venue).order_by(models.Venue.id)
    ]


@router.post(
    "/availability",
    response_model=schemas.AvailabilityOut,
    dependencies=[Depends(verify_public_booking_token)],
)
def availability(
    payload: schemas.AvailabilityRequest,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
):
    """預約網站把「每週可教時間」換算成的每天時段送過來，這裡用找空檔同一套
    判斷（不撞課、算車程、工作時段內、晚於現在）回傳每個場館可以開始上課的
    時間；只回時間跟場館，不透露既有課程是誰的。"""
    names = sorted({n for d in payload.days for n in d.venue_names})
    venues = _venues_by_name(db, names)
    busy = _load_busy(db, sorted({d.date for d in payload.days}))
    travel = _load_travel(db)
    id_to_name = {v.id: v.name for v in venues.values()}

    found: dict[tuple, schemas.AvailabilitySlotOut] = {}
    for day in payload.days:
        window = TimeWindow(
            start=datetime.combine(day.date, day.time_from), end=datetime.combine(day.date, day.time_to)
        )
        for slot in find_bookable_slots(
            busy=busy,
            window=window,
            venue_ids=[venues[n].id for n in day.venue_names],
            duration_minutes=payload.duration_minutes,
            travel=travel,
            now=now,
        ):
            key = (slot.start, slot.venue_id)
            found.setdefault(
                key,
                schemas.AvailabilitySlotOut(
                    date=slot.start.date(),
                    start_time=slot.start.time(),
                    end_time=slot.end.time(),
                    venue_name=id_to_name[slot.venue_id],
                    adjacent=slot.adjacent,
                ),
            )
    return schemas.AvailabilityOut(slots=[found[k] for k in sorted(found)])


@router.post(
    "/venue-fee-quote",
    response_model=schemas.VenueFeeQuoteOut,
    dependencies=[Depends(verify_public_booking_token)],
)
def venue_fee_quote(payload: schemas.VenueFeeQuoteRequest, db: Session = Depends(get_db)):
    """依場地管理裡的「場館 × 時段價目表」試算場地費。價目表沒涵蓋到這個時段
    時回 400（不猜預設值），預約網站應該請學生改時段或聯絡教練。"""
    venue = _venues_by_name(db, [payload.venue_name])[payload.venue_name]
    try:
        fee = compute_venue_fee(db, venue.id, payload.date, payload.start_time, payload.duration)
    except VenueFeeNotSet as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.VenueFeeQuoteOut(venue_fee=fee)


def _public_booking_lesson(db: Session, lesson_id: int) -> models.Lesson:
    lesson = db.get(models.Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="課程不存在")
    if lesson.source_booking_id is None:
        raise HTTPException(status_code=403, detail="這堂課不是由預約網站建立的，不能從預約網站修改")
    return lesson


def _status_out(lesson: models.Lesson) -> schemas.PublicLessonStatusOut:
    return schemas.PublicLessonStatusOut(
        lesson_id=lesson.id,
        status=lesson.status,
        payment_status=lesson.payment_status,
        payment_date=lesson.payment_date,
    )


@router.post(
    "/lessons/{lesson_id}/cancel",
    response_model=schemas.PublicLessonStatusOut,
    dependencies=[Depends(verify_public_booking_token)],
)
def cancel_public_lesson(lesson_id: int, db: Session = Depends(get_db)):
    """預約網站那邊逾期未付款、未收到款項、學生取消時呼叫，把課改成「已取消」
    （找空檔與衝突檢查都把已取消視為時段釋放）。重複呼叫不會出錯。"""
    lesson = _public_booking_lesson(db, lesson_id)
    if lesson.status == LessonStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="這堂課已經上完，不能取消")
    lesson.status = LessonStatus.CANCELLED
    db.commit()
    db.refresh(lesson)
    return _status_out(lesson)


@router.post(
    "/lessons/{lesson_id}/mark-paid",
    response_model=schemas.PublicLessonStatusOut,
    dependencies=[Depends(verify_public_booking_token)],
)
def mark_public_lesson_paid(
    lesson_id: int, payload: schemas.PublicLessonMarkPaid, db: Session = Depends(get_db)
):
    """教練在預約網站「確認收款」時呼叫，教練不用再到這裡標一次已付款。"""
    lesson = _public_booking_lesson(db, lesson_id)
    lesson.payment_status = PaymentStatus.PAID
    lesson.payment_date = payload.payment_date
    db.commit()
    db.refresh(lesson)
    return _status_out(lesson)
