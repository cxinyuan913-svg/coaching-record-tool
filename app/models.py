"""SQLAlchemy ORM models：六張表一次建齊（見 SPEC.md 資料模型）。"""
import enum
from datetime import datetime, date, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.timeutil import now_taipei


class Tier(str, enum.Enum):
    """學生等級：新生／朋友／熟客。"""

    NEW = "new"
    FRIEND = "friend"
    REGULAR = "regular"


class PackageStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


class PaymentStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PAID = "paid"


class LessonStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    LEAVE = "leave"


class BookingStatus(str, enum.Enum):
    NOT_BOOKED = "not_booked"
    BOOKED = "booked"
    FAILED = "failed"


class AdjustmentType(str, enum.Enum):
    HEADCOUNT_DIFF = "headcount_diff"
    VENUE_FEE = "venue_fee"
    VENUE_CHANGE = "venue_change"
    OTHER = "other"


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier: Mapped[Tier] = mapped_column(Enum(Tier), nullable=False, default=Tier.NEW)

    packages: Mapped[list["Package"]] = relationship(back_populates="student")
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="student")


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 兩者皆為 NULL 代表「隨時可訂」，訂場檢查時永遠視為已開放
    booking_open_days_before: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    booking_open_time: Mapped[time | None] = mapped_column(Time, nullable=True, default=time(0, 0))
    cancellation_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    lessons: Mapped[list["Lesson"]] = relationship(back_populates="venue")
    packages: Mapped[list["Package"]] = relationship(back_populates="default_venue")


class PriceRule(Base):
    __tablename__ = "price_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    headcount_min: Mapped[int] = mapped_column(Integer, nullable=False)
    headcount_max: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[Tier] = mapped_column(Enum(Tier), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)


class Package(Base):
    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    session_duration: Mapped[int] = mapped_column(Integer, nullable=False)
    total_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    remaining_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    # 堂課費／場地費皆為「每小時」費率；total_price、price_per_session 為依費率與時長算出的結果，非使用者直接輸入
    coach_fee_per_hour: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    venue_fee_per_hour: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    price_per_session: Mapped[float] = mapped_column(Float, nullable=False)
    purchased_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    recur_weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    recur_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    default_venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    status: Mapped[PackageStatus] = mapped_column(
        Enum(PackageStatus), nullable=False, default=PackageStatus.ACTIVE
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), nullable=False, default=PaymentStatus.UNPAID
    )
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 「最後一堂課剩7天」提醒是否已發送過，避免每次排程檢查都重複通知
    ending_reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    student: Mapped["Student"] = relationship(back_populates="packages")
    default_venue: Mapped["Venue"] = relationship(back_populates="packages")
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="package")


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("packages.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    headcount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sequence_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[LessonStatus] = mapped_column(
        Enum(LessonStatus), nullable=False, default=LessonStatus.SCHEDULED
    )
    deduct_session: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    makeup_for_lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("lessons.id"), nullable=True
    )
    booking_status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus), nullable=False, default=BookingStatus.NOT_BOOKED
    )
    booked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), nullable=False, default=PaymentStatus.UNPAID
    )
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revenue_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    # 場地費：代收代付給場館的費用，不算教練收入，不計入收入統計
    venue_fee_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    # 「上課前一小時」提醒是否已發送過，避免每次排程檢查都重複通知
    hour_reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    student: Mapped["Student"] = relationship(back_populates="lessons")
    venue: Mapped["Venue"] = relationship(back_populates="lessons")
    package: Mapped["Package | None"] = relationship(back_populates="lessons")
    adjustments: Mapped[list["Adjustment"]] = relationship(back_populates="lesson")


class Adjustment(Base):
    __tablename__ = "adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), nullable=False)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("packages.id"), nullable=True)
    type: Mapped[AdjustmentType] = mapped_column(Enum(AdjustmentType), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    settled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    lesson: Mapped["Lesson"] = relationship(back_populates="adjustments")

    @property
    def student_name(self) -> str:
        return self.lesson.student.name

    @property
    def lesson_date(self):
        return self.lesson.date


class VenueArea(Base):
    """場地↔地區對照（例如「竹北」對到某幾個場地），給約課訊息解析功能
    查詢地區時用。一個場地可以對應多個地區字串，教練直接改這張表即可，
    不用改程式碼。全新的表，不影響 Venue 既有欄位。"""

    __tablename__ = "venue_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    area: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    venue: Mapped["Venue"] = relationship()


class StudentAlias(Base):
    """學生別名（暱稱、不同稱呼方式），給約課訊息解析比對學生姓名用。
    全新的表，不影響 Student 既有欄位。"""

    __tablename__ = "student_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    student: Mapped["Student"] = relationship()


class BookingRequestStatus(str, enum.Enum):
    OK = "ok"
    NEEDS_REVIEW = "needs_review"
    NOT_BOOKING = "not_booking"


class BookingRequest(Base):
    """約課訊息解析紀錄：原始訊息、LLM 原始輸出、換算後結果、驗證狀態，
    每次呼叫都留一筆，供之後評測跟除錯用。"""

    __tablename__ = "booking_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    reference_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    parsed_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[BookingRequestStatus] = mapped_column(
        Enum(BookingRequestStatus), nullable=False, default=BookingRequestStatus.NEEDS_REVIEW
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_taipei)


class VenueTravelTime(Base):
    """場館兩兩之間的固定車程（分鐘），給找空檔排班用（見 spec/scheduling-agent.md）。
    雙向共用一筆，存的時候固定 venue_a_id < venue_b_id；同場館車程視為 0，
    不存在這張表裡。查不到的組合代表「不可銜接」，不要自己猜一個預設值。"""

    __tablename__ = "venue_travel_times"
    __table_args__ = (UniqueConstraint("venue_a_id", "venue_b_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_a_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    venue_b_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    travel_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
