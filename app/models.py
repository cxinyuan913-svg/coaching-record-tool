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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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
