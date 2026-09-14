"""初始資料建立：價目表預設值（見 SPEC.md 價目表）。"""
from sqlalchemy.orm import Session

from app import models
from app.models import Tier

DEFAULT_PRICE_RULES = [
    # (headcount_min, headcount_max, tier, price)
    (1, 1, Tier.NEW, 1600),
    (1, 1, Tier.FRIEND, 1400),
    (1, 1, Tier.REGULAR, 1200),
    (2, 2, Tier.NEW, 1800),
    (2, 2, Tier.FRIEND, 1600),
    (2, 2, Tier.REGULAR, 1400),
    (3, 999, Tier.NEW, 1800),
    # 3 人以上朋友價刻意不建立，查無資料時由業務邏輯退回熟客價
    (3, 999, Tier.REGULAR, 1500),
]


def seed_price_rules(db: Session) -> None:
    """僅在 price_rules 表為空時寫入預設價目，避免覆蓋使用者後續調整。"""
    if db.query(models.PriceRule).first() is not None:
        return
    for headcount_min, headcount_max, tier, price in DEFAULT_PRICE_RULES:
        db.add(
            models.PriceRule(
                headcount_min=headcount_min,
                headcount_max=headcount_max,
                tier=tier,
                price=price,
            )
        )
    db.commit()
