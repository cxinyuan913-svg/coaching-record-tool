"""FastAPI 進入點。"""
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app import models  # noqa: F401  匯入以註冊 ORM models 到 Base.metadata
from app import scheduler, web_auth
from app.database import Base, SessionLocal, engine, ensure_schema_migrations
from app.routers import (
    adjustments,
    booking,
    booking_parser,
    integrations,
    lessons,
    packages,
    price_rules,
    settings,
    slot_search,
    stats,
    students,
    venue_travel_times,
    venues,
)
from app.seed import seed_price_rules

# 六張表一次建齊
Base.metadata.create_all(bind=engine)
# 既有的 coaching.db 建表時間早於新欄位加入的時間，補上缺少的欄位
ensure_schema_migrations()

with SessionLocal() as db:
    seed_price_rules(db)

app = FastAPI(title="羽球教練紀錄工具")

# 全站都要登入（登入頁、健康檢查、外部系統介接端點除外，見 app/web_auth.py）
app.middleware("http")(web_auth.require_login)
app.include_router(web_auth.router)

app.include_router(venues.router)
app.include_router(price_rules.router)
app.include_router(students.router)
app.include_router(lessons.router)
app.include_router(packages.router)
app.include_router(stats.router)
app.include_router(booking.router)
app.include_router(adjustments.router)
app.include_router(integrations.router)
app.include_router(booking_parser.router)
app.include_router(venue_travel_times.router)
app.include_router(slot_search.router)
app.include_router(settings.router)

# 測試會把 DATABASE_URL 指向暫存資料庫，此時不啟動背景排程，避免跟測試的
# drop_all/create_all 互相干擾，也避免測試過程真的打出 Discord 通知
if "DATABASE_URL" not in os.environ:
    scheduler.start_scheduler()


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """沒被處理的例外也回 JSON {"detail": ...}（預設是純文字 Internal Server Error），
    前端跟自動訂場排程才能一致地判斷錯誤；完整錯誤堆疊照樣寫進伺服器紀錄。"""
    logging.getLogger("app").exception("未處理的錯誤：%s %s", request.method, request.url.path)
    return JSONResponse(
        {"detail": f"伺服器內部錯誤（{type(exc).__name__}），請查看伺服器紀錄"},
        status_code=500,
    )


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
