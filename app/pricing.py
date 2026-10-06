"""價目表查詢邏輯（見 SPEC.md 價目表章節）。"""
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.models import Tier


def resolve_price(db: Session, tier: Tier, headcount: int, duration_minutes: int = 60) -> float:
    """依人數與 tier 查價目表（價目表金額為 1 小時價），乘以時長比例得出總金額；
    3 人以上查無朋友價時退回熟客價。"""
    rule = (
        db.query(models.PriceRule)
        .filter(
            models.PriceRule.headcount_min <= headcount,
            models.PriceRule.headcount_max >= headcount,
            models.PriceRule.tier == tier,
        )
        .first()
    )
    if rule is None and tier == Tier.FRIEND:
        rule = (
            db.query(models.PriceRule)
            .filter(
                models.PriceRule.headcount_min <= headcount,
                models.PriceRule.headcount_max >= headcount,
                models.PriceRule.tier == Tier.REGULAR,
            )
            .first()
        )
    if rule is None:
        raise HTTPException(status_code=400, detail="找不到對應的價目規則")
    return round(rule.price * (duration_minutes / 60), 2)


class VenueFeeNotSet(ValueError):
    """場地價目表沒有涵蓋整堂課的時段：不猜預設值，交給呼叫端回報錯誤。"""


def compute_venue_fee(
    db: Session, venue_id: int, lesson_date: date, start_time: time, duration_minutes: int
) -> float:
    """依場館 × 時段價目表（每小時價）計算一堂課的場地費。跨兩個價格時段時
    按分鐘比例分別計算（例如 17:30-18:30、18:00 前後不同價，各算半小時）。
    價目表沒有涵蓋到的分鐘一律視為未設定，拋 VenueFeeNotSet。"""
    start = datetime.combine(lesson_date, start_time)
    end = start + timedelta(minutes=duration_minutes)
    weekday = lesson_date.weekday()

    total = 0.0
    covered_minutes = 0
    rates = db.query(models.VenueFeeRate).filter(models.VenueFeeRate.venue_id == venue_id)
    for rate in rates:
        if weekday not in rate.weekday_list:
            continue
        overlap_start = max(start, datetime.combine(lesson_date, rate.start_time))
        overlap_end = min(end, datetime.combine(lesson_date, rate.end_time))
        minutes = int((overlap_end - overlap_start).total_seconds() // 60)
        if minutes > 0:
            covered_minutes += minutes
            total += rate.fee_per_hour * minutes / 60

    if covered_minutes < duration_minutes:
        venue = db.get(models.Venue, venue_id)
        name = venue.name if venue else f"#{venue_id}"
        raise VenueFeeNotSet(
            f"「{name}」{lesson_date.isoformat()} {start_time.strftime('%H:%M')} 起 "
            f"{duration_minutes} 分鐘的場地費沒有設定，請到場地管理補上價目表"
        )
    return round(total, 2)
