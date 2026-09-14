"""價目表 CRUD API。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/api/price_rules", tags=["price_rules"])


@router.get("", response_model=list[schemas.PriceRuleOut])
def list_price_rules(db: Session = Depends(get_db)):
    return db.query(models.PriceRule).order_by(models.PriceRule.headcount_min).all()


@router.post("", response_model=schemas.PriceRuleOut, status_code=201)
def create_price_rule(rule: schemas.PriceRuleCreate, db: Session = Depends(get_db)):
    db_rule = models.PriceRule(**rule.model_dump())
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule


@router.get("/{rule_id}", response_model=schemas.PriceRuleOut)
def get_price_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(models.PriceRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="價目規則不存在")
    return rule


@router.put("/{rule_id}", response_model=schemas.PriceRuleOut)
def update_price_rule(rule_id: int, rule: schemas.PriceRuleUpdate, db: Session = Depends(get_db)):
    db_rule = db.get(models.PriceRule, rule_id)
    if db_rule is None:
        raise HTTPException(status_code=404, detail="價目規則不存在")
    for key, value in rule.model_dump().items():
        setattr(db_rule, key, value)
    db.commit()
    db.refresh(db_rule)
    return db_rule


@router.delete("/{rule_id}", status_code=204)
def delete_price_rule(rule_id: int, db: Session = Depends(get_db)):
    db_rule = db.get(models.PriceRule, rule_id)
    if db_rule is None:
        raise HTTPException(status_code=404, detail="價目規則不存在")
    db.delete(db_rule)
    db.commit()
