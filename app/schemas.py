"""Pydantic schemas：API 輸入輸出格式。"""
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict

from app.models import AdjustmentType, BookingStatus, LessonStatus, PackageStatus, PaymentStatus, Tier


class VenueBase(BaseModel):
    name: str
    address: str | None = None
    # 兩者皆為 None 代表「隨時可訂」，不受開放時間限制
    booking_open_days_before: int | None = 0
    booking_open_time: time | None = time(0, 0)
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
    venue_fee_amount: float = 0


class LessonCreate(LessonBase):
    package_id: int | None = None
    """掛在某個「臨時約時間」套組上；此時金額／收款狀態改由套組控管，並會佔用一堂套組額度。"""


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
    package_total_sessions: int | None
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
    venue_fee_amount: float


class LessonLeaveRequest(BaseModel):
    makeup_date: date | None = None
    makeup_start_time: time | None = None


class LessonLeaveResult(BaseModel):
    leave_lesson: LessonOut
    makeup_lesson: LessonOut


class PackageBase(BaseModel):
    student_id: int
    name: str
    session_duration: int
    coach_fee_per_hour: float
    venue_fee_per_hour: float = 0
    purchased_date: date
    recur_start_time: time
    default_venue_id: int
    payment_status: PaymentStatus = PaymentStatus.UNPAID


class PackageCreate(PackageBase):
    session_dates: list[date] = []
    """使用者手動選定的上課日期清單（不假設每週固定間隔，方便跳過連假）；堂數＝清單長度。
    留空表示「臨時約時間」：先收款、之後在行事曆逐堂新增再掛回這個套組，此時改用 total_sessions 欄位。"""
    total_sessions: int | None = None
    """僅在 session_dates 留空時需要：臨時約時間模式下的預購堂數。"""


class PackageUpdate(BaseModel):
    """套組設定完後可編輯的欄位；不含 student_id/payment_status（付款狀態走專屬端點）。"""

    name: str
    session_duration: int
    total_sessions: int
    coach_fee_per_hour: float
    venue_fee_per_hour: float = 0
    purchased_date: date
    start_date: date
    recur_weekday: int
    recur_start_time: time
    default_venue_id: int


class PackagePaymentUpdate(BaseModel):
    payment_status: PaymentStatus


class PackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    student_name: str
    name: str
    session_duration: int
    total_sessions: int
    remaining_sessions: int
    available_sessions: int
    coach_fee_per_hour: float
    venue_fee_per_hour: float
    total_price: float
    price_per_session: float
    purchased_date: date
    start_date: date
    recur_weekday: int
    recur_start_time: time
    default_venue_id: int
    venue_name: str
    status: PackageStatus
    payment_status: PaymentStatus
    payment_date: date | None


class RevenueStats(BaseModel):
    week: float
    month: float
    year: float
    total: float


class AdjustmentBase(BaseModel):
    lesson_id: int
    package_id: int | None = None
    type: AdjustmentType
    amount: float
    note: str | None = None


class AdjustmentCreate(AdjustmentBase):
    pass


class AdjustmentOut(AdjustmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    settled: bool
    settled_at: datetime | None
    student_name: str
    lesson_date: date


class UnpaidSummary(BaseModel):
    unpaid_lessons: list[LessonOut]
    unpaid_packages: list[PackageOut]
    unsettled_adjustments: list[AdjustmentOut]


class BookingStatusUpdate(BaseModel):
    booking_status: BookingStatus


class BookingCheckItem(BaseModel):
    lesson: LessonOut
    booking_open_at: datetime | None  # None = 該場地隨時可訂，無開放時間限制


class BookingCheckSummary(BaseModel):
    need_booking: list[BookingCheckItem]
    not_yet_open: list[BookingCheckItem]
    booked: list[BookingCheckItem]


class PackageSettlement(BaseModel):
    adjustments: list[AdjustmentOut]
    total: float


class StudentRevenueItem(BaseModel):
    student_id: int
    student_name: str
    total_revenue: float


class MonthRevenueItem(BaseModel):
    month: str  # "YYYY-MM"
    total_revenue: float
