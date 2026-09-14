"""Pydantic schemas：API 輸入輸出格式。"""
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict

from app.models import BookingStatus, LessonStatus, PaymentStatus, Tier


class VenueBase(BaseModel):
    name: str
    address: str | None = None
    booking_open_days_before: int = 0
    booking_open_time: time = time(0, 0)
    cancellation_policy: str | None = None
    note: str | None = None


class VenueCreate(VenueBase):
    pass


class VenueUpdate(VenueBase):
    pass


class VenueOut(VenueBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class PriceRuleBase(BaseModel):
    headcount_min: int
    headcount_max: int
    tier: Tier
    price: float


class PriceRuleCreate(PriceRuleBase):
    pass


class PriceRuleUpdate(PriceRuleBase):
    pass


class PriceRuleOut(PriceRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class StudentBase(BaseModel):
    name: str
    contact: str | None = None
    note: str | None = None
    tier: Tier = Tier.NEW


class StudentCreate(StudentBase):
    pass


class StudentUpdate(StudentBase):
    pass


class StudentOut(StudentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class LessonBase(BaseModel):
    student_id: int
    venue_id: int
    date: date
    start_time: time
    duration: int
    headcount: int = 1
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    revenue_amount: float | None = None


class LessonCreate(LessonBase):
    pass


class LessonUpdate(LessonBase):
    status: LessonStatus = LessonStatus.SCHEDULED
    revenue_amount: float


class LessonPaymentUpdate(BaseModel):
    payment_status: PaymentStatus


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    student_name: str
    venue_id: int
    venue_name: str
    package_id: int | None
    date: date
    start_time: time
    duration: int
    headcount: int
    sequence_no: int | None
    status: LessonStatus
    deduct_session: bool
    makeup_for_lesson_id: int | None
    booking_status: BookingStatus
    booked_at: datetime | None
    payment_status: PaymentStatus
    payment_date: date | None
    revenue_amount: float
