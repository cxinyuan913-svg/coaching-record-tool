"""FastAPI 進入點。"""
from fastapi import FastAPI

from app import models  # noqa: F401  匯入以註冊 ORM models 到 Base.metadata
from app.database import Base, SessionLocal, engine
from app.routers import price_rules, students, venues
from app.seed import seed_price_rules

# 六張表一次建齊
Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    seed_price_rules(db)

app = FastAPI(title="羽球教練紀錄工具")

app.include_router(venues.router)
app.include_router(price_rules.router)
app.include_router(students.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
