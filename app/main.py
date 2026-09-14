"""FastAPI 進入點。"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401  匯入以註冊 ORM models 到 Base.metadata
from app.database import Base, SessionLocal, engine
from app.routers import booking, lessons, packages, price_rules, stats, students, venues
from app.seed import seed_price_rules

# 六張表一次建齊
Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    seed_price_rules(db)

app = FastAPI(title="羽球教練紀錄工具")

app.include_router(venues.router)
app.include_router(price_rules.router)
app.include_router(students.router)
app.include_router(lessons.router)
app.include_router(packages.router)
app.include_router(stats.router)
app.include_router(booking.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# 靜態頁面掛載於根路徑，須放在所有 /api 路由之後才不會攔截 API 請求
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="static", html=True), name="pages")
