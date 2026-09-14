"""價目表查詢邏輯（見 SPEC.md 價目表章節）。"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.models import Tier


def resolve_price(db: Session, tier: Tier, headcount: int) -> float:
    """依人數與 tier 查價目表；3 人以上查無朋友價時退回熟客價。"""
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
    return rule.price
