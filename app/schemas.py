"""Pydantic schemas：API 輸入輸出格式。"""
from datetime import time

from pydantic import BaseModel, ConfigDict

from app.models import Tier


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
