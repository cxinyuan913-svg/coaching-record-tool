"""資料庫連線設定：SQLite engine 與 session。"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 可用環境變數覆寫，測試時指向獨立的暫存資料庫，不會動到真實的 coaching.db
SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./coaching.db")

# SQLite 須加 check_same_thread=False 才能在 FastAPI 多執行緒下使用
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依賴注入用：取得一個 session，用完自動關閉。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
