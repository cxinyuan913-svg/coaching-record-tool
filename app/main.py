"""FastAPI 進入點。"""
from fastapi import FastAPI

from app import models  # noqa: F401  匯入以註冊 ORM models 到 Base.metadata
from app.database import Base, engine
from app.routers import venues

# 六張表一次建齊
Base.metadata.create_all(bind=engine)

app = FastAPI(title="羽球教練紀錄工具")

app.include_router(venues.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
