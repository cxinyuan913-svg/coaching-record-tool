"""FastAPI 進入點。"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app import models  # noqa: F401  匯入以註冊 ORM models 到 Base.metadata
from app.database import Base, SessionLocal, engine
from app.routers import (
    adjustments,
    booking,
    integrations,
    lessons,
    packages,
    price_rules,
    stats,
    students,
    venues,
)
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
app.include_router(adjustments.router)
app.include_router(integrations.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


class NoCacheStaticFiles(StaticFiles):
    """開發階段沒有建置流程、檔名也不會加版本號，瀏覽器預設的試探性快取會讓
    F5 重新整理讀到舊檔案，只能用 Cache-Control: no-cache 強制每次都跟伺服器
    重新驗證 ETag。"""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = "no-cache"
        return response


# 靜態頁面掛載於根路徑，須放在所有 /api 路由之後才不會攔截 API 請求
app.mount("/static", NoCacheStaticFiles(directory="static"), name="static")
app.mount("/", NoCacheStaticFiles(directory="static", html=True), name="pages")
